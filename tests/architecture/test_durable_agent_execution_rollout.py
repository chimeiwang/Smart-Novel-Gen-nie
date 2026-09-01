from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from inkforge_core.db.schema_guard import project_schema_contract

from tests.architecture.durable_agent_execution_fixtures import (
    BASE_SCHEMA,
    _psql,
    _scalar,
)

ROOT = Path(__file__).parents[2]
HELPER = ROOT / "scripts" / "durable-agent-execution-migration.sh"
ROLLOUT_GATE = ROOT / "scripts" / "durable-agent-v2-rollout-gate.sh"
IMAGE_VERIFIER = ROOT / "scripts" / "verify-durable-agent-v2-image.sh"
POSTGRES_QUARANTINE = ROOT / "scripts" / "prepare-postgres-restore-quarantine.sh"
FORWARD = ROOT / "scripts" / "migrations" / "20260831_durable_agent_execution.sql"
ROLLBACK = ROOT / "scripts" / "migrations" / "20260831_durable_agent_execution.rollback.sql"
PRE_CONTRACT = (
    ROOT
    / "apps"
    / "core-api-java"
    / "src"
    / "main"
    / "resources"
    / "db"
    / "pre-durable-agent-v2"
    / "schema-contract.json"
)
POST_CONTRACT = (
    ROOT
    / "apps"
    / "core-api-java"
    / "src"
    / "main"
    / "resources"
    / "db"
    / "post-durable-agent-v2"
    / "schema-contract.json"
)
POSIX_SHELL = shutil.which("sh") or str(
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "bin" / "sh.exe"
)


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _posix_path(path: Path) -> str:
    resolved = path.resolve()
    if os.name != "nt":
        return resolved.as_posix()
    return f"/{resolved.drive[0].lower()}{resolved.as_posix()[2:]}"


