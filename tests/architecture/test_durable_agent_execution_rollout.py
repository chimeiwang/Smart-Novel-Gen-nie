from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

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
  *'WorkflowEvidenceBundle'*'workflowRunId'*) sed -n '1p' "$V2_STATE" ;;
  *'status::text NOT IN'*) printf '%s\n' "${FAKE_ACTIVE_V2_RUN_COUNT:-0}" ;;
  *) printf 'unexpected schema query\n' >&2; exit 42 ;;
esac
""",
        )
        _write_executable(
            self.bin_dir / "pg_dump",
            "#!/bin/sh\n"
            "output=''\n"
            "previous=''\n"
            'for argument in "$@"; do\n'
            "  [ \"$previous\" != '--file' ] || output=$argument\n"
            '  case "$argument" in --file=*) output=${argument#--file=};; esac\n'
            "  previous=$argument\n"
            "done\n"
            '[ -n "$output" ] || exit 43\n'
            "printf 'database-dump-fixture' > \"$output\"\n",
        )
        _write_executable(self.bin_dir / "pg_restore", "#!/bin/sh\nexit 0\n")
        _write_executable(
            self.bin_dir / "docker",
            r"""#!/bin/sh
printf 'docker %s\n' "$*" >> "$MIGRATION_LOG"
case " $* " in
  *' compose version '*) exit 0 ;;
  *' compose '*' ps -q execution-redis '*) printf 'abc123\n' ;;
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
            "TARGET_DATABASE": self.database,
        }
        if backup_dir is not None:
            env["DURABLE_AGENT_MIGRATION_BACKUP_DIR"] = _posix_path(backup_dir)
        if confirm_file is not None:
            env["DURABLE_AGENT_MIGRATION_CONFIRM_FILE"] = _posix_path(confirm_file)
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
    ):
        assert required in source
    assert "source .env" not in source
    assert ". $env_file" not in source
    assert 'psql "$raw_database_url"' not in source
    assert 'pg_dump "$raw_database_url"' not in source
    assert 'PGOPTIONS="$pg_options -c inkforge' not in source
    assert "生产 GUC 只进入 0600 临时 SQL" in source


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


def test_production_forward_requires_exact_0600_confirmation(tmp_path: Path) -> None:
    fixture = MigrationFixture(tmp_path, database="novelwriter")
    backup_dir = fixture.backup()
    wrong = fixture.confirm("novelwriter:20260831:wrong")
    wrong_mode = fixture.confirm("novelwriter:20260831:apply")
    wrong_mode.chmod(0o644)

    rejected = fixture.run("forward", backup_dir=backup_dir, confirm_file=wrong)
    rejected_mode = fixture.run("forward", backup_dir=backup_dir, confirm_file=wrong_mode)
    wrong_mode.chmod(0o600)
    accepted = fixture.run(
        "forward",
        backup_dir=backup_dir,
        confirm_file=wrong_mode,
    )

    assert rejected.returncode != 0
    assert "confirmation-token:mismatch" in rejected.stderr
    assert rejected_mode.returncode != 0
    assert "confirmation-file:invalid" in rejected_mode.stderr
    assert accepted.returncode == 0, accepted.stderr
    assert "novelwriter:20260831:apply" not in fixture.log_path.read_text(encoding="utf-8")


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


def _run_rollout_gate(
    tmp_path: Path,
    *,
    stage: str,
    route_mode: str,
    agent_manifest_fingerprint: str,
    migration_state: str = "migrated-empty-v2",
    active_v2_run_count: int = 0,
    running_core_route_mode: str = "off",
) -> subprocess.CompletedProcess[str]:
    app_dir = tmp_path / "app"
    bin_dir = tmp_path / "bin"
    (app_dir / "infra").mkdir(parents=True)
    (app_dir / "scripts").mkdir(parents=True)
    (app_dir / "contracts" / "agent-execution").mkdir(parents=True)
    bin_dir.mkdir()
    (app_dir / "infra" / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    (app_dir / ".env").write_text(
        "DURABLE_AGENT_EXECUTION_SCHEMA_READY=true\n"
        f"DURABLE_AGENT_EXECUTION_ROUTE_MODE={route_mode}\n"
        "DURABLE_AGENT_EXECUTION_USER_ALLOWLIST=user-canary\n"
        "DURABLE_AGENT_EXECUTION_NOVEL_ALLOWLIST=novel-canary\n",
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
        '  *" exec -T core-api /bin/sh -ec "*"DURABLE_AGENT_EXECUTION_ROUTE_MODE"*)\n'
        '    [ "$FAKE_RUNNING_CORE_ROUTE_MODE" = "off" ] ;;\n'
        "  *' compose '*' exec -T core-api '*) exit 0 ;;\n"
        "  *' compose '*' exec -T agent-service '*) exit 0 ;;\n"
        "  *' compose '*' exec -T execution-redis '*' INFO persistence '*) "
        "printf 'aof_enabled:1\\naof_last_write_status:ok\\n' ;;\n"
        "  *' compose '*' exec -T execution-redis '*' EXISTS '*) printf '0\\n' ;;\n"
        "  *' compose '*' exec -T execution-redis '*' INFO stats '*) "
        "printf 'evicted_keys:0\\n' ;;\n"
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
        "FAKE_RUNNING_CORE_ROUTE_MODE": running_core_route_mode,
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
    assert "当前运行 Core 未精确证明 route=off" in route_off_runtime_allowlist.stderr


def test_rollout_gate_freezes_the_staged_route_matrix() -> None:
    source = ROLLOUT_GATE.read_text(encoding="utf-8")

    for stage in (
        "pre-contract",
        "post-contract-route-off",
        "schema-ready-route-off",
        "allowlist",
        "route-off-drain",
        "ddl-rollback",
    ):
        assert stage in source
    assert "schemaReady=false" not in source  # 配置使用正式环境变量名，不靠自然语言解析。
    assert "DURABLE_AGENT_EXECUTION_SCHEMA_READY" in source
    assert "DURABLE_AGENT_EXECUTION_ROUTE_MODE" in source
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

    _psql(docker, container, BASE_SCHEMA.read_text(encoding="utf-8"))
    assert _scalar(docker, container, structural_query) == "unmigrated"
    _psql(docker, container, FORWARD.read_text(encoding="utf-8"))
    assert _scalar(docker, container, structural_query) == "migrated"
    assert _scalar(docker, container, v2_query) == "empty-v2"

    _psql(
        docker,
        container,
        'DROP TRIGGER "WorkflowEvent_immutable_trigger" ON "WorkflowEvent";',
    )
    assert _scalar(docker, container, structural_query) == "partial"
