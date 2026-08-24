from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
GIT_ATTRIBUTES = ROOT / ".gitattributes"
DEV_UP = ROOT / "scripts" / "migrations" / "20260823_token_usage_details.sql"
PRODUCTION_UP = (
    ROOT / "scripts" / "migrations" / "20260823_token_usage_details.production.sql"
)
ROLLBACK = (
    ROOT / "scripts" / "migrations" / "rollback_20260823_token_usage_details.sql"
)
HELPER = ROOT / "scripts" / "token-usage-production-migration.sh"
DEPLOY = ROOT / "scripts" / "deploy-production.sh"
POSIX_SHELL = shutil.which("sh") or str(
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "bin" / "sh.exe"
)


def _posix_path(path: Path) -> str:
    resolved = path.resolve()
    if os.name != "nt":
        return resolved.as_posix()
    return f"/{resolved.drive[0].lower()}{resolved.as_posix()[2:]}"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _run_helper(
    tmp_path: Path, database_url: str, *, action: str = "status"
) -> tuple[subprocess.CompletedProcess[str], str, str, list[Path]]:
    app_dir = tmp_path / "app"
    migration_dir = app_dir / "scripts" / "migrations"
    bin_dir = tmp_path / "bin"
    runtime_dir = tmp_path / "runtime"
    migration_dir.mkdir(parents=True)
    bin_dir.mkdir()
    runtime_dir.mkdir()
    (app_dir / ".env").write_text(f"DATABASE_URL={database_url}\n", encoding="utf-8")
    shutil.copy2(PRODUCTION_UP, migration_dir / PRODUCTION_UP.name)
    shutil.copy2(ROLLBACK, migration_dir / ROLLBACK.name)

    command_log = tmp_path / "command.log"
    pgpass_capture = tmp_path / "pgpass.capture"
    python_path = _posix_path(Path(sys.executable))
    _write_executable(bin_dir / "python3", f'#!/bin/sh\nexec "{python_path}" "$@"\n')
    _write_executable(
        bin_dir / "psql",
        "#!/bin/sh\n"
        "printf 'psql %s\\n' \"$*\" >> \"$HELPER_COMMAND_LOG\"\n"
        "cp \"$PGPASSFILE\" \"$HELPER_PGPASS_CAPTURE\"\n"
        "case \"$*\" in\n"
        "  *'SELECT CASE WHEN count(DISTINCT relation.relowner)'*) "
        "printf 'video_owner\\n'; exit 0 ;;\n"
        "esac\n"
        "query=$(sed -n '1,$p')\n"
        "case \"$query\" in\n"
        "  *'CREATE TEMP TABLE token_usage_details_constraint_contract'*"
        "'expected_constraints'*'pg_get_constraintdef(actual_constraint.oid)'*"
        "'constraint_state.constraints_valid'*) "
        "printf '%s\\n' \"${FAKE_HELPER_SCHEMA_STATE:-migrated}\"; exit 0 ;;\n"
        "  *'has_table_privilege(current_user'*'has_sequence_privilege(current_user'*) "
        "printf '%s\\n' 'schema-usage:true' 'table-count:69' "
        "'table-select-missing:25' 'table-missing-owner-count:1' "
        "'table-missing-owner-membership:false' 'table:VideoProject:owner=false' "
        "'sequence-count:0' 'sequence-select-missing:0'; exit 0 ;;\n"
        "  *) printf 'schema query contract mismatch\\n' >&2; exit 42 ;;\n"
        "esac\n",
    )
    for command_name in ("pg_dump", "pg_restore", "sha256sum"):
        _write_executable(bin_dir / command_name, "#!/bin/sh\nexit 0\n")
    _write_executable(bin_dir / "timeout", "#!/bin/sh\nshift\nexec \"$@\"\n")
    env = {
        **os.environ,
        "APP_DIR": _posix_path(app_dir),
        "TMPDIR": _posix_path(runtime_dir),
        "HELPER_COMMAND_LOG": _posix_path(command_log),
        "HELPER_PGPASS_CAPTURE": _posix_path(pgpass_capture),
    }
    result = subprocess.run(  # noqa: S603 - 仅执行仓库固定脚本和测试夹具
        [
            POSIX_SHELL,
            "-c",
            'PATH="$1:$PATH"; export PATH; exec /bin/sh "$2" "$3"',
            "migration-helper-test",
            _posix_path(bin_dir),
            _posix_path(HELPER),
            action,
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )
    log = command_log.read_text(encoding="utf-8") if command_log.exists() else ""
    pgpass = pgpass_capture.read_text(encoding="utf-8") if pgpass_capture.exists() else ""
    return result, log, pgpass, list(runtime_dir.iterdir())


def test_production_forward_is_fixed_and_only_changes_the_database_guard() -> None:
    dev = DEV_UP.read_text(encoding="utf-8")
    production = PRODUCTION_UP.read_text(encoding="utf-8")

    assert "current_database() <> 'novelwriter'" in production
    assert "novelwriterdev" not in production
    normalized = production.replace("novelwriter", "novelwriterdev")
    assert normalized == dev


def test_shell_and_migration_line_endings_are_pinned_to_lf() -> None:
    source = GIT_ATTRIBUTES.read_text(encoding="utf-8")

    assert "*.sh text eol=lf" in source
    assert "scripts/migrations/*.sql text eol=lf" in source


def test_fixed_rollback_validates_before_dropping_without_cascade() -> None:
    source = ROLLBACK.read_text(encoding="utf-8")

    assert "current_database() <> 'novelwriter'" in source
    for name in (
        "TokenUsage_token_details_nonnegative_check",
        "TokenUsage_prompt_cache_details_check",
        "TokenUsage_reasoning_details_check",
        "promptCacheMissTokens",
        "reasoningTokens",
    ):
        assert name in source
    assert "pg_get_constraintdef" in source
    assert 'WHERE "promptCacheMissTokens" IS NOT NULL' in source
    assert 'OR "reasoningTokens" IS NOT NULL' in source
    assert source.index("VALIDATE CONSTRAINT") < source.index("DROP CONSTRAINT")
    assert source.index("DROP CONSTRAINT") < source.index("DROP COLUMN")
    assert "DROP CONSTRAINT IF EXISTS" not in source
    assert "DROP COLUMN IF EXISTS" not in source
    assert "CASCADE" not in source


def test_production_helper_keeps_password_out_of_argv_and_pins_artifacts() -> None:
    source = HELPER.read_text(encoding="utf-8")

    for value in (
        'env_file="$app_dir/.env"',
        'parts.path != "/novelwriter"',
        'hostname != "host.docker.internal"',
        'command_hostname = "127.0.0.1"',
        "PGPASSFILE",
        "umask 077",
        "chmod 600",
        "BACKUP_ROOT=\"$app_dir/.token-usage-production-backups\"",
        "pg_restore --list",
        "sha256sum --check",
        "20260823_token_usage_details.production.sql",
        "rollback_20260823_token_usage_details.sql",
        "schema-state:partial",
        "CREATE TEMP TABLE token_usage_details_constraint_contract",
        "expected_constraints",
    ):
        assert value in source
    assert "source .env" not in source
    assert ". $env_file" not in source
    assert 'psql "$raw_database_url"' not in source
    assert 'pg_dump "$raw_database_url"' not in source
    assert "print(value)" not in source

    for path, variable in (
        (PRODUCTION_UP, "forward_sha"),
        (ROLLBACK, "rollback_sha"),
    ):
        expected = re.search(rf'{variable}="([A-F0-9]{{64}})"', source)
        assert expected is not None
        normalized = path.read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(normalized).hexdigest().upper() == expected.group(1)


def test_deploy_orders_conditional_migration_before_version_switch() -> None:
    source = DEPLOY.read_text(encoding="utf-8")

    state = source.index('"$migration_helper" status')
    backup = source.index('"$migration_helper" backup')
    first_up = source.index('"$migration_helper" up')
    migration_flag = source.index('migration_applied_by_deploy="1"')
    second_up = source.index(
        '"$migration_helper" up', first_up + 1
    )
    switch_flag = source.index('version_switch_started="1"')
    compose_up = source.index("compose up --no-build -d --wait", switch_flag)

    assert state < backup < migration_flag < first_up < second_up < switch_flag < compose_up
    rollback = source.index('"$migration_helper" down')
    restore = source.index('INKFORGE_IMAGE_TAG="$previous_tag"')
    assert rollback < restore
    assert 'if [ "$migration_applied_by_deploy" = "1" ]' in source
    assert 'if [ "$version_switch_started" != "1" ]' in source


def test_helper_uses_encoded_password_only_through_pgpass_and_cleans_temp(
    tmp_path: Path,
) -> None:
    secret = "pa@ss:word"  # noqa: S105 - 仅用于验证测试凭据不会进入命令行
    result, log, pgpass, remaining = _run_helper(
        tmp_path,
        "postgresql+asyncpg://writer:pa%40ss%3Aword@host.docker.internal:5432/novelwriter",
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "migrated"
    assert "writer@127.0.0.1:5432/novelwriter" in log
    assert secret not in log
    assert "pa%40ss%3Aword" not in log
    assert pgpass == "127.0.0.1:5432:novelwriter:writer:pa@ss\\:word\n"
    assert remaining == []


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql://writer:secret@db.example:5432/novelwriter",
        "postgresql://writer:secret@host.docker.internal:5432/other",
        "postgresql://writer:secret@host.docker.internal:5432/novelwriter?target_session_attrs=read-write",
        "postgresql://writer:secret@host.docker.internal:5432/novelwriter?sslmode=require&sslmode=disable",
    ],
)
def test_helper_rejects_nonproduction_urls_before_psql(
    tmp_path: Path, database_url: str
) -> None:
    result, log, _pgpass, remaining = _run_helper(tmp_path, database_url)

    assert result.returncode != 0
    assert log == ""
    assert "secret" not in result.stderr
    assert "database-url-check:" in result.stderr
    assert remaining == []


def test_helper_access_reports_only_missing_read_privileges(tmp_path: Path) -> None:
    result, log, _pgpass, remaining = _run_helper(
        tmp_path,
        "postgresql://writer:secret@host.docker.internal:5432/novelwriter",
        action="access",
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "schema-usage:true",
        "table-count:69",
        "table-select-missing:25",
        "table-missing-owner-count:1",
        "table-missing-owner-membership:false",
        "table:VideoProject:owner=false",
        "sequence-count:0",
        "sequence-select-missing:0",
        "database-admin-path:unavailable",
    ]
    assert "secret" not in log
    assert remaining == []