def _execution_manifest_fingerprint(path: Path) -> str:
    document = json.loads(path.read_text(encoding="utf-8"))
    canonical = json.dumps(
        document,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


_DRAIN_POSTGRES_METRICS = {
    "v1WritingTasksActive",
    "v1WritingTasksAwaitingUser",
    "v1WritingTasksRecoverable",
    "v1CommandsActive",
    "v1OutboxUndelivered",
    "v1ArtifactsAwaitingUser",
    "v1ArtifactsRecoverable",
    "v2RunsActive",
    "v2StepsActive",
    "v2BillingReserved",
    "v2BillingReconciliationRequired",
}


def _drain_source_files(
    root: Path,
    *,
    postgres_metric: str | None = None,
    ordinary_category: str | None = None,
    execution_category: str | None = None,
    quarantined: bool = False,
    skew_seconds: int = 0,
    index_version: str = "1",
    ordinary_run_id: str = "a" * 40,
    execution_run_id: str = "b" * 40,
    postgres_after_identity: dict[str, int | str] | None = None,
    pre_contract: bool = False,
) -> dict[str, str]:
    observed = datetime(2026, 9, 1, 3, tzinfo=UTC)
    observed_text = observed.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    observed_ms = str(round(observed.timestamp() * 1000))
    redis_ms = str(round((observed.timestamp() + skew_seconds) * 1000))
    metric_names = _DRAIN_POSTGRES_METRICS
    if pre_contract:
        metric_names = {
            name for name in _DRAIN_POSTGRES_METRICS if not name.startswith("v2")
        }
    postgres_metrics: dict[str, list[dict[str, str]]] = {
        name: [] for name in metric_names
    }
    if postgres_metric is not None:
        postgres_metrics[postgres_metric] = [
            {"id": "oldest-postgres-id", "at": observed_text}
        ]
    postgres = {
        "sourceVersion": "2",
        "database": "novelwriterdev",
        "identity": {
            "databaseOid": 16_384,
            "serverAddress": "127.0.0.1",
            "serverPort": 5432,
            "serverVersionNum": 140019,
        },
        "observedAt": observed_text,
        "snapshot": "100:100:",
        "walLsn": "0/16B6A00",
        "metrics": postgres_metrics,
    }
    ordinary = {
        "sourceVersion": "2",
        "indexVersion": index_version,
        "redisRunId": ordinary_run_id,
        "observedAtMs": redis_ms,
        "queued": [],
        "running": [],
    }
    if ordinary_category is not None:
        ordinary[ordinary_category] = [
            {"id": "job-oldest", "createdAtMs": observed_ms}
        ]
    execution: dict[str, object] = {
        "sourceVersion": "2",
        "indexVersion": index_version,
        "redisRunId": execution_run_id,
        "observedAtMs": observed_ms,
        "active": [],
        "pending": [],
        "leased": [],
        "rejected": [],
        "quarantined": quarantined,
    }
    if execution_category is not None:
        execution[execution_category] = [
            {"id": "step-oldest", "acceptedAtMs": observed_ms}
        ]
    files: dict[str, str] = {}
    for name, value in (
        ("FAKE_DRAIN_POSTGRES_FILE", postgres),
        ("FAKE_V1_REDIS_FILE", ordinary),
        ("FAKE_V2_REDIS_FILE", execution),
    ):
        path = root / f"{name.lower()}.json"
        path.write_text(
            json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        files[name] = _posix_path(path)
    if postgres_after_identity is not None:
        postgres_after = {**postgres, "identity": postgres_after_identity}
        path = root / "fake_drain_postgres_after_file.json"
        path.write_text(
            json.dumps(postgres_after, ensure_ascii=False, separators=(",", ":"))
            + "\n",
            encoding="utf-8",
        )
        files["FAKE_DRAIN_POSTGRES_AFTER_FILE"] = _posix_path(path)
    return files


def _drain_runtime_file(
    path: Path,
    *,
    core_container: str = "1" * 64,
    route_mode: str = "off",
    v1_fresh_starts: bool = False,
) -> Path:
    value = {
        "sourceVersion": "1",
        "core": {
            "containerId": core_container,
            "imageId": "sha256:" + "4" * 64,
            "schemaReady": True,
            "routeMode": route_mode,
            "v1FreshStartsEnabled": v1_fresh_starts,
        },
        "redis": {
            "containerId": "2" * 64,
            "imageId": "sha256:" + "5" * 64,
            "redisRunId": "a" * 40,
        },
        "executionRedis": {
            "containerId": "3" * 64,
            "imageId": "sha256:" + "6" * 64,
            "redisRunId": "b" * 40,
        },
    }
    path.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return path


class MigrationFixture:
    def __init__(
        self,
        tmp_path: Path,
        *,
        database: str = "novelwriterdev",
        host: str = "host.docker.internal",
        password: str = "pa@ss:word",  # noqa: S107 - 仅用于凭据脱敏测试
    ) -> None:
        self.tmp_path = tmp_path
        self.app_dir = tmp_path / "app"
        self.bin_dir = tmp_path / "bin"
        self.runtime_dir = tmp_path / "runtime"
        self.backup_root = tmp_path / "backups"
        self.log_path = tmp_path / "commands.log"
        self.pgpass_capture = tmp_path / "pgpass.capture"
        self.state_path = tmp_path / "schema-state"
        self.v2_path = tmp_path / "v2-state"
        self.forward_count = tmp_path / "forward-count"
        self.drain_postgres_read_count = tmp_path / "drain-postgres-read-count"
        self.database = database
        self.password = password

        migration_dir = self.app_dir / "scripts" / "migrations"
        pre_dir = (
            self.app_dir
            / "apps"
            / "core-api-java"
            / "src"
            / "main"
            / "resources"
            / "db"
            / "pre-durable-agent-v2"
        )
        post_dir = pre_dir.parent / "post-durable-agent-v2"
        (self.app_dir / "infra").mkdir(parents=True)
        migration_dir.mkdir(parents=True)
        pre_dir.mkdir(parents=True)
        post_dir.mkdir(parents=True)
        self.bin_dir.mkdir()
        self.runtime_dir.mkdir()
        self.backup_root.mkdir()
        shutil.copy2(FORWARD, migration_dir / FORWARD.name)
        shutil.copy2(ROLLBACK, migration_dir / ROLLBACK.name)
        shutil.copy2(PRE_CONTRACT, pre_dir / PRE_CONTRACT.name)
        shutil.copy2(POST_CONTRACT, post_dir / POST_CONTRACT.name)
        shutil.copy2(ROOT / "scripts" / "backup.sh", self.app_dir / "scripts")
        shutil.copy2(
            ROOT / "scripts" / "durable_agent_contract_evidence.py",
            self.app_dir / "scripts",
        )
        for drain_asset in (
            "durable_agent_joint_drain.py",
            "durable_agent_release_boundary.py",
            "durable_agent_v1_queue_snapshot.lua",
            "durable_agent_v2_execution_snapshot.lua",
            "durable_agent_v1_pre_activation_snapshot.lua",
            "durable_agent_v2_pre_activation_snapshot.lua",
            "durable_agent_v1_drain_index_initialize.lua",
            "durable_agent_v2_drain_index_initialize.lua",
        ):
            shutil.copy2(ROOT / "scripts" / drain_asset, self.app_dir / "scripts")
        (self.app_dir / "infra" / "compose.yaml").write_text(
            "services:\n  core-api: {}\n  execution-redis: {}\n",
            encoding="utf-8",
        )
        encoded_password = password.replace("@", "%40").replace(":", "%3A")
        (self.app_dir / ".env").write_text(
            "DATABASE_URL="
            f"postgresql+asyncpg://writer:{encoded_password}@{host}:5432/{database}\n"
            "DURABLE_AGENT_EXECUTION_SCHEMA_READY=false\n"
            "DURABLE_AGENT_EXECUTION_ROUTE_MODE=off\n",
            encoding="utf-8",
        )
        self.state_path.write_text("unmigrated\n", encoding="utf-8")
        self.v2_path.write_text("empty-v2\n", encoding="utf-8")
        self._write_commands()

    def _write_commands(self) -> None:
        python_path = _posix_path(Path(sys.executable))
        _write_executable(self.bin_dir / "python3", f'#!/bin/sh\nexec "{python_path}" "$@"\n')
        _write_executable(
            self.bin_dir / "timeout",
            "#!/bin/sh\n"
            'while [ "$#" -gt 0 ]; do\n'
            '  case "$1" in --foreground|--kill-after=*) shift ;; *) break ;; esac\n'
            "done\n"
            "shift\n"
            'exec "$@"\n',
        )
        _write_executable(
            self.bin_dir / "psql",
            r"""#!/bin/sh
printf 'psql %s\n' "$*" >> "$MIGRATION_LOG"
cp "$PGPASSFILE" "$PGPASS_CAPTURE"
file=''
previous=''
for argument in "$@"; do
  [ "$previous" != '-f' ] || file=$argument
  previous=$argument
done
if [ -n "$file" ]; then
  case "$file" in
    *20260831_durable_agent_execution.rollback.sql)
      printf 'unmigrated\n' > "$MIGRATION_STATE" ;;
    *20260831_durable_agent_execution.sql)
      printf 'migrated\n' > "$MIGRATION_STATE"
      count=0
      [ ! -f "$FORWARD_COUNT" ] || count=$(sed -n '1p' "$FORWARD_COUNT")
      count=$((count + 1))
      printf '%s\n' "$count" > "$FORWARD_COUNT" ;;
    *) exit 41 ;;
  esac
  exit 0
fi
query=$(sed -n '1,$p')
if [ "${FAKE_ACTUAL_DATABASE:-$TARGET_DATABASE}" != "$TARGET_DATABASE" ]; then
  printf 'wrong-database\n'
  exit 0
fi
case "$query" in
  *'WITH migration_shape AS'*) sed -n '1p' "$MIGRATION_STATE" ;;
  *'blockers(metric, id, "createdAt") AS'*)
    [ -n "${FAKE_DRAIN_POSTGRES_FILE:-}" ] || exit 44
    count=0
    [ ! -f "$DRAIN_POSTGRES_READ_COUNT" ] \
      || count=$(sed -n '1p' "$DRAIN_POSTGRES_READ_COUNT")
    count=$((count + 1))
    printf '%s\n' "$count" > "$DRAIN_POSTGRES_READ_COUNT"
    source_file="$FAKE_DRAIN_POSTGRES_FILE"
    if [ "$count" -ge 2 ] && [ -n "${FAKE_DRAIN_POSTGRES_AFTER_FILE:-}" ]; then
      source_file="$FAKE_DRAIN_POSTGRES_AFTER_FILE"
    fi
    sed -n '1p' "$source_file" ;;
  *'count(*)::text FROM public."WorkflowRun" WHERE "engineVersion" = 2'*)
    printf '%s\n' "${FAKE_ALL_V2_RUN_COUNT:-0}" ;;
  *'WorkflowEvidenceBundle'*'workflowRunId'*) sed -n '1p' "$V2_STATE" ;;
  *'status::text NOT IN'*) printf '%s\n' "${FAKE_ACTIVE_V2_RUN_COUNT:-0}" ;;
  *'json_build_object'*)
    printf '%s%s\n' \
      '{"databaseName":"'"$TARGET_DATABASE"'","serverAddress":"127.0.0.1",' \
      '"serverPort":5432,"serverVersion":"14.19","serverVersionNum":140019}' ;;
  *) printf 'unexpected schema query\n' >&2; exit 42 ;;
esac
""",
        )
        _write_executable(
            self.bin_dir / "pg_dump",
            "#!/bin/sh\n"
            "printf 'pg_dump %s\\n' \"$*\" >> \"$MIGRATION_LOG\"\n"
            "output=''\n"
            "previous=''\n"
            'for argument in "$@"; do\n'
            "  [ \"$previous\" != '--file' ] || output=$argument\n"
            '  case "$argument" in --file=*) output=${argument#--file=};; esac\n'
            "  previous=$argument\n"
            "done\n"
            '[ -n "$output" ] || exit 43\n'
            "printf '%s' \"${FAKE_SCHEMA_DUMP_CONTENT:-database-dump-fixture}\" > \"$output\"\n",
        )
        _write_executable(self.bin_dir / "pg_restore", "#!/bin/sh\nexit 0\n")
        _write_executable(
            self.bin_dir / "docker",
            r"""#!/bin/sh
printf 'docker %s\n' "$*" >> "$MIGRATION_LOG"
case " $* " in
  *' compose version '*) exit 0 ;;
  *' compose '*' ps -q core-api '*) printf '%064d\n' 1 ;;
  *' compose '*' ps -q redis '*) printf '%064d\n' 2 ;;
  *' compose '*' ps -q execution-redis '*) printf '%064d\n' 3 ;;
  *' inspect --format {{.Image}} '*) printf 'sha256:%064d\n' 4 ;;
  *' compose '*' exec -T redis redis-cli --raw INFO server '*)
    printf 'run_id:%s\n' 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' ;;
  *' compose '*' exec -T execution-redis redis-cli --raw INFO server '*)
    printf 'run_id:%s\n' 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb' ;;
  *' compose '*' exec -T redis redis-cli --raw PING '*)
    printf 'PONG\n' ;;
  *' compose '*' exec -T execution-redis redis-cli --raw INFO persistence '*)
    printf 'aof_enabled:1\naof_last_write_status:ok\n' ;;
  *' compose '*' exec -T execution-redis redis-cli --raw INFO stats '*)
    printf 'evicted_keys:%s\n' "${FAKE_EXECUTION_EVICTED_KEYS:-0}" ;;
  *' compose '*' exec -T redis redis-cli --raw EVAL_RO '*)
    [ "${FAKE_DRAIN_REDIS_FAILURE:-false}" != true ] || exit 45
    [ -n "${FAKE_V1_REDIS_FILE:-}" ] || exit 46
    sed -n '1p' "$FAKE_V1_REDIS_FILE" ;;
  *' compose '*' exec -T execution-redis redis-cli --raw EVAL_RO '*)
    [ "${FAKE_DRAIN_REDIS_FAILURE:-false}" != true ] || exit 47
    [ -n "${FAKE_V2_REDIS_FILE:-}" ] || exit 48
    sed -n '1p' "$FAKE_V2_REDIS_FILE" ;;
  *' compose '*' exec -T redis redis-cli --raw GET inkforge:runs:drain:index-version '*)
    [ "${FAKE_V1_DRAIN_INDEX_VERSION:-1}" = __missing__ ] \
      || printf '%s\n' "${FAKE_V1_DRAIN_INDEX_VERSION:-1}" ;;
  *' execution-redis '*' GET inkforge:executions:drain:index-version '*)
    [ "${FAKE_V2_DRAIN_INDEX_VERSION:-1}" = __missing__ ] \
      || printf '%s\n' "${FAKE_V2_DRAIN_INDEX_VERSION:-1}" ;;
  *' compose '*' exec -T redis redis-cli --raw EVAL '*)
    printf '%s\n' "${FAKE_V1_DRAIN_INITIALIZE_RESULT:-initialized}" ;;
  *' compose '*' exec -T execution-redis redis-cli --raw EVAL '*)
    printf '%s\n' "${FAKE_V2_DRAIN_INITIALIZE_RESULT:-initialized}" ;;
  *' compose '*' exec -T agent-service python -c '*) exit 0 ;;
  *' compose '*' exec -T core-api /usr/local/bin/inkforge-schema-guard '*)
    [ "${FAKE_CONTRACT_GUARD_STATUS:-0}" = 0 ] || exit "$FAKE_CONTRACT_GUARD_STATUS"
    printf '%s\n' "$FAKE_SCHEMA_GUARD_FINGERPRINT" ;;
  *'INKFORGE_EXPECTED_DATABASE='*)
    [ "${FAKE_CORE_DATABASE_MATCH:-true}" = true ] || exit 31
    printf '%s\n' "${FAKE_SCHEMA_PROFILE:-full}" ;;
  *' compose '*' exec -T core-api '*'V1FreshAgentStartGate.class'*)
    [ "${FAKE_RUNNING_CORE_GATE_IMPLEMENTED:-true}" = true ] || exit 49
    printf '%s\n%s\n%s\n' \
      "${FAKE_RUNNING_CORE_SCHEMA_READY:-true}" \
      "${FAKE_RUNNING_CORE_ROUTE_MODE:-off}" \
      "${FAKE_RUNNING_CORE_V1_FRESH_STARTS:-false}" ;;
  *' compose '*' exec -T core-api '*) exit "${FAKE_CONTRACT_GUARD_STATUS:-0}" ;;
  *' exec --user 999:999 '*' INFO persistence '*)
    printf 'aof_enabled:1\naof_last_write_status:ok\n' ;;
  *' exec --user 999:999 '*' redis-cli --rdb '*) exit 0 ;;
  *' exec --user 999:999 '*' redis-check-rdb '*) exit 0 ;;
  *' cp '*'execution-journal.rdb'*)
    destination=''
    for argument in "$@"; do destination=$argument; done
    printf 'journal-rdb-fixture' > "$destination" ;;
  *' exec --user 999:999 '*' rm -f '*) exit 0 ;;
  *) exit 0 ;;
esac
""",
        )

    def run(
        self,
        action: str,
        *,
        backup_dir: Path | None = None,
        confirm_file: Path | None = None,
        evidence_dir: Path | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = {
            **os.environ,
            "PATH": f"{self.bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            "APP_DIR": _posix_path(self.app_dir),
            "DURABLE_AGENT_MIGRATION_ENV_FILE": _posix_path(self.app_dir / ".env"),
            "DURABLE_AGENT_MIGRATION_BACKUP_ROOT": _posix_path(self.backup_root),
            "TMPDIR": _posix_path(self.runtime_dir),
            "MIGRATION_LOG": _posix_path(self.log_path),
            "PGPASS_CAPTURE": _posix_path(self.pgpass_capture),
            "MIGRATION_STATE": _posix_path(self.state_path),
            "V2_STATE": _posix_path(self.v2_path),
            "FORWARD_COUNT": _posix_path(self.forward_count),
            "DRAIN_POSTGRES_READ_COUNT": _posix_path(
                self.drain_postgres_read_count
            ),
            "TARGET_DATABASE": self.database,
            "FAKE_SCHEMA_GUARD_FINGERPRINT": json.loads(
                POST_CONTRACT.read_text(encoding="utf-8")
            )["fingerprint"],
        }
        if backup_dir is not None:
            env["DURABLE_AGENT_MIGRATION_BACKUP_DIR"] = _posix_path(backup_dir)
        if confirm_file is not None:
            env["DURABLE_AGENT_MIGRATION_CONFIRM_FILE"] = _posix_path(confirm_file)
        if evidence_dir is not None:
            env["DURABLE_AGENT_CONTRACT_EVIDENCE_DIR"] = _posix_path(evidence_dir)
        if extra_env:
            env.update(extra_env)
        return subprocess.run(  # noqa: S603 - 仅执行仓库固定脚本与测试夹具
            [POSIX_SHELL, str(HELPER), action, self.database],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )

    def backup(self) -> Path:
        result = self.run("backup")
        assert result.returncode == 0, result.stderr
        assert result.stdout.startswith("backup-ok:")
        return Path(result.stdout.strip().split(":", 1)[1])

    def confirm(self, token: str) -> Path:
        path = self.tmp_path / f"confirm-{hashlib.sha256(token.encode()).hexdigest()[:8]}"
        path.write_text(token + "\n", encoding="utf-8")
        path.chmod(0o600)
        return path


def _psql_file_execution_count(fixture: MigrationFixture) -> int:
    if not fixture.log_path.exists():
        return 0
    return sum(
        line.startswith("psql ") and " -f " in line
        for line in fixture.log_path.read_text(encoding="utf-8").splitlines()
    )


def test_named_helper_pins_sql_contracts_and_never_sources_env() -> None:
    source = HELPER.read_text(encoding="utf-8")

    for required in (
        "f8342b40c63aba24075fba04a877a5601faa982ef7c40c99d8d164a80b502600",
        "9855a0487d7c5f71723a2fdeda5ae81c3e10dcf0fbc0fa44cd9fceef30000db1",
        "pre-durable-agent-v2/schema-contract.json",
        "post-durable-agent-v2/schema-contract.json",
        "migrated-empty-v2",
        "migrated-with-v2",
        "schema-state:partial",
        "PGPASSFILE",
        "chmod 600",
        "execution-journal.rdb",
        "postgresRestoreRequiresExecutionQuarantine=true",
        "active-v2-count",
        "drain-status",
        "verify-drain",
        "durable_agent_joint_drain.py",
        "EVAL_RO",
        "export-contract",
        "verify-contract",
        "DURABLE_AGENT_CONTRACT_EVIDENCE_DIR",
        "schema-only.sql",
    ):
        assert required in source
    assert "source .env" not in source
    assert ". $env_file" not in source
    assert 'psql "$raw_database_url"' not in source
    assert 'pg_dump "$raw_database_url"' not in source
    assert 'PGOPTIONS="$pg_options -c inkforge' not in source
    assert "生产 GUC 只进入 0600 临时 SQL" in source
    gate_source = ROLLOUT_GATE.read_text(encoding="utf-8")
    assert 'sh "$migration_helper" verify-drain' in gate_source
    route_off_case = gate_source.split("  route-off-drain)", 1)[1].split(
        "  ddl-rollback)", 1
    )[0]
    assert "verify-drain" not in route_off_case
    assert "require_runtime_route_off" in gate_source


def test_status_uses_private_pgpass_without_leaking_credentials(tmp_path: Path) -> None:
    fixture = MigrationFixture(tmp_path)

    result = fixture.run("status")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "unmigrated"
    log = fixture.log_path.read_text(encoding="utf-8")
    assert "writer@127.0.0.1:5432/novelwriterdev" in log
    assert fixture.password not in log
    assert "%40" not in log
    assert fixture.password not in result.stdout
    assert fixture.password not in result.stderr
    assert fixture.pgpass_capture.read_text(encoding="utf-8") == (
        "127.0.0.1:5432:novelwriterdev:writer:pa@ss\\:word\n"
    )
    assert list(fixture.runtime_dir.iterdir()) == []


def test_active_v2_count_is_read_from_postgres_without_leaking_credentials(
    tmp_path: Path,
) -> None:
    fixture = MigrationFixture(tmp_path)
    fixture.state_path.write_text("migrated\n", encoding="utf-8")
    fixture.v2_path.write_text("with-v2\n", encoding="utf-8")

    result = fixture.run(
        "active-v2-count",
        extra_env={"FAKE_ACTIVE_V2_RUN_COUNT": "3"},
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "3"
    log = fixture.log_path.read_text(encoding="utf-8")
    assert "status::text NOT IN" not in log
    assert fixture.password not in log
    assert fixture.password not in result.stdout
    assert fixture.password not in result.stderr


def test_joint_drain_status_and_verify_are_versioned_and_awaiting_user_is_nonzero(
    tmp_path: Path,
) -> None:
    fixture = MigrationFixture(tmp_path)
    fixture.state_path.write_text("migrated\n", encoding="utf-8")
    fixture.v2_path.write_text("with-v2\n", encoding="utf-8")
    zero_dir = tmp_path / "zero"
    zero_dir.mkdir()
    zero_sources = _drain_source_files(zero_dir)

    status = fixture.run("drain-status", extra_env=zero_sources)
    verified = fixture.run("verify-drain", extra_env=zero_sources)

    assert status.returncode == 0, status.stderr
    assert verified.returncode == 0, verified.stderr
    report = json.loads(status.stdout)
    assert report == json.loads(verified.stdout)
    assert set(report) == {
        "schema",
        "schemaVersion",
        "database",
        "coreRuntime",
        "sampleWindow",
        "postgres",
        "redisIndexes",
        "runtimeTopologySha256",
        "v1DrainZero",
        "v2Converged",
        "metrics",
    }
    assert report["schema"] == "inkforge.durable-agent-joint-drain"
    assert report["schemaVersion"] == "2"
    assert report["coreRuntime"]["routeMode"] == "off"
    assert report["coreRuntime"]["v1FreshStartsEnabled"] is False
    assert report["v1DrainZero"] is True
    assert report["v2Converged"] is True
    assert all(
        set(metric) == {"count", "oldestId", "oldestAt", "setSha256"}
        for metric in report["metrics"].values()
    )

    awaiting_dir = tmp_path / "awaiting"
    awaiting_dir.mkdir()
    awaiting_sources = _drain_source_files(
        awaiting_dir,
        postgres_metric="v1ArtifactsAwaitingUser",
    )
    awaiting_status = fixture.run("drain-status", extra_env=awaiting_sources)
    awaiting_verify = fixture.run("verify-drain", extra_env=awaiting_sources)

    assert awaiting_status.returncode == 0, awaiting_status.stderr
    assert awaiting_verify.returncode == 3
    awaiting_report = json.loads(awaiting_verify.stdout)
    assert awaiting_report["coreRuntime"]["routeMode"] == "off"
    assert awaiting_report["v1DrainZero"] is False
    assert awaiting_report["metrics"]["v1ArtifactsAwaitingUser"] | {
        "setSha256": "ignored"
    } == {
        "count": 1,
        "oldestId": "oldest-postgres-id",
        "oldestAt": "2026-09-01T03:00:00.000Z",
        "setSha256": "ignored",
    }
    combined_output = status.stdout + status.stderr + awaiting_verify.stdout
    assert fixture.password not in combined_output
    assert "payloadJson" not in combined_output
    assert "snapshotSha256" not in combined_output


@pytest.mark.parametrize(
    ("postgres_metric", "ordinary_category", "execution_category", "quarantined"),
    [
        ("v1WritingTasksActive", None, None, False),
        ("v1WritingTasksRecoverable", None, None, False),
        ("v1CommandsActive", None, None, False),
        ("v1OutboxUndelivered", None, None, False),
        ("v1ArtifactsRecoverable", None, None, False),
        (None, "queued", None, False),
        (None, "running", None, False),
        ("v2RunsActive", None, None, False),
        ("v2StepsActive", None, None, False),
        ("v2BillingReserved", None, None, False),
        ("v2BillingReconciliationRequired", None, None, False),
        (None, None, "pending", False),
        (None, None, "leased", False),
        (None, None, "rejected", False),
        (None, None, "active", False),
    ],
)
def test_joint_drain_each_authoritative_nonterminal_category_blocks_its_boolean(
    tmp_path: Path,
    postgres_metric: str | None,
    ordinary_category: str | None,
    execution_category: str | None,
    quarantined: bool,
) -> None:
    fixture = MigrationFixture(tmp_path)
    fixture.state_path.write_text("migrated\n", encoding="utf-8")
    fixture.v2_path.write_text("with-v2\n", encoding="utf-8")
    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    sources = _drain_source_files(
        source_dir,
        postgres_metric=postgres_metric,
        ordinary_category=ordinary_category,
        execution_category=execution_category,
        quarantined=quarantined,
    )

    result = fixture.run("drain-status", extra_env=sources)

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    if postgres_metric is not None and postgres_metric.startswith("v1"):
        assert report["v1DrainZero"] is False
    elif ordinary_category is not None:
        assert report["v1DrainZero"] is False
    else:
        assert report["v2Converged"] is False


def test_joint_drain_quarantine_fails_closed_without_report(tmp_path: Path) -> None:
    fixture = MigrationFixture(tmp_path)
    fixture.state_path.write_text("migrated\n", encoding="utf-8")
    fixture.v2_path.write_text("with-v2\n", encoding="utf-8")
    source_dir = tmp_path / "quarantine"
    source_dir.mkdir()
    sources = _drain_source_files(source_dir, quarantined=True)

    result = fixture.run("drain-status", extra_env=sources)

    assert result.returncode != 0
    assert result.stdout == ""


def test_named_drain_index_initialization_only_accepts_empty_authoritative_state(
    tmp_path: Path,
) -> None:
    fixture = MigrationFixture(tmp_path / "empty")
    fixture.state_path.write_text("migrated\n", encoding="utf-8")
    fixture.v2_path.write_text("empty-v2\n", encoding="utf-8")
    missing_markers = {
        "FAKE_V1_DRAIN_INDEX_VERSION": "__missing__",
        "FAKE_V2_DRAIN_INDEX_VERSION": "__missing__",
    }

    initialized = fixture.run(
        "initialize-drain-indexes", extra_env=missing_markers
    )

    assert initialized.returncode == 0, initialized.stderr
    assert initialized.stdout.strip() == (
        "drain-indexes-ready:v1=initialized:v2=initialized"
    )

    active_v1 = MigrationFixture(tmp_path / "active-v1")
    active_v1.state_path.write_text("migrated\n", encoding="utf-8")
    active_v1.v2_path.write_text("empty-v2\n", encoding="utf-8")
    rejected = active_v1.run(
        "initialize-drain-indexes",
        extra_env={
            **missing_markers,
            "FAKE_V1_DRAIN_INITIALIZE_RESULT": "active-or-orphan-index",
        },
    )
    assert rejected.returncode != 0
    assert "不能安全初始化" in rejected.stderr

    existing_v2 = MigrationFixture(tmp_path / "existing-v2")
    existing_v2.state_path.write_text("migrated\n", encoding="utf-8")
    existing_v2.v2_path.write_text("with-v2\n", encoding="utf-8")
    quarantined = existing_v2.run(
        "initialize-drain-indexes", extra_env=missing_markers
    )
    assert quarantined.returncode != 0
    assert "已有 V2 数据" in quarantined.stderr


@pytest.mark.parametrize(
    "extra_env",
    [
        {"FAKE_DRAIN_REDIS_FAILURE": "true"},
        {"FAKE_EXECUTION_EVICTED_KEYS": "1"},
    ],
)
def test_joint_drain_redis_failure_or_eviction_fails_closed(
    tmp_path: Path, extra_env: dict[str, str]
) -> None:
    fixture = MigrationFixture(tmp_path)
    fixture.state_path.write_text("migrated\n", encoding="utf-8")
    fixture.v2_path.write_text("with-v2\n", encoding="utf-8")
    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    sources = _drain_source_files(source_dir)

    result = fixture.run("drain-status", extra_env={**sources, **extra_env})

    assert result.returncode != 0
    assert result.stdout == ""
    assert fixture.password not in result.stderr


def test_joint_drain_source_skew_and_invalid_json_fail_closed(tmp_path: Path) -> None:
    fixture = MigrationFixture(tmp_path)
    fixture.state_path.write_text("migrated\n", encoding="utf-8")
    fixture.v2_path.write_text("with-v2\n", encoding="utf-8")
    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    skewed = _drain_source_files(source_dir, skew_seconds=31)

    skew_result = fixture.run("drain-status", extra_env=skewed)
    assert skew_result.returncode != 0
    assert skew_result.stdout == ""

    (source_dir / "fake_v2_redis_file.json").write_text(
        '{"sourceVersion":"1","error":"corrupt"}\n', encoding="utf-8"
    )
    invalid_result = fixture.run("drain-status", extra_env=skewed)
    assert invalid_result.returncode != 0
    assert invalid_result.stdout == ""
    assert fixture.password not in invalid_result.stderr


def test_unmigrated_boundary_drain_uses_honest_pre_contract_profile(
    tmp_path: Path,
) -> None:
    fixture = MigrationFixture(tmp_path)
    source_dir = tmp_path / "pre-contract-sources"
    source_dir.mkdir()
    sources = _drain_source_files(
        source_dir,
        index_version="pre-activation",
        pre_contract=True,
    )

    result = fixture.run(
        "boundary-drain",
        extra_env={
            **sources,
            "FAKE_RUNNING_CORE_SCHEMA_READY": "false",
            "FAKE_RUNNING_CORE_ROUTE_MODE": "off",
            "FAKE_RUNNING_CORE_V1_FRESH_STARTS": "false",
        },
    )

    assert result.returncode == 0, result.stderr
    document = json.loads(result.stdout)
    assert document["format"] == "inkforge-durable-agent-v2-live-drain/1"
    assert document["mode"] == "pre-contract"
    assert document["schemaState"] == "unmigrated"
    assert document["zeroDrain"] is True
    assert document["coreRuntime"] == {
        "containerId": "0" * 63 + "1",
        "imageId": "sha256:" + "0" * 63 + "4",
        "routeMode": "off",
        "schemaReady": False,
        "v1FreshStartsEnabled": False,
    }
    assert _psql_file_execution_count(fixture) == 0


def test_migrated_schema_with_closed_core_uses_post_contract_closed_profile(
    tmp_path: Path,
) -> None:
    fixture = MigrationFixture(tmp_path)
    fixture.state_path.write_text("migrated\n", encoding="utf-8")
    fixture.v2_path.write_text("empty-v2\n", encoding="utf-8")
    source_dir = tmp_path / "post-contract-closed-sources"
    source_dir.mkdir()
    sources = _drain_source_files(
        source_dir,
        index_version="pre-activation",
    )

    result = fixture.run(
        "boundary-drain",
        extra_env={
            **sources,
            "FAKE_RUNNING_CORE_SCHEMA_READY": "false",
            "FAKE_RUNNING_CORE_ROUTE_MODE": "off",
            "FAKE_RUNNING_CORE_V1_FRESH_STARTS": "false",
        },
    )

    assert result.returncode == 0, result.stderr
    document = json.loads(result.stdout)
    assert document["mode"] == "post-contract-closed"
    assert document["schemaState"] == "migrated-empty-v2-closed"
    assert document["coreRuntime"]["schemaReady"] is False
    assert _psql_file_execution_count(fixture) == 0


@pytest.mark.parametrize(
    "attack",
    ("postgres", "ordinary-redis", "execution-redis", "pending-callback"),
)
def test_pre_contract_boundary_identity_or_callback_drift_fails_before_ddl(
    tmp_path: Path,
    attack: str,
) -> None:
    fixture = MigrationFixture(tmp_path)
    source_dir = tmp_path / "attack-sources"
    source_dir.mkdir()
    options: dict[str, object] = {
        "index_version": "pre-activation",
        "pre_contract": True,
    }
    if attack == "postgres":
        options["postgres_after_identity"] = {
            "databaseOid": 16_384,
            "serverAddress": "127.0.0.1",
            "serverPort": 6432,
            "serverVersionNum": 140019,
        }
    elif attack == "ordinary-redis":
        options["ordinary_run_id"] = "c" * 40
    elif attack == "execution-redis":
        options["execution_run_id"] = "d" * 40
    elif attack == "pending-callback":
        options["execution_category"] = "pending"
    sources = _drain_source_files(source_dir, **options)  # type: ignore[arg-type]

    result = fixture.run(
        "boundary-drain",
        extra_env={
            **sources,
            "FAKE_RUNNING_CORE_SCHEMA_READY": "false",
            "FAKE_RUNNING_CORE_ROUTE_MODE": "off",
            "FAKE_RUNNING_CORE_V1_FRESH_STARTS": "false",
        },
    )

    assert result.returncode != 0
    assert result.stdout == ""
    assert _psql_file_execution_count(fixture) == 0


@pytest.mark.parametrize(
    "mutation",
    [
        "postgres-set-change",
        "postgres-time-reverse",
        "postgres-wal-reverse",
        "container-drift",
        "v1-gate-open",
        "old-v2-index",
    ],
)
def test_joint_drain_stable_window_rejects_every_identity_or_watermark_change(
    tmp_path: Path, mutation: str
) -> None:
    source_dir = tmp_path / mutation
    source_dir.mkdir()
    sources = _drain_source_files(source_dir)
    postgres_before = Path(sources["FAKE_DRAIN_POSTGRES_FILE"])
    postgres_after = source_dir / "postgres-after.json"
    postgres_after.write_text(postgres_before.read_text(encoding="utf-8"), encoding="utf-8")
    runtime_before = _drain_runtime_file(source_dir / "runtime-before.json")
    runtime_after = _drain_runtime_file(source_dir / "runtime-after.json")

    if mutation == "postgres-set-change":
        value = json.loads(postgres_after.read_text(encoding="utf-8"))
        value["metrics"]["v1CommandsActive"] = [
            {"id": "concurrent-command", "at": value["observedAt"]}
        ]
        postgres_after.write_text(json.dumps(value), encoding="utf-8")
    elif mutation == "postgres-time-reverse":
        value = json.loads(postgres_after.read_text(encoding="utf-8"))
        value["observedAt"] = "2026-09-01T02:59:59.000Z"
        postgres_after.write_text(json.dumps(value), encoding="utf-8")
    elif mutation == "postgres-wal-reverse":
        value = json.loads(postgres_after.read_text(encoding="utf-8"))
        value["walLsn"] = "0/0"
        postgres_after.write_text(json.dumps(value), encoding="utf-8")
    elif mutation == "container-drift":
        _drain_runtime_file(runtime_after, core_container="7" * 64)
    elif mutation == "v1-gate-open":
        _drain_runtime_file(runtime_before, v1_fresh_starts=True)
        _drain_runtime_file(runtime_after, v1_fresh_starts=True)
    else:
        execution_path = Path(sources["FAKE_V2_REDIS_FILE"])
        value = json.loads(execution_path.read_text(encoding="utf-8"))
        value["indexVersion"] = "0"
        execution_path.write_text(json.dumps(value), encoding="utf-8")

    result = subprocess.run(  # noqa: S603 - 固定仓库脚本与隔离快照
        [
            sys.executable,
            str(ROOT / "scripts/durable_agent_joint_drain.py"),
            "build",
            "--database",
            "novelwriterdev",
            "--runtime-before",
            str(runtime_before),
            "--postgres-before",
            str(postgres_before),
            "--ordinary-redis",
            sources["FAKE_V1_REDIS_FILE"],
            "--execution-redis",
            sources["FAKE_V2_REDIS_FILE"],
            "--postgres-after",
            str(postgres_after),
            "--runtime-after",
            str(runtime_after),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert result.stdout == ""


@pytest.mark.parametrize(
    ("database", "host", "target"),
    [
        ("other", "host.docker.internal", "novelwriterdev"),
        ("novelwriterdev", "db.example", "novelwriterdev"),
    ],
)
def test_wrong_database_or_host_is_rejected_before_psql(
    tmp_path: Path, database: str, host: str, target: str
) -> None:
    fixture = MigrationFixture(tmp_path, database=database, host=host)
    fixture.database = target

    result = fixture.run("status")

    assert result.returncode != 0
    assert not fixture.log_path.exists()
    assert fixture.password not in result.stderr


def test_server_reported_database_mismatch_is_rejected(tmp_path: Path) -> None:
    fixture = MigrationFixture(tmp_path)

    result = fixture.run("status", extra_env={"FAKE_ACTUAL_DATABASE": "novelwriter"})

    assert result.returncode != 0
    assert "wrong-database" in result.stderr


def test_partial_state_fails_closed_before_backup_or_sql(tmp_path: Path) -> None:
    fixture = MigrationFixture(tmp_path)
    fixture.state_path.write_text("partial\n", encoding="utf-8")

    status = fixture.run("status")
    backup = fixture.run("backup")

    assert status.returncode == 0
    assert status.stdout.strip() == "partial"
    assert backup.returncode != 0
    assert list(fixture.backup_root.iterdir()) == []
    assert " -f " not in fixture.log_path.read_text(encoding="utf-8")


def test_wrong_sql_hash_is_rejected_before_database_access(tmp_path: Path) -> None:
    fixture = MigrationFixture(tmp_path)
    forward = fixture.app_dir / "scripts" / "migrations" / FORWARD.name
    forward.write_text(forward.read_text(encoding="utf-8") + "\n-- drift\n", encoding="utf-8")

    result = fixture.run("status")

    assert result.returncode != 0
    assert "forward SQL 哈希不匹配" in result.stderr
    assert not fixture.log_path.exists()


def test_backup_requires_and_contains_execution_journal(tmp_path: Path) -> None:
    fixture = MigrationFixture(tmp_path)

    backup_dir = fixture.backup()

    for name in (
        "database.dump",
        "execution-journal.rdb",
        "execution-journal.meta",
        "recovery-boundary.meta",
        "durable-agent-migration.meta",
        "SHA256SUMS",
    ):
        assert (backup_dir / name).is_file()
    sums = (backup_dir / "SHA256SUMS").read_text(encoding="utf-8")
    assert "execution-journal.rdb" in sums
    assert "durable-agent-migration.meta" in sums


def test_forward_rejects_backup_missing_journal(tmp_path: Path) -> None:
    fixture = MigrationFixture(tmp_path)
    backup_dir = fixture.backup()
    (backup_dir / "execution-journal.rdb").unlink()

    result = fixture.run("forward", backup_dir=backup_dir)

    assert result.returncode != 0
    assert "备份校验和失败" in result.stderr or "缺少 execution journal" in result.stderr
    assert not fixture.forward_count.exists()


def test_forward_requires_running_dual_contract_guard_before_sql(tmp_path: Path) -> None:
    fixture = MigrationFixture(tmp_path)
    backup_dir = fixture.backup()

    result = fixture.run(
        "forward",
        backup_dir=backup_dir,
        extra_env={"FAKE_CONTRACT_GUARD_STATUS": "19"},
    )

    assert result.returncode != 0
    assert not fixture.forward_count.exists()


def test_forward_is_repeatable_with_one_verified_backup(tmp_path: Path) -> None:
    fixture = MigrationFixture(tmp_path)
    backup_dir = fixture.backup()

    first = fixture.run("forward", backup_dir=backup_dir)
    second = fixture.run("forward", backup_dir=backup_dir)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert first.stdout.strip() == "forward-ok"
    assert second.stdout.strip() == "forward-ok"
    assert fixture.forward_count.read_text(encoding="utf-8").strip() == "2"


def test_production_forward_requires_confirmation_and_trusted_live_boundary(
    tmp_path: Path,
) -> None:
    fixture = MigrationFixture(tmp_path, database="novelwriter")
    backup_dir = fixture.backup()
    wrong = fixture.confirm("novelwriter:20260831:wrong")
    wrong_mode = fixture.confirm("novelwriter:20260831:apply")
    wrong_mode.chmod(0o644)

    missing_confirmation = fixture.run("forward", backup_dir=backup_dir)
    rejected = fixture.run("forward", backup_dir=backup_dir, confirm_file=wrong)
    rejected_mode = fixture.run("forward", backup_dir=backup_dir, confirm_file=wrong_mode)
    wrong_mode.chmod(0o600)
    missing_boundary = fixture.run(
        "forward",
        backup_dir=backup_dir,
        confirm_file=wrong_mode,
    )

    assert missing_confirmation.returncode != 0
    assert "缺少确认令牌文件" in missing_confirmation.stderr
    assert rejected.returncode != 0
    assert "confirmation-token:mismatch" in rejected.stderr
    assert rejected_mode.returncode != 0
    assert "confirmation-file:invalid" in rejected_mode.stderr
    assert missing_boundary.returncode != 0
    assert "必须设置 boundary driver" in missing_boundary.stderr
    assert "novelwriter:20260831:apply" not in fixture.log_path.read_text(
        encoding="utf-8"
    )
    assert _psql_file_execution_count(fixture) == 0


def test_production_forward_rejects_arbitrary_boundary_driver_before_sql(
    tmp_path: Path,
) -> None:
    fixture = MigrationFixture(tmp_path, database="novelwriter")
    backup_dir = fixture.backup()
    confirmation = fixture.confirm("novelwriter:20260831:apply")
    arbitrary = tmp_path / "arbitrary-boundary-driver.sh"
    arbitrary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    arbitrary.chmod(0o755)

    result = fixture.run(
        "forward",
        backup_dir=backup_dir,
        confirm_file=confirmation,
        extra_env={
            "DURABLE_AGENT_BOUNDARY_DRIVER": _posix_path(arbitrary),
            "DURABLE_AGENT_DDL_BOUNDARY": "ddl-forward-1",
        },
    )

    assert result.returncode != 0
    assert "不是当前 trusted control driver" in result.stderr
    assert _psql_file_execution_count(fixture) == 0


def test_production_forward_propagates_stale_boundary_rejection_before_sql(
    tmp_path: Path,
) -> None:
    fixture = MigrationFixture(tmp_path, database="novelwriter")
    backup_dir = fixture.backup()
    confirmation = fixture.confirm("novelwriter:20260831:apply")
    trusted_path = fixture.app_dir / "scripts" / "durable-agent-v2-release.sh"
    trusted_path.write_text(
        "#!/bin/sh\n"
        "[ \"$1\" = consume-live-boundary ] || exit 2\n"
        "echo 'release-boundary:error:live drain 已超过一次性授权窗口' >&2\n"
        "exit 17\n",
        encoding="utf-8",
    )
    trusted_path.chmod(0o755)

    result = fixture.run(
        "forward",
        backup_dir=backup_dir,
        confirm_file=confirmation,
        extra_env={
            "DURABLE_AGENT_BOUNDARY_DRIVER": _posix_path(trusted_path),
            "DURABLE_AGENT_DDL_BOUNDARY": "ddl-forward-1",
        },
    )

    assert result.returncode == 17
    assert "live drain 已超过" in result.stderr
    assert _psql_file_execution_count(fixture) == 0


def test_rollback_is_refused_forever_after_any_v2_fact(tmp_path: Path) -> None:
    fixture = MigrationFixture(tmp_path)
    backup_dir = fixture.backup()
    assert fixture.run("forward", backup_dir=backup_dir).returncode == 0
    fixture.v2_path.write_text("with-v2\n", encoding="utf-8")

    result = fixture.run("rollback", backup_dir=backup_dir)

    assert result.returncode != 0
    assert "DDL rollback 永久禁止" in result.stderr
    log = fixture.log_path.read_text(encoding="utf-8")
    assert "20260831_durable_agent_execution.rollback.sql" not in log


def test_contract_export_and_verify_are_atomic_private_and_credential_safe(
    tmp_path: Path,
) -> None:
    fixture = MigrationFixture(tmp_path)
    fixture.state_path.write_text("migrated\n", encoding="utf-8")
    evidence_dir = tmp_path / "contract-evidence"

    exported = fixture.run("export-contract", evidence_dir=evidence_dir)
    verified = fixture.run("verify-contract", evidence_dir=evidence_dir)

    assert exported.returncode == 0, exported.stderr
    assert verified.returncode == 0, verified.stderr
    expected_fingerprint = json.loads(POST_CONTRACT.read_text(encoding="utf-8"))[
        "fingerprint"
    ]
    assert exported.stdout.strip() == (
        f"contract-export-ok:{evidence_dir}:{expected_fingerprint}"
    )
    assert verified.stdout.strip() == (
        f"contract-verify-ok:{evidence_dir}:{expected_fingerprint}"
    )
    assert {path.name for path in evidence_dir.iterdir()} == {
        "schema-contract.json",
        "schema-only.sql",
        "contract-verification.meta",
        "SHA256SUMS",
    }
    assert evidence_dir.stat().st_mode & 0o077 == 0
    assert all(path.stat().st_mode & 0o077 == 0 for path in evidence_dir.iterdir())
    exported_contract = json.loads(
        (evidence_dir / "schema-contract.json").read_text(encoding="utf-8")
    )
    assert exported_contract["fingerprint"] == expected_fingerprint
    assert exported_contract["source"]["product"] == "PostgreSQL"
    assert "databaseName" not in exported_contract["source"]
    metadata = (evidence_dir / "contract-verification.meta").read_text(
        encoding="utf-8"
    )
    assert "database=novelwriterdev" in metadata
    assert "schemaState=migrated-empty-v2" in metadata
    assert "schemaProfile=full" in metadata
    all_evidence = "".join(
        path.read_text(encoding="utf-8") for path in evidence_dir.iterdir()
    )
    log = fixture.log_path.read_text(encoding="utf-8")
    observables = (
        exported.stdout,
        exported.stderr,
        verified.stdout,
        verified.stderr,
        log,
        all_evidence,
    )
    for observable in observables:
        assert fixture.password not in observable
        assert "%40" not in observable
    assert "writer@127.0.0.1:5432/novelwriterdev" in log
    assert list(fixture.runtime_dir.iterdir()) == []


def test_contract_export_refuses_unmigrated_existing_or_repository_directory(
    tmp_path: Path,
) -> None:
    fixture = MigrationFixture(tmp_path)
    evidence_dir = tmp_path / "contract-evidence"

    unmigrated = fixture.run("export-contract", evidence_dir=evidence_dir)
    assert unmigrated.returncode != 0
    assert not evidence_dir.exists()

    fixture.state_path.write_text("migrated\n", encoding="utf-8")
    evidence_dir.mkdir()
    existing = fixture.run("export-contract", evidence_dir=evidence_dir)
    repository_target = fixture.app_dir / "contract-evidence"
    repository = fixture.run("export-contract", evidence_dir=repository_target)

    assert existing.returncode != 0
    assert repository.returncode != 0
    assert list(evidence_dir.iterdir()) == []
    assert not repository_target.exists()


def test_contract_export_fails_closed_on_guard_mismatch_without_partial_directory(
    tmp_path: Path,
) -> None:
    fixture = MigrationFixture(tmp_path)
    fixture.state_path.write_text("migrated\n", encoding="utf-8")
    evidence_dir = tmp_path / "contract-evidence"

    result = fixture.run(
        "export-contract",
        evidence_dir=evidence_dir,
        extra_env={"FAKE_SCHEMA_GUARD_FINGERPRINT": "0" * 64},
    )

    assert result.returncode != 0
    assert "结构证据构建失败" in result.stderr
    assert not evidence_dir.exists()
    assert not list(tmp_path.glob(".contract-evidence.partial.*"))


def test_contract_verify_rejects_schema_dump_drift_and_extra_files(
    tmp_path: Path,
) -> None:
    fixture = MigrationFixture(tmp_path)
    fixture.state_path.write_text("migrated\n", encoding="utf-8")
    evidence_dir = tmp_path / "contract-evidence"
    assert fixture.run("export-contract", evidence_dir=evidence_dir).returncode == 0

    drifted = fixture.run(
        "verify-contract",
        evidence_dir=evidence_dir,
        extra_env={"FAKE_SCHEMA_DUMP_CONTENT": "schema-drift"},
    )
    assert drifted.returncode != 0
    assert "结构证据复验失败" in drifted.stderr

    (evidence_dir / "unexpected.txt").write_text("unexpected", encoding="utf-8")
    extra_file = fixture.run("verify-contract", evidence_dir=evidence_dir)
    assert extra_file.returncode != 0
    assert "文件集合" in extra_file.stderr or "files:invalid" in extra_file.stderr


@pytest.mark.parametrize(
    ("runtime_profile", "python_profile"),
    [
        ("full", "full"),
        ("without-video-preview", "without_video_preview"),
        ("without-phone-auth", "without_phone_auth"),
        (
            "without-video-preview-and-phone-auth",
            "without_video_preview_and_phone_auth",
        ),
    ],
)
def test_contract_export_projection_matches_existing_python_contract_logic(
    tmp_path: Path,
    runtime_profile: str,
    python_profile: str,
) -> None:
    fixture = MigrationFixture(tmp_path)
    fixture.state_path.write_text("migrated\n", encoding="utf-8")
    post_contract = json.loads(POST_CONTRACT.read_text(encoding="utf-8"))
    expected = project_schema_contract(post_contract, python_profile)  # type: ignore[arg-type]
    evidence_dir = tmp_path / f"evidence-{runtime_profile}"

    result = fixture.run(
        "export-contract",
        evidence_dir=evidence_dir,
        extra_env={
            "FAKE_SCHEMA_PROFILE": runtime_profile,
            "FAKE_SCHEMA_GUARD_FINGERPRINT": expected["fingerprint"],
        },
    )

    assert result.returncode == 0, result.stderr
    actual = json.loads((evidence_dir / "schema-contract.json").read_text(encoding="utf-8"))
    actual_without_source = {key: value for key, value in actual.items() if key != "source"}
    expected_without_source = {
        key: value for key, value in expected.items() if key != "source"
    }
    assert actual_without_source == expected_without_source


def _run_rollout_gate(
    tmp_path: Path,
    *,
    stage: str,
    route_mode: str,
    agent_manifest_fingerprint: str,
    migration_state: str = "migrated-empty-v2",
    active_v2_run_count: int = 0,
    running_core_route_mode: str = "off",
    running_core_v1_fresh_starts: str | None = None,
) -> subprocess.CompletedProcess[str]:
    app_dir = tmp_path / "app"
    bin_dir = tmp_path / "bin"
    (app_dir / "infra").mkdir(parents=True)
    (app_dir / "scripts").mkdir(parents=True)
    (app_dir / "contracts" / "agent-execution").mkdir(parents=True)
    bin_dir.mkdir()
    drain_stage = stage in {
        "initialize-drain-indexes",
        "drain-status",
        "verify-drain",
        "route-off-drain",
        "ddl-rollback",
    }
    v1_fresh_starts = "false" if drain_stage else "true"
    if running_core_v1_fresh_starts is None:
        running_core_v1_fresh_starts = v1_fresh_starts
    (app_dir / "infra" / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    (app_dir / ".env").write_text(
        "DURABLE_AGENT_EXECUTION_SCHEMA_READY=true\n"
        f"DURABLE_AGENT_EXECUTION_ROUTE_MODE={route_mode}\n"
        "DURABLE_AGENT_EXECUTION_USER_ALLOWLIST=user-canary\n"
        "DURABLE_AGENT_EXECUTION_NOVEL_ALLOWLIST=novel-canary\n"
        f"V1_FRESH_AGENT_STARTS_ENABLED={v1_fresh_starts}\n",
        encoding="utf-8",
    )
    shutil.copy2(
        ROOT / "contracts" / "agent-execution" / "manifest.json",
        app_dir / "contracts" / "agent-execution" / "manifest.json",
    )
    _write_executable(
        app_dir / "scripts" / "durable-agent-execution-migration.sh",
        "#!/bin/sh\n"
        'case "$1" in\n'
        "  status) printf '%s\\n' \"$FAKE_MIGRATION_STATE\" ;;\n"
        "  active-v2-count) printf '%s\\n' \"$FAKE_ACTIVE_V2_RUN_COUNT\" ;;\n"
        "  initialize-drain-indexes) printf 'drain-indexes-ready:"
        "v1=initialized:v2=initialized\\n' ;;\n"
        "  drain-status|verify-drain) printf '%s\\n' \"$FAKE_DRAIN_REPORT\" ;;\n"
        "  *) exit 2 ;;\n"
        "esac\n",
    )
    _write_executable(
        app_dir / "scripts" / "verify-durable-agent-v2-image.sh",
        "#!/bin/sh\n"
        '[ "$1" = "agent" ] || exit 2\n'
        "printf 'v2-aware-image-ok:agent:%s\\n' \"$FAKE_AGENT_MANIFEST\"\n",
    )
    _write_executable(
        bin_dir / "docker",
        "#!/bin/sh\n"
        'case " $* " in\n'
        "  *' compose version '*) exit 0 ;;\n"
        "  *' compose '*' ps -q agent-service '*) printf 'agent-container\\n' ;;\n"
        '  *" exec -T core-api /bin/sh -ec "*"V1FreshAgentStartGate.class"*)\n'
        '    [ "$FAKE_RUNNING_CORE_ROUTE_MODE" = "off" ] '
        '&& [ "$FAKE_RUNNING_CORE_V1_FRESH_STARTS" = "false" ] ;;\n'
        '  *" exec -T core-api /bin/sh -ec "*"DURABLE_AGENT_EXECUTION_ROUTE_MODE"*)\n'
        '    [ "$FAKE_RUNNING_CORE_ROUTE_MODE" = "off" ] ;;\n'
        "  *' compose '*' exec -T core-api '*) exit 0 ;;\n"
        "  *' compose '*' exec -T agent-service '*) exit 0 ;;\n"
        "  *' compose '*' exec -T execution-redis '*' INFO persistence '*) "
        "printf 'aof_enabled:1\\naof_last_write_status:ok\\n' ;;\n"
        "  *' compose '*' exec -T execution-redis '*' EXISTS '*) printf '0\\n' ;;\n"
        "  *' compose '*' exec -T execution-redis '*' INFO stats '*) "
        "printf 'evicted_keys:0\\n' ;;\n"
        "  *' redis '*' GET inkforge:runs:drain:index-version '*) "
        "printf '1\\n' ;;\n"
        "  *' execution-redis '*' GET inkforge:executions:drain:index-version '*) "
        "printf '1\\n' ;;\n"
        "  *' inspect --format '*'agent-container'*) "
        "printf 'sha256:%s\\n' \"$FAKE_AGENT_IMAGE_DIGEST\" ;;\n"
        "  *) exit 2 ;;\n"
        "esac\n",
    )
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "APP_DIR": _posix_path(app_dir),
        "DURABLE_AGENT_MIGRATION_ENV_FILE": _posix_path(app_dir / ".env"),
        "FAKE_AGENT_MANIFEST": agent_manifest_fingerprint,
        "FAKE_AGENT_IMAGE_DIGEST": "c" * 64,
        "FAKE_MIGRATION_STATE": migration_state,
        "FAKE_ACTIVE_V2_RUN_COUNT": str(active_v2_run_count),
        "FAKE_DRAIN_REPORT": (
            '{"schema":"inkforge.durable-agent-joint-drain",'
            '"schemaVersion":"2","v1DrainZero":true,"v2Converged":true}'
        ),
        "FAKE_RUNNING_CORE_ROUTE_MODE": running_core_route_mode,
        "FAKE_RUNNING_CORE_V1_FRESH_STARTS": running_core_v1_fresh_starts,
    }
    return subprocess.run(  # noqa: S603 - 仅执行仓库固定脚本与测试夹具
        [POSIX_SHELL, str(ROLLOUT_GATE), stage, "novelwriter"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_rollout_gate_requires_exact_manifest_for_allowlist_and_terminal_runs_for_route_off(
    tmp_path: Path,
) -> None:
    expected = _execution_manifest_fingerprint(
        ROOT / "contracts" / "agent-execution" / "manifest.json"
    )
    same_manifest = _run_rollout_gate(
        tmp_path / "same",
        stage="allowlist",
        route_mode="allowlist",
        agent_manifest_fingerprint=expected,
    )
    older_manifest = _run_rollout_gate(
        tmp_path / "older",
        stage="allowlist",
        route_mode="allowlist",
        agent_manifest_fingerprint="b" * 64,
    )
    route_off_terminal = _run_rollout_gate(
        tmp_path / "route-off-terminal",
        stage="route-off-drain",
        route_mode="off",
        agent_manifest_fingerprint="b" * 64,
        migration_state="migrated-with-v2",
        active_v2_run_count=0,
    )
    route_off_active = _run_rollout_gate(
        tmp_path / "route-off-active",
        stage="route-off-drain",
        route_mode="off",
        agent_manifest_fingerprint="b" * 64,
        migration_state="migrated-with-v2",
        active_v2_run_count=2,
    )
    route_off_runtime_allowlist = _run_rollout_gate(
        tmp_path / "route-off-runtime-allowlist",
        stage="route-off-drain",
        route_mode="off",
        agent_manifest_fingerprint="b" * 64,
        migration_state="migrated-with-v2",
        active_v2_run_count=0,
        running_core_route_mode="allowlist",
    )

    assert same_manifest.returncode == 0, same_manifest.stderr
    assert older_manifest.returncode != 0
    assert "冻结 execution manifest 不一致" in older_manifest.stderr
    assert route_off_terminal.returncode == 0, route_off_terminal.stderr
    assert route_off_active.returncode != 0
    assert "仍有 V2 非终态 Run" in route_off_active.stderr
    assert route_off_runtime_allowlist.returncode != 0
    assert "V1/V2 新建入口同时关闭" in route_off_runtime_allowlist.stderr


def test_rollout_gate_exposes_separate_drain_status_and_verify_actions(
    tmp_path: Path,
) -> None:
    expected = _execution_manifest_fingerprint(
        ROOT / "contracts" / "agent-execution" / "manifest.json"
    )
    status_while_allowlist = _run_rollout_gate(
        tmp_path / "status",
        stage="drain-status",
        route_mode="allowlist",
        agent_manifest_fingerprint=expected,
        migration_state="migrated-with-v2",
    )
    verified_off = _run_rollout_gate(
        tmp_path / "verify-off",
        stage="verify-drain",
        route_mode="off",
        agent_manifest_fingerprint=expected,
        migration_state="migrated-with-v2",
    )
    rejected_allowlist = _run_rollout_gate(
        tmp_path / "verify-allowlist",
        stage="verify-drain",
        route_mode="allowlist",
        agent_manifest_fingerprint=expected,
        migration_state="migrated-with-v2",
    )

    assert status_while_allowlist.returncode != 0
    assert "V1 fresh start" in status_while_allowlist.stderr
    assert verified_off.returncode == 0, verified_off.stderr
    assert json.loads(verified_off.stdout)["v2Converged"] is True
    assert rejected_allowlist.returncode != 0
    assert "schemaReady/route" in rejected_allowlist.stderr


def test_rollout_gate_freezes_the_staged_route_matrix() -> None:
    source = ROLLOUT_GATE.read_text(encoding="utf-8")

    for stage in (
        "pre-contract",
        "post-contract-route-off",
        "schema-ready-route-off",
        "initialize-drain-indexes",
        "allowlist",
        "route-off-drain",
        "ddl-rollback",
    ):
        assert stage in source
    assert "schemaReady=false" not in source  # 配置使用正式环境变量名，不靠自然语言解析。
    assert "DURABLE_AGENT_EXECUTION_SCHEMA_READY" in source
    assert "DURABLE_AGENT_EXECUTION_ROUTE_MODE" in source
    assert "V1_FRESH_AGENT_STARTS_ENABLED" in source
    assert "inkforge-schema-guard" in source
    assert "restore:quarantine" in source
    assert "evicted_keys" in source
    assert "verify-durable-agent-v2-image.sh" in source
    assert "require_release_execution_manifest" in source
    assert "require_route_off_execution_manifest" in source
    assert "current_agent_manifest_fingerprint" in source


def test_postgres_restore_has_named_quarantine_step_but_no_restore_command() -> None:
    source = POSTGRES_QUARANTINE.read_text(encoding="utf-8")

    for required in (
        "postgresRestoreRequiresExecutionQuarantine=true",
        "inkforge:executions:restore:quarantine",
        "WAITAOF 1 0 5000",
        '[ "$local_aof_ack" = "1" ]',
        "PREPARE_POSTGRES_RESTORE_QUARANTINE",
        "DURABLE_AGENT_EXECUTION_ROUTE_MODE",
        "EXECUTION_DISPATCH_STOPPED",
        "CORE_API_CONTAINER",
        "AGENT_SERVICE_CONTAINER",
        "com.docker.compose.project.config_files",
        "com.docker.compose.project.working_dir",
        "docker ps -a -q --no-trunc",
        "com.docker.compose.service",
        '"$expected_status|$expected_running|false|false"',
        "本脚本不执行数据库覆盖恢复",
    ):
        assert required in source
    assert "pg_restore" not in source
    assert "psql" not in source
    assert source.count("require_authoritative_compose_quiescence") == 3


@pytest.mark.parametrize(
    (
        "waitaof_ack",
        "core_state",
        "agent_state",
        "core_instances",
        "core_project",
        "expected_success",
        "expected_error",
    ),
    [
        pytest.param(
            "1",
            "exited|false|false|false",
            "exited|false|false|false",
            "core-api-test",
            "inkforge",
            True,
            "",
            id="unique-stopped-in-authoritative-project",
        ),
        (
            "0",
            "exited|false|false|false",
            "exited|false|false|false",
            "core-api-test",
            "inkforge",
            False,
            "禁止恢复数据库",
        ),
        (
            "1",
            "running|true|false|false",
            "exited|false|false|false",
            "core-api-test",
            "inkforge",
            False,
            "状态不满足恢复屏障",
        ),
        (
            "1",
            "exited|false|false|false",
            "running|true|false|false",
            "core-api-test",
            "inkforge",
            False,
            "状态不满足恢复屏障",
        ),
        pytest.param(
            "1",
            "exited|false|false|false",
            "exited|false|false|false",
            "core-api-test,core-api-current-running",
            "inkforge",
            False,
            "恰有一个且无残留实例",
            id="old-stopped-plus-current-running",
        ),
        pytest.param(
            "1",
            "exited|false|false|false",
            "exited|false|false|false",
            "core-api-test",
            "other-project",
            False,
            "project/config 身份不一致",
            id="cross-project-container",
        ),
    ],
)
def test_postgres_restore_quarantine_requires_quiesce_and_local_waitaof_one(
    tmp_path: Path,
    waitaof_ack: str,
    core_state: str,
    agent_state: str,
    core_instances: str,
    core_project: str,
    expected_success: bool,
    expected_error: str,
) -> None:
    backup_dir = tmp_path / "backup"
    bin_dir = tmp_path / "bin"
    backup_dir.mkdir()
    bin_dir.mkdir()
    database_dump = backup_dir / "database.dump"
    database_dump.write_bytes(b"postgres-backup-fixture")
    database_sha = hashlib.sha256(database_dump.read_bytes()).hexdigest()
    (backup_dir / "recovery-boundary.meta").write_text(
        "postgresRestoreRequiresExecutionQuarantine=true\n", encoding="utf-8"
    )
    sha256sum = shutil.which("sha256sum")
    assert sha256sum is not None
    with (backup_dir / "SHA256SUMS").open("w", encoding="utf-8") as sums:
        subprocess.run(  # noqa: S603 - 仅执行本机已解析的 sha256sum
            [sha256sum, "database.dump", "recovery-boundary.meta"],
            cwd=backup_dir,
            check=True,
            text=True,
            stdout=sums,
        )
    epoch = "postgres-restore-test"
    confirm = tmp_path / "restore.confirm"
    confirm.write_text(
        f"PREPARE_POSTGRES_RESTORE_QUARANTINE:{epoch}:{database_sha}\n",
        encoding="utf-8",
    )
    confirm.chmod(0o600)
    docker_log = tmp_path / "docker.log"
    _write_executable(
        bin_dir / "docker",
        "#!/bin/sh\n"
        'printf \'%s\\n\' "$*" >> "$FAKE_DOCKER_LOG"\n'
        'case " $* " in\n'
        "  *' ps -a -q --no-trunc '*'com.docker.compose.service=execution-redis'*) "
        "printf 'execution-redis-test\\n' ;;\n"
        "  *' ps -a -q --no-trunc '*'com.docker.compose.service=core-api'*) "
        "printf '%s\\n' \"$FAKE_CORE_INSTANCES\" | tr ',' '\\n' ;;\n"
        "  *' ps -a -q --no-trunc '*'com.docker.compose.service=agent-service'*) "
        "printf 'agent-service-test\\n' ;;\n"
        "  *' inspect '*'execution-redis-test'*) "
        "printf 'inkforge|/srv/inkforge/infra/compose.yaml|/srv/inkforge|"
        "execution-redis|running|true|false|false\\n' ;;\n"
        "  *' inspect '*'core-api-test'*) "
        "printf '%s|/srv/inkforge/infra/compose.yaml|/srv/inkforge|core-api|%s\\n' "
        '"$FAKE_CORE_PROJECT" "$FAKE_CORE_STATE" ;;\n'
        "  *' inspect '*'core-api-current-running'*) "
        "printf 'inkforge|/srv/inkforge/infra/compose.yaml|/srv/inkforge|"
        "core-api|running|true|false|false\\n' ;;\n"
        "  *' inspect '*'agent-service-test'*) "
        "printf 'inkforge|/srv/inkforge/infra/compose.yaml|/srv/inkforge|agent-service|%s\\n' "
        '"$FAKE_AGENT_STATE" ;;\n'
        "  *' INFO persistence '*) printf 'aof_enabled:1\\naof_last_write_status:ok\\n' ;;\n"
        "  *' EVAL '*) printf '1\\n' ;;\n"
        "  *' WAITAOF '*) printf '%s\\n0\\n' \"$FAKE_WAITAOF_ACK\" ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n",
    )
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "POSTGRES_BACKUP_DIR": _posix_path(backup_dir),
        "EXECUTION_REDIS_CONTAINER": "execution-redis-test",
        "RESTORE_EPOCH": epoch,
        "POSTGRES_RESTORE_CONFIRM_FILE": _posix_path(confirm),
        "DURABLE_AGENT_EXECUTION_ROUTE_MODE": "off",
        "EXECUTION_DISPATCH_STOPPED": "true",
        "CORE_API_CONTAINER": "core-api-test",
        "AGENT_SERVICE_CONTAINER": "agent-service-test",
        "FAKE_WAITAOF_ACK": waitaof_ack,
        "FAKE_CORE_STATE": core_state,
        "FAKE_AGENT_STATE": agent_state,
        "FAKE_CORE_INSTANCES": core_instances,
        "FAKE_CORE_PROJECT": core_project,
        "FAKE_DOCKER_LOG": _posix_path(docker_log),
    }

    result = subprocess.run(  # noqa: S603 - 仅执行仓库固定脚本与测试夹具
        [POSIX_SHELL, str(POSTGRES_QUARANTINE)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert (result.returncode == 0) is expected_success
    log = docker_log.read_text(encoding="utf-8")
    if expected_error:
        assert expected_error in result.stderr
    pre_marker_errors = {
        "状态不满足恢复屏障",
        "恰有一个且无残留实例",
        "project/config 身份不一致",
    }
    if expected_error in pre_marker_errors:
        assert " EVAL " not in f" {log} "
    elif not expected_success:
        assert " EVAL " in f" {log} "
    else:
        assert "quiesce + execution quarantine 屏障已耐久生效" in result.stdout
        assert " EVAL " in f" {log} "


@pytest.mark.parametrize(
    ("route_mode", "dispatch_stopped", "expected_error"),
    [
        ("allowlist", "true", "route-off"),
        ("off", "false", "停止新的 execution dispatch"),
    ],
)
def test_postgres_restore_quarantine_requires_route_off_and_stopped_dispatch(
    tmp_path: Path,
    route_mode: str,
    dispatch_stopped: str,
    expected_error: str,
) -> None:
    env = {
        **os.environ,
        "POSTGRES_BACKUP_DIR": _posix_path(tmp_path),
        "EXECUTION_REDIS_CONTAINER": "execution-redis-test",
        "RESTORE_EPOCH": "postgres-restore-test",
        "POSTGRES_RESTORE_CONFIRM_FILE": _posix_path(tmp_path / "confirm"),
        "DURABLE_AGENT_EXECUTION_ROUTE_MODE": route_mode,
        "EXECUTION_DISPATCH_STOPPED": dispatch_stopped,
        "CORE_API_CONTAINER": "core-api-test",
        "AGENT_SERVICE_CONTAINER": "agent-service-test",
    }

    result = subprocess.run(  # noqa: S603 - 仅执行仓库固定脚本
        [POSIX_SHELL, str(POSTGRES_QUARANTINE)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert expected_error in result.stderr


def test_image_verifier_runs_without_network_secrets_or_volumes() -> None:
    source = IMAGE_VERIFIER.read_text(encoding="utf-8")

    assert source.count("--network none") == 2
    assert source.count("--read-only") == 2
    assert "--env" not in source
    assert "--mount" not in source
    assert "WorkflowsController.class" in source
    assert "load_execution_registry" in source
    assert "manifest_fingerprint" in source


def test_agent_image_verifier_requires_exact_offline_manifest_fingerprint(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker_log = tmp_path / "docker.log"
    actual = "a" * 64
    _write_executable(
        bin_dir / "docker",
        "#!/bin/sh\n"
        'printf \'%s\\n\' "$*" >> "$FAKE_DOCKER_LOG"\n'
        'case " $* " in\n'
        "  *' image inspect '*) exit 0 ;;\n"
        "  *' run '*) printf '%s\\n' \"$FAKE_MANIFEST_FINGERPRINT\" ;;\n"
        "  *) exit 2 ;;\n"
        "esac\n",
    )
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "FAKE_DOCKER_LOG": _posix_path(docker_log),
        "FAKE_MANIFEST_FINGERPRINT": actual,
    }

    accepted = subprocess.run(  # noqa: S603 - 仅执行仓库固定脚本与测试夹具
        [
            POSIX_SHELL,
            str(IMAGE_VERIFIER),
            "agent",
            "inkforge-agent-service:fixture",
            actual,
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    rejected = subprocess.run(  # noqa: S603 - 仅执行仓库固定脚本与测试夹具
        [
            POSIX_SHELL,
            str(IMAGE_VERIFIER),
            "agent",
            "inkforge-agent-service:fixture",
            "b" * 64,
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert accepted.returncode == 0, accepted.stderr
    assert accepted.stdout.strip() == f"v2-aware-image-ok:agent:{actual}"
    assert rejected.returncode != 0
    assert "与发布预期不一致" in rejected.stderr
    run_lines = [
        line for line in docker_log.read_text(encoding="utf-8").splitlines() if "run " in line
    ]
    assert len(run_lines) == 2
    for line in run_lines:
        assert "--network none" in line
        assert "--read-only" in line
        assert "--cap-drop ALL" in line
        assert "--mount" not in line
        assert "--env" not in line
        assert "load_execution_registry" in line


def test_status_query_recognizes_real_postgres14_pre_post_and_partial_shapes(
    isolated_postgres: tuple[str, str],
    tmp_path: Path,
) -> None:
    docker, container = isolated_postgres
    source = HELPER.read_text(encoding="utf-8")
    structural_start = source.index("WITH migration_shape AS (")
    structural_end = source.index("\nSQL", structural_start)
    structural_query = source[structural_start:structural_end].replace(
        ":'expected_database'", "'novelwriterdev'"
    )
    v2_start = source.index("SELECT CASE WHEN\n  pg_catalog.current_database()", structural_end)
    v2_end = source.index("\nSQL", v2_start)
    v2_query = source[v2_start:v2_end].replace(":'expected_database'", "'novelwriterdev'")

    _psql(docker, container, "DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    _psql(docker, container, BASE_SCHEMA.read_text(encoding="utf-8"))
    assert _scalar(docker, container, structural_query) == "unmigrated"
    _psql(docker, container, FORWARD.read_text(encoding="utf-8"))
    assert _scalar(docker, container, structural_query) == "migrated"
    assert _scalar(docker, container, v2_query) == "empty-v2"

    drain_start = source.index("WITH\nobserved AS MATERIALIZED (")
    drain_end = source.index("\nCOMMIT;", drain_start)
    drain_query = source[drain_start:drain_end].replace(
        ":'expected_database'", "'novelwriterdev'"
    )
    empty_drain = json.loads(_scalar(docker, container, drain_query))
    assert all(metric == [] for metric in empty_drain["metrics"].values())
    _psql(
        docker,
        container,
        """
        INSERT INTO public."User" (
          id, username, "passwordHash", "creditBalanceMicros", "createdAt", "updatedAt"
        ) VALUES ('drain-user', 'drain-user', 'test', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
        INSERT INTO public."Novel" (id, name, "userId", "createdAt", "updatedAt")
        VALUES ('drain-novel', 'drain', 'drain-user', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
        INSERT INTO public."Chapter" (
          id, "novelId", title, content, "order", status, "createdAt", "updatedAt"
        ) VALUES (
          'drain-chapter', 'drain-novel', '第一章', '', 1, 'drafting',
          CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        );
        INSERT INTO public."WritingTask" (
          id, "novelId", "chapterId", "targetWordCount", "selectedAgents",
          phase, "createdAt", "updatedAt"
        ) VALUES (
          'drain-task', 'drain-novel', 'drain-chapter', 1000, '编辑',
          'awaiting_user_review', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        );
        INSERT INTO public."ReviewArtifact" (
          id, "novelId", "chapterId", "taskId", kind, status,
          "payloadJson", revision, "createdAt", "updatedAt"
        ) VALUES (
          'drain-artifact', 'drain-novel', 'drain-chapter', 'drain-task',
          'chapter_draft', 'awaiting_user', '{}', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        );
        """,
    )
    nonzero_drain = json.loads(_scalar(docker, container, drain_query))
    assert len(nonzero_drain["metrics"]["v1WritingTasksAwaitingUser"]) == 1
    assert len(nonzero_drain["metrics"]["v1ArtifactsAwaitingUser"]) == 1

    # helper 的凭据解析、只读状态/来源查询和 schema-only 导出仍走固定 shell 入口；
    # 仅 Compose/Core 探针由夹具代替，所有 PostgreSQL catalog 与 pg_dump 都来自真实 PG14。
    fixture = MigrationFixture(tmp_path / "real-helper")
    docker_command = shlex.quote(docker)
    container_name = shlex.quote(container)
    _write_executable(
        fixture.bin_dir / "psql",
        "#!/bin/sh\n"
        "printf 'psql %s\\n' \"$*\" >> \"$MIGRATION_LOG\"\n"
        "cp \"$PGPASSFILE\" \"$PGPASS_CAPTURE\"\n"
        f"exec {docker_command} exec -i {container_name} psql -X "
        "-v ON_ERROR_STOP=1 -v expected_database=novelwriterdev "
        "-Atq -U postgres -d novelwriterdev\n",
    )
    _write_executable(
        fixture.bin_dir / "pg_dump",
        "#!/bin/sh\n"
        "output=''\n"
        "previous=''\n"
        "for argument in \"$@\"; do\n"
        "  [ \"$previous\" != '--file' ] || output=$argument\n"
        "  case \"$argument\" in --file=*) output=${argument#--file=};; esac\n"
        "  previous=$argument\n"
        "done\n"
        "[ -n \"$output\" ] || exit 43\n"
        f"exec {docker_command} exec {container_name} pg_dump -U postgres "
        "-d novelwriterdev --schema-only --no-owner --no-acl --format=plain "
        "> \"$output\"\n",
    )
    expected_fingerprint = json.loads(POST_CONTRACT.read_text(encoding="utf-8"))[
        "fingerprint"
    ]
    _write_executable(
        fixture.bin_dir / "docker",
        "#!/bin/sh\n"
        "printf 'docker %s\\n' \"$*\" >> \"$MIGRATION_LOG\"\n"
        "case \" $* \" in\n"
        "  *' compose version '*) exit 0 ;;\n"
        "  *' /usr/local/bin/inkforge-schema-guard '*) "
        f"printf '%s\\n' '{expected_fingerprint}' ;;\n"
        "  *'INKFORGE_EXPECTED_DATABASE='*) printf '%s\\n' full ;;\n"
        "  *' compose '*' exec -T core-api '*) exit 0 ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n",
    )
    evidence_dir = tmp_path / "real-pg14-contract-evidence"
    exported = fixture.run("export-contract", evidence_dir=evidence_dir)
    verified = fixture.run("verify-contract", evidence_dir=evidence_dir)
    assert exported.returncode == 0, exported.stderr
    assert verified.returncode == 0, verified.stderr
    assert exported.stdout.strip().endswith(f":{expected_fingerprint}")
    assert verified.stdout.strip().endswith(f":{expected_fingerprint}")
    assert "CREATE TABLE public.\"WorkflowEvidenceBundle\"" in (
        evidence_dir / "schema-only.sql"
    ).read_text(encoding="utf-8")
    assert fixture.password not in fixture.log_path.read_text(encoding="utf-8")

    _psql(
        docker,
        container,
        'DROP TRIGGER "WorkflowEvent_immutable_trigger" ON "WorkflowEvent";',
    )
    assert _scalar(docker, container, structural_query) == "partial"


def test_real_postgres14_concurrent_fresh_fact_invalidates_two_snapshot_window(
    isolated_postgres: tuple[str, str],
    tmp_path: Path,
) -> None:
    docker, container = isolated_postgres
    source = HELPER.read_text(encoding="utf-8")
    drain_start = source.index("WITH\nobserved AS MATERIALIZED (")
    drain_end = source.index("\nCOMMIT;", drain_start)
    drain_query = source[drain_start:drain_end].replace(
        ":'expected_database'", "'novelwriterdev'"
    )
    _psql(docker, container, "DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    _psql(docker, container, BASE_SCHEMA.read_text(encoding="utf-8"))
    _psql(docker, container, FORWARD.read_text(encoding="utf-8"))
    postgres_before = json.loads(_scalar(docker, container, drain_query))

    _psql(
        docker,
        container,
        """
        INSERT INTO public."User" (
          id, username, "passwordHash", "creditBalanceMicros", "createdAt", "updatedAt"
        ) VALUES ('race-user', 'race-user', 'test', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
        INSERT INTO public."Novel" (id, name, "userId", "createdAt", "updatedAt")
        VALUES ('race-novel', 'race', 'race-user', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
        INSERT INTO public."Chapter" (
          id, "novelId", title, content, "order", status, "createdAt", "updatedAt"
        ) VALUES (
          'race-chapter', 'race-novel', '第一章', '', 1, 'drafting',
          CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        );
        INSERT INTO public."WritingTask" (
          id, "novelId", "chapterId", "targetWordCount", "selectedAgents",
          phase, "createdAt", "updatedAt"
        ) VALUES (
          'race-task', 'race-novel', 'race-chapter', 1000, '写作',
          'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        );
        """,
    )
    postgres_after = json.loads(_scalar(docker, container, drain_query))

    source_dir = tmp_path / "pg-race"
    source_dir.mkdir()
    redis_sources = _drain_source_files(source_dir)
    before_path = source_dir / "pg-before.json"
    after_path = source_dir / "pg-after.json"
    before_path.write_text(json.dumps(postgres_before), encoding="utf-8")
    after_path.write_text(json.dumps(postgres_after), encoding="utf-8")
    runtime_before = _drain_runtime_file(source_dir / "runtime-before.json")
    runtime_after = _drain_runtime_file(source_dir / "runtime-after.json")

    result = subprocess.run(  # noqa: S603 - 固定仓库脚本与隔离 PG14 证据
        [
            sys.executable,
            str(ROOT / "scripts/durable_agent_joint_drain.py"),
            "build",
            "--database",
            "novelwriterdev",
            "--runtime-before",
            str(runtime_before),
            "--postgres-before",
            str(before_path),
            "--ordinary-redis",
            redis_sources["FAKE_V1_REDIS_FILE"],
            "--execution-redis",
            redis_sources["FAKE_V2_REDIS_FILE"],
            "--postgres-after",
            str(after_path),
            "--runtime-after",
            str(runtime_after),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert result.stdout == ""
    assert "精确阻断集合发生变化" in result.stderr
