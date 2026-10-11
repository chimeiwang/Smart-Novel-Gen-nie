"""退役前只读核对在途状态，并备份数据库与旧执行日志；不修复或删除业务记录。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit


def run(args: list[str], *, env: dict[str, str] | None = None, stdin: str | None = None) -> str:
    try:
        result = subprocess.run(  # noqa: S603 - 固定运维程序和参数数组，不经 shell。
            args,
            input=stdin,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"退役预检命令超时：{Path(args[0]).name}") from None
    if result.returncode:
        # psql/pg_dump 的错误可能带连接信息，不能直接写入 CI 日志。
        raise RuntimeError(f"退役预检命令失败：{Path(args[0]).name}，退出码 {result.returncode}")
    return result.stdout.strip()


def database_environment(app: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (app / ".env").read_text().splitlines():
        key, sep, value = line.strip().partition("=")
        if not sep or key not in {
            "DATABASE_URL",
            "DURABLE_AGENT_EXECUTION_ROUTE_MODE",
            "VIDEO_PREVIEW_ENABLED",
        }:
            continue
        if key in values:
            raise ValueError("退役配置包含重复项")
        values[key] = value.strip().strip("\"'")
    if values.get("DURABLE_AGENT_EXECUTION_ROUTE_MODE", "off") != "off":
        raise ValueError("退役前必须关闭旧引擎新建路由")
    if values.get("VIDEO_PREVIEW_ENABLED", "false") != "false":
        raise ValueError("生产视频必须保持关闭")
    url = urlsplit(values["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://", 1))
    if (
        url.scheme != "postgresql"
        or url.path != "/novelwriter"
        or url.fragment
        or url.query
        or not url.hostname
        or not url.username
        or not url.password
    ):
        raise ValueError("退役只允许明确的 novelwriter 生产数据库")
    return {
        **{key: value for key, value in os.environ.items() if not key.startswith("PG")},
        "PGHOST": "127.0.0.1" if url.hostname == "host.docker.internal" else (url.hostname or ""),
        "PGPORT": str(url.port or 5432),
        "PGDATABASE": "novelwriter",
        "PGUSER": unquote(url.username or ""),
        "PGPASSWORD": unquote(url.password or ""),
        "PGCONNECT_TIMEOUT": "10",
        "PGOPTIONS": "-c default_transaction_read_only=on -c statement_timeout=30000",
    }


def database_snapshot(env: dict[str, str]) -> dict[str, int]:
    statement = """
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT json_build_object(
  'activeV2Runs',(SELECT count(*) FROM "WorkflowRun" WHERE "engineVersion"=2
    AND status::text NOT IN ('completed','failed','cancelled')),
  'nonterminalV2Steps',(SELECT count(*) FROM "WorkflowStep" s JOIN "WorkflowRun" r ON r.id=s."runId"
    WHERE r."engineVersion"=2 AND s.status::text NOT IN ('completed','failed','skipped')),
  'unsettledReservations',(SELECT count(*) FROM "WorkflowBillingReservation"
    WHERE status::text NOT IN ('settled','released')));
