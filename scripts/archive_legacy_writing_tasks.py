"""具名退出旧写作执行；仅允许修改冻结 Task 的 phase 与 updatedAt。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, quote, unquote, urlsplit, urlunsplit

UTC = timezone.utc  # noqa: UP017 - 运维入口必须兼容服务器 Python 3.10。

ALLOWED_PHASES = {"idle", "awaiting_user_review"}
STATIC_METRICS = {
    "v1WritingTasksActive", "v1WritingTasksAwaitingUser", "v1WritingTasksRecoverable",
    "v1ArtifactsAwaitingUser", "v1ArtifactsRecoverable",
}
EXECUTION_METRICS = {
    "v1CommandsActive", "v1OutboxUndelivered", "v1AgentJobsQueued",
    "v1AgentJobsOrCallbacksRunning", "v2ExecutionsActive", "v2CallbacksPending",
    "v2CallbacksLeased", "v2CallbacksRejected", "v2RunsActive", "v2StepsActive",
    "v2BillingReserved", "v2BillingReconciliationRequired",
}
REASON = "用户授权退出旧执行，小说成果及来源保留"


class ArchiveError(Exception):
    """只携带可以安全公开的固定诊断。"""


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ArchiveError("JSON 含重复字段")
        result[key] = value
    return result


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_json(path, value):
    descriptor, temporary = tempfile.mkstemp(prefix=".archive-write-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(canonical(value) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        # link 原子发布完整文件且不覆盖任何已存在归档；中断不会留下半份最终回执。
        os.link(temporary, path)
    finally:
        Path(temporary).unlink()
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def timestamp(value):
    if not isinstance(value, str):
        raise ArchiveError("冻结更新时间无效")
    parts = re.fullmatch(
        r"([0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}:[0-9]{2})"
        r"(?:\.([0-9]{1,6}))?(Z|[+-][0-9]{2}:[0-9]{2})?", value,
    )
    if parts is None:
        raise ArchiveError("冻结更新时间无效")
    normalized = parts[1]
    if parts[2] is not None:
        # PostgreSQL 省略小数秒末尾零；补齐到 Python 3.10 可解析的微秒，不改变精度。
        normalized += "." + parts[2].ljust(6, "0")
    normalized += (parts[3] or "").replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    except (ValueError, OverflowError) as error:
        raise ArchiveError("冻结更新时间无效") from error
    return parsed


def validate_scope(scope, database):
    if database not in {"novelwriterdev", "novelwriter"}:
        raise ArchiveError("只允许具名开发库或正式库")
    if not isinstance(scope, dict) or set(scope) != {"schemaVersion", "database", "tasks"}:
        raise ArchiveError("冻结清单字段不完整")
    if scope["schemaVersion"] != 1 or scope["database"] != database:
        raise ArchiveError("冻结清单数据库或版本不匹配")
    if not isinstance(scope["tasks"], list) or not scope["tasks"]:
        raise ArchiveError("冻结任务清单不能为空")
    seen = set()
    for task in scope["tasks"]:
        if not isinstance(task, dict) or set(task) != {"id", "phase", "updatedAt", "novelId"}:
            raise ArchiveError("冻结任务必须包含精确 ID、阶段、更新时间和小说 ID")
        if any(not isinstance(task[key], str) or not task[key] for key in task):
            raise ArchiveError("冻结任务字段无效")
        if task["phase"] not in ALLOWED_PHASES or task["id"] in seen:
            raise ArchiveError("冻结任务重复或不属于允许退出的旧阶段")
        timestamp(task["updatedAt"])
        seen.add(task["id"])
    return scope


def run(arguments, *, environment, input_text=None, timeout=180):
    try:
        result = subprocess.run(  # noqa: S603 - 固定本机工具，SQL 仅通过 stdin 传递
            arguments, input=input_text, capture_output=True, text=True,
            encoding="utf-8", env=environment, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise ArchiveError("具名旧执行维护超时，未确认提交；请运行 verify 核对") from error
    if result.returncode != 0:
        # 数据库 stderr 可能含用户字段、SQL 上下文或凭据，禁止转发。
        raise ArchiveError("具名旧执行维护被拒绝或数据库检查失败，未通过保全校验")
    return result.stdout


def database_connection(env_file, database, directory):
    values = []
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("DATABASE_URL="):
            value = line.removeprefix("DATABASE_URL=").strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            values.append(value)
    if len(values) != 1:
        raise ArchiveError("环境文件必须包含唯一数据库地址")
    parts = urlsplit(values[0].replace("postgresql+asyncpg://", "postgresql://", 1))
    query = parse_qsl(parts.query, keep_blank_values=True)
    if (
        parts.scheme != "postgresql" or parts.hostname != "host.docker.internal"
        or parts.path != "/" + database or parts.fragment
        or len({key for key, _ in query}) != len(query)
        or any(key not in {"application_name", "sslmode"} for key, _ in query)
    ):
        raise ArchiveError("数据库地址不符合具名本机服务器范围")
    username, password = unquote(parts.username or ""), unquote(parts.password or "")
    if not username or not password or any(c in username + password for c in "\r\n\0"):
        raise ArchiveError("数据库凭据格式无效")
    port = parts.port or 5432
    password_file = directory / "pgpass"
    fields = ["127.0.0.1", str(port), database, username, password]
    descriptor = os.open(password_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(":".join(value.replace("\\", "\\\\").replace(":", "\\:")
                              for value in fields) + "\n")
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith("PG") and key != "DATABASE_URL"}
    environment.update({
        "PGPASSFILE": str(password_file),
        "PGOPTIONS": "-c statement_timeout=120000 -c lock_timeout=5000",
    })
    safe_url = urlunsplit(parts._replace(netloc=f"{quote(username, safe='')}@127.0.0.1:{port}"))
    return safe_url, environment


def literal(value):
    return "'" + value.replace("'", "''") + "'"


def identifier(value):
    return '"' + value.replace('"', '""') + '"'


class Database:
    def __init__(self, url, environment, scope):
        self.url, self.environment, self.scope = url, environment, scope
        self.ids = ",".join(literal(task["id"]) for task in scope["tasks"])

    def sql(self, query):
        return run(["psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1", "-d", self.url],
                   environment=self.environment, input_text=query)

    def tables(self):
        result = self.sql("""
            BEGIN READ ONLY;
            SELECT coalesce(json_agg(c.relname ORDER BY c.relname), '[]'::json)
            FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relkind IN ('r','p');
            COMMIT;
        """)
        tables = json.loads(result)
        if not {"WritingTask", "WritingRunCommand", "WritingEventOutbox"}.issubset(tables):
            raise ArchiveError("数据库缺少旧执行结构")
        return tables

    def fingerprints(self, tables):
        queries = []
        for table in tables:
            row = "to_jsonb(t)"
            if table == "WritingTask":
                row = (f"CASE WHEN t.id IN ({self.ids}) THEN "
                       "to_jsonb(t)-'phase'-'updatedAt' ELSE to_jsonb(t) END")
            queries.append(f"""
                SELECT {literal(table)} AS name, jsonb_build_object(
                    'count', count(*), 'sha256', encode(sha256(convert_to(
                        coalesce(string_agg(value, E'\\n' ORDER BY value), ''), 'UTF8')), 'hex')
                ) AS fact FROM (SELECT ({row})::text AS value
                               FROM public.{identifier(table)} t) rows
            """)  # noqa: S608 - 标识符与值分别严格引用，SQL 不经过 shell
        return ("SELECT jsonb_object_agg(name, fact) FROM ("  # noqa: S608 - 仅拼接上方受控查询
                + " UNION ALL ".join(queries) + ") all_tables")

    def snapshot(self):
        tables = self.tables()
        query = f"""
            BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
            SET LOCAL TIME ZONE 'UTC';
            SELECT jsonb_build_object(
                'database', current_database(),
                'databaseOid', (SELECT oid FROM pg_catalog.pg_database
                                WHERE datname=current_database()),
                'tables', ({self.fingerprints(tables)}),
                'tasks', (SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY t.id), '[]'::jsonb)
                          FROM public."WritingTask" t WHERE id IN ({self.ids})),
                'activeCommands', (SELECT count(*) FROM public."WritingRunCommand"
                    WHERE "taskId" IN ({self.ids})
                      AND status IN ('pending','submitted','processing')),
                'undeliveredOutbox', (SELECT count(*) FROM public."WritingEventOutbox"
                    WHERE "taskId" IN ({self.ids})
                      AND "deliveryState" IN ('pending','delivering','blocked')),
                'applyingArtifacts', (SELECT count(*) FROM public."ReviewArtifact"
                    WHERE status='applying')
            );
            COMMIT;
        """  # noqa: S608 - ID 仅由 literal 转义进入 SQL
        result = json.loads(self.sql(query))
        if result["database"] != self.scope["database"]:
            raise ArchiveError("实际连接数据库与冻结清单不一致")
        return result

    def apply(self, before, intent):
        tables = self.tables()
        if set(tables) != set(before["tables"]):
            raise ArchiveError("备份后数据库表集合已变化")
        scope_rows = canonical([{**task, "updatedAt": timestamp(task["updatedAt"]).isoformat()}
                                for task in self.scope["tasks"]])
        expected_tables = literal(canonical(before["tables"])) + "::jsonb"
        target = literal(self.scope["database"])
        retired_at = literal(intent["retiredAt"])
        locks = ",".join("public." + identifier(table) for table in tables)
        block_tag = "$archive_" + uuid.uuid4().hex + "$"
        while block_tag in scope_rows + expected_tables + locks:
            block_tag = "$archive_" + uuid.uuid4().hex + "$"
        # 所有内容检查和 CAS 处于一个有界 DO statement；表锁仍允许普通 SELECT。
        query = f"""
            BEGIN;
            SET LOCAL TIME ZONE 'UTC';
            SET LOCAL lock_timeout='5s';
            SET LOCAL statement_timeout='120s';
            LOCK TABLE {locks} IN SHARE ROW EXCLUSIVE MODE;
            DO {block_tag}
            DECLARE current_facts jsonb; archived_count bigint; affected bigint;
            BEGIN
                IF current_database()<>{target} OR
                  (SELECT oid FROM pg_catalog.pg_database WHERE datname=current_database())
                    <>{int(before['databaseOid'])} THEN
                    RAISE EXCEPTION '归档数据库身份不匹配';
                END IF;
                SELECT ({self.fingerprints(tables)}) INTO current_facts;
                IF current_facts <> {expected_tables} THEN
                    RAISE EXCEPTION '备份后保全内容已变化';
                END IF;
                IF EXISTS (SELECT 1 FROM public."WritingRunCommand"
                    WHERE "taskId" IN ({self.ids})
                      AND status IN ('pending','submitted','processing'))
                  OR EXISTS (SELECT 1 FROM public."WritingEventOutbox"
                    WHERE "taskId" IN ({self.ids})
                      AND "deliveryState" IN ('pending','delivering','blocked'))
                  OR EXISTS (SELECT 1 FROM public."ReviewArtifact"
                    WHERE status='applying') THEN
                    RAISE EXCEPTION '旧执行尚未静止';
                END IF;
                SELECT count(*) INTO archived_count FROM public."WritingTask"
                    WHERE id IN ({self.ids}) AND phase='error'
                      AND "updatedAt"={retired_at}::timestamp;
                IF archived_count <> {len(self.scope['tasks'])} THEN
                    IF archived_count <> 0 OR EXISTS (
                      SELECT 1 FROM jsonb_to_recordset({literal(scope_rows)}::jsonb)
                        AS s(id text, phase text, "updatedAt" text, "novelId" text)
                      LEFT JOIN public."WritingTask" t ON t.id=s.id
                      WHERE t.id IS NULL OR t.phase::text<>s.phase OR t."novelId"<>s."novelId"
                         OR t."updatedAt"<>s."updatedAt"::timestamp
                    ) THEN RAISE EXCEPTION '冻结任务状态已变化'; END IF;
                    UPDATE public."WritingTask" SET phase='error',
                        "updatedAt"={retired_at}::timestamp
                        WHERE id IN ({self.ids});
                    GET DIAGNOSTICS affected = ROW_COUNT;
                    IF affected <> {len(self.scope['tasks'])} THEN
                        RAISE EXCEPTION '更新范围不匹配';
                    END IF;
                END IF;
                SELECT ({self.fingerprints(tables)}) INTO current_facts;
                IF current_facts <> {expected_tables} THEN
                    RAISE EXCEPTION '事务内保全检查失败';
                END IF;
                IF (SELECT count(*) FROM public."WritingTask" WHERE id IN ({self.ids})
                    AND phase='error' AND "updatedAt"={retired_at}::timestamp)
                    <> {len(self.scope['tasks'])} THEN
                    RAISE EXCEPTION '退出终态未按具名意图保存';
                END IF;
            END;
            {block_tag};
            COMMIT;
        """  # noqa: S608 - 所有值/标识符已引用，随机 DO delimiter 不与内容相撞
        self.sql(query)


def assert_original(snapshot, scope):
    rows = {row["id"]: row for row in snapshot["tasks"]}
    if len(rows) != len(scope["tasks"]):
        raise ArchiveError("冻结任务已缺失")
    if (snapshot["activeCommands"] or snapshot["undeliveredOutbox"]
            or snapshot["applyingArtifacts"]):
        raise ArchiveError("目标任务仍有活动命令或未送达事件")
    for task in scope["tasks"]:
        row = rows.get(task["id"])
        if (row is None or row["phase"] != task["phase"] or row["novelId"] != task["novelId"]
                or timestamp(row["updatedAt"]) != timestamp(task["updatedAt"])):
            raise ArchiveError("冻结任务状态或更新时间已变化，请重新盘点")


def assert_preserved(before, after, intent):
    if (before["tables"] != after["tables"] or before["databaseOid"] != after["databaseOid"]
            or before["database"] != after["database"]
            or after["activeCommands"] or after["undeliveredOutbox"]
            or after["applyingArtifacts"]):
        raise ArchiveError("保全内容或数据库身份发生变化")
    if len(before["tasks"]) != len(after["tasks"]):
        raise ArchiveError("归档任务数量变化")
    for row in after["tasks"]:
        if row["phase"] != "error" or timestamp(row["updatedAt"]) != timestamp(intent["retiredAt"]):
            raise ArchiveError("任务未按本次具名归档退出")


def require_queue_idle(app_dir, database, environment):
    output = run(["sh", str(app_dir / "scripts" / "durable-agent-execution-migration.sh"),
                  "drain-status", database], environment=environment, timeout=180)
    report = json.loads(output, object_pairs_hook=unique_object)
    metrics = report.get("metrics", {})
    if (report.get("database") != database
            or report.get("coreRuntime", {}).get("routeMode") != "off"
            or report.get("coreRuntime", {}).get("v1FreshStartsEnabled") is not False
            or set(metrics) != STATIC_METRICS | EXECUTION_METRICS
            or any(type(metrics[name].get("count")) is not int or metrics[name]["count"] != 0
                   for name in EXECUTION_METRICS)):
        raise ArchiveError("真实联合 drain 报告仍有活动命令、队列、回调或计费尾项")
    finished = timestamp(report["sampleWindow"]["finishedAt"])
    age = (datetime.now(UTC).replace(tzinfo=None) - finished).total_seconds()
    if not 0 <= age <= 60:
        raise ArchiveError("联合 drain 报告已过期")
    return report


def protected_file(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
        raise ArchiveError("归档文件必须是非符号链接的 0600 普通文件")


def load_archive(directory, scope):
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700:
        raise ArchiveError("归档目录必须是非符号链接的 0700 目录")
    protected_file(directory / "backup.json")
    metadata = read_json(directory / "backup.json")
    for name in ("scope.json", "before.json", "database.dump"):
        protected_file(directory / name)
        if metadata.get("files", {}).get(name) != file_hash(directory / name):
            raise ArchiveError("原始归档或备份哈希不匹配")
    if read_json(directory / "scope.json") != scope:
        raise ArchiveError("本次清单与不可覆盖的原归档不一致")
    return read_json(directory / "before.json")


def perform(action, database, scope_path, directory, app_dir, env_file):
    scope = validate_scope(read_json(scope_path), database)
    with tempfile.TemporaryDirectory(prefix="inkforge-legacy-archive-") as temporary:
        url, environment = database_connection(env_file, database, Path(temporary))
        connection = Database(url, environment, scope)
        if action == "preview":
            before = connection.snapshot()
            assert_original(before, scope)
            return {"action": action, "database": database, "taskCount": len(scope["tasks"]),
                    "protectedTableCount": len(before["tables"]), "readyForBackup": True}
        if action == "backup":
            if directory.exists():
                load_archive(directory, scope)
                return {"action": action, "existing": True, "taskCount": len(scope["tasks"])}
            directory.mkdir(mode=0o700)
            before = connection.snapshot()
            assert_original(before, scope)
            save_json(directory / "scope.json", scope)
            save_json(directory / "before.json", before)
            dump = directory / "database.dump"
            run(["pg_dump", "--format=custom", "--no-owner", "--no-acl", "--file", str(dump),
                 "--dbname", url], environment=environment, timeout=900)
            os.chmod(dump, 0o600)
            run(["pg_restore", "--list", str(dump)], environment=environment)
            if connection.snapshot() != before:
                raise ArchiveError("备份期间数据已变化；保留原归档，必须另建备份目录")
            save_json(directory / "backup.json", {
                "schemaVersion": 1, "database": database, "reason": REASON,
                "files": {name: file_hash(directory / name)
                          for name in ("scope.json", "before.json", "database.dump")},
            })
            return {"action": action, "taskCount": len(scope["tasks"]), "verifiedBackup": True}
        before = load_archive(directory, scope)
        intent_path = directory / "apply-intent.json"
        if action == "apply":
            report = require_queue_idle(app_dir, database, environment)
            if not intent_path.exists():
                assert_original(connection.snapshot(), scope)
                save_json(intent_path, {
                    "schemaVersion": 1, "database": database, "reason": REASON,
                    "beforeSha256": file_hash(directory / "before.json"),
                    "retiredAt": datetime.now(UTC).replace(tzinfo=None).isoformat(
                        timespec="milliseconds"),
                    "queueReport": report,
                })
            protected_file(intent_path)
            intent = read_json(intent_path)
            if (intent.get("database") != database
                    or intent.get("beforeSha256") != file_hash(directory / "before.json")):
                raise ArchiveError("具名归档意图与原备份不一致")
            connection.apply(before, intent)
        else:
            protected_file(intent_path)
            intent = read_json(intent_path)
            if (intent.get("database") != database
                    or intent.get("beforeSha256") != file_hash(directory / "before.json")):
                raise ArchiveError("具名归档意图与原备份不一致")
        after = connection.snapshot()
        assert_preserved(before, after, intent)
        if not (directory / "after.json").exists():
            save_json(directory / "after.json", after)
        else:
            protected_file(directory / "after.json")
            if read_json(directory / "after.json") != after:
                raise ArchiveError("独立核验与原退出回执不一致")
        return {"action": action, "database": database, "taskCount": len(scope["tasks"]),
                "archived": True, "allProtectedValuesUnchanged": True}


def main():
    # 具名维护只允许 Linux 服务器执行；纯清单和时间校验仍可跨平台复验。
    if os.name != "posix":
        raise ArchiveError("具名旧执行维护只支持 POSIX 服务器")
    import fcntl

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preview", "backup", "apply", "verify"))
    parser.add_argument("database", choices=("novelwriterdev", "novelwriter"))
    parser.add_argument("scope", type=Path)
    parser.add_argument("archive", type=Path)
    arguments = parser.parse_args()
    app_dir = Path(os.environ.get("APP_DIR", Path.cwd())).resolve()
    env_file = Path(os.environ.get("DURABLE_AGENT_MIGRATION_ENV_FILE", app_dir / ".env"))
    # 与原发布/迁移共用同一服务器锁，不新增调度器或发布控制面。
    lock_path = app_dir / ".inkforge-production.lock"
    descriptor = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = perform(arguments.action, arguments.database, arguments.scope,
                         arguments.archive, app_dir, env_file)
        print(canonical(result))
    finally:
        os.close(descriptor)


if __name__ == "__main__":
    try:
        main()
    except ArchiveError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
    except Exception:
        print("具名旧执行维护无法完成；未输出数据库或用户正文详情", file=sys.stderr)
        sys.exit(1)