COMMIT;
"""
    output = run(
        [
            "psql",
            "--no-psqlrc",
            "--quiet",
            "--tuples-only",
            "--no-align",
            "--set=ON_ERROR_STOP=1",
            "--command",
            statement,
        ],
        env=env,
    )
    facts = json.loads(output)
    if (
        not isinstance(facts, dict)
        or set(facts) != {"activeV2Runs", "nonterminalV2Steps", "unsettledReservations"}
        or any(type(v) is not int or v < 0 for v in facts.values())
    ):
        raise ValueError("退役预检返回了无效计数")
    if facts["activeV2Runs"] or facts["nonterminalV2Steps"]:
        raise ValueError("仍有旧引擎在途任务；保留现网，待原引擎完成后重试")
    # 未知账务继续挂账，由历史对账入口处理，不能为发布改成零用量。
    return facts


def journal_snapshot(app: Path, container: str) -> dict[str, object]:
    script = (app / "scripts/retirement_execution_snapshot.lua").read_text()
    facts = json.loads(
        run(["docker", "exec", "-i", container, "redis-cli", "--raw", "EVAL", script, "0"])
    )
    if not isinstance(facts, dict) or "error" in facts or facts.get("quarantined") is not False:
        raise ValueError("旧日志排空索引无效或处于恢复隔离，停止退役")
    if any(facts.get(key) != [] for key in ("active", "pending", "leased", "rejected")):
        raise ValueError("旧执行日志仍有执行或回调，停止退役")
    return facts


def main() -> None:
    if len(sys.argv) != 3:
        raise ValueError("必须传入当前 Core 和可选的旧日志容器")
    core, journal = sys.argv[1:]
    if any(value and not re.fullmatch(r"[A-Za-z0-9_.-]+", value) for value in (core, journal)):
        raise ValueError("容器标识无效")
    app = Path(os.environ["APP_DIR"])
    sha = os.environ["DEPLOY_SHA"]
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("退役备份必须绑定完整部署提交")
    # 只读取运行 Core，目标 .env 不能代替当前进程的路由状态。
    run(
        [
            "docker",
            "exec",
            core,
            "/bin/sh",
            "-ec",
            'test "${DURABLE_AGENT_EXECUTION_ROUTE_MODE:-off}" = off',
        ]
    )
    if not journal:
        label = run(
            [
                "docker",
                "inspect",
                "--format",
                '{{ index .Config.Labels "cn.inkforge.execution-engine" }}',
                core,
            ]
        )
        if label != "v1":
            raise ValueError("旧引擎日志容器缺失，无法证明未送达回调已排空")
    env = database_environment(app)
    before = database_snapshot(env)
    journal_facts = journal_snapshot(app, journal) if journal else None
    if database_snapshot(env) != before:
        raise ValueError("排空检查期间历史状态发生变化，保留现网后重试")
    # 每次发布保留独立恢复点；不覆盖旧备份，也不输出任何作品或凭据。
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")  # noqa: UP017 - 生产服务器使用 Python 3.10。
    target = (
        Path(os.environ.get("BACKUP_ROOT", "/srv/inkforge-backups")) / f"retirement-{sha}-{stamp}"
    )
    target.mkdir(parents=True, mode=0o700)
    os.chmod(target, 0o700)
    dump = target / "database.dump"
    run(["pg_dump", "--format=custom", "--no-owner", "--no-acl", "--file", str(dump)], env=env)
    os.chmod(dump, 0o600)
    run(["pg_restore", "--list", str(dump)])
    if journal:
        remote = f"/data/.retirement-{sha}-{stamp}.rdb"
        try:
            run(["docker", "exec", "--user", "999:999", journal, "redis-cli", "--rdb", remote])
            run(["docker", "exec", "--user", "999:999", journal, "redis-check-rdb", remote])
            run(["docker", "cp", f"{journal}:{remote}", str(target / "execution-journal.rdb")])
            os.chmod(target / "execution-journal.rdb", 0o600)
        finally:
            run(["docker", "exec", "--user", "999:999", journal, "rm", "-f", "--", remote])
    (target / "facts.json").write_text(
        json.dumps({"database": before, "journal": journal_facts}, ensure_ascii=False) + "\n"
    )
    checksums = []
    for path in sorted(target.iterdir()):
        os.chmod(path, 0o600)
        digest = hashlib.sha256()
        # Python 3.10 没有 file_digest；逐块读取到 EOF，完整覆盖大型备份。
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        checksums.append(f"{digest.hexdigest()}  {path.name}")
    (target / "SHA256SUMS").write_text("\n".join(checksums) + "\n")
    os.chmod(target / "SHA256SUMS", 0o600)
    if database_snapshot(env) != before:
        raise ValueError("备份期间历史状态发生变化，保留现网后重试")
    if journal:
        journal_snapshot(app, journal)
    print(f"退役排空及备份通过：{target}；历史待对账数={before['unsettledReservations']}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, KeyError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from None
