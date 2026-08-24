from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "token-usage-details-migration.yml"
MIGRATION = ROOT / "scripts" / "migrations" / "20260823_token_usage_details.sql"
EXPECTED_SHA256 = "E5D7D5946828CA3E516666607104353ADE4C034F681544B83AD45E639E549760"


def _source() -> str:
    assert WORKFLOW.is_file(), "TokenUsage dev 迁移工作流不存在"
    return WORKFLOW.read_text(encoding="utf-8")


def _embedded_database_parser(index: int = 0) -> str:
    source = _source()
    matches = list(
        re.finditer(
            r"python3 - \"\$env_file\" \"\$pgpass_file\"(?: \"\$database_url_file\")? "
            r"<<'PY'\n(?P<script>.*?)\n          PY",
            source,
            re.DOTALL,
        )
    )
    assert len(matches) == 2, "inspect 与 migrate_dev 必须各包含一个数据库 URL 解析器"
    return textwrap.dedent(matches[index].group("script"))


def _run_embedded_database_parser(
    env_text: str,
    *,
    parser_index: int = 0,
) -> subprocess.CompletedProcess[bytes]:
    python = shutil.which("python") or shutil.which("python3")
    assert python is not None
    with tempfile.TemporaryDirectory() as temporary_directory:
        temporary = Path(temporary_directory)
        env_file = temporary / ".env"
        pgpass_file = temporary / ".pgpass"
        database_url_file = temporary / ".database-url"
        env_file.write_text(env_text, encoding="utf-8")
        arguments = [python, "-", str(env_file), str(pgpass_file)]
        if parser_index == 1:
            arguments.append(str(database_url_file))
        result = subprocess.run(  # noqa: S603
            arguments,
            input=_embedded_database_parser(parser_index).encode("utf-8"),
            capture_output=True,
        )
        result.pgpass = (  # type: ignore[attr-defined]
            pgpass_file.read_text(encoding="utf-8") if pgpass_file.exists() else ""
        )
        result.pgpass_mode = (  # type: ignore[attr-defined]
            pgpass_file.stat().st_mode & 0o777 if pgpass_file.exists() else None
        )
        result.database_url = (  # type: ignore[attr-defined]
            database_url_file.read_text(encoding="utf-8")
            if database_url_file.exists()
            else ""
        )
        result.database_url_mode = (  # type: ignore[attr-defined]
            database_url_file.stat().st_mode & 0o777 if database_url_file.exists() else None
        )
        return result


def test_workflow_accepts_only_the_fixed_dispatch_choice() -> None:
    source = _source()

    assert re.search(
        r"^[\"']?on[\"']?:\n  workflow_dispatch:\n    inputs:\n      action:",
        source,
        re.MULTILINE,
    )
    assert "type: choice" in source
    assert "- inspect" in source
    assert "- migrate_dev" in source
    assert "push:" not in source
    assert "pull_request:" not in source
    assert source.count("inputs:") == 1
    assert "SQL" not in source.split("workflow_dispatch:", maxsplit=1)[1].split("jobs:", 1)[0]


def test_workflow_pins_sql_hash_and_uses_production_ssh_environment() -> None:
    source = _source()

    assert "scripts/migrations/20260823_token_usage_details.sql" in source
    assert hashlib.sha256(MIGRATION.read_bytes()).hexdigest().upper() == EXPECTED_SHA256
    assert EXPECTED_SHA256 in source
    for value in (
        "environment: production",
        "secrets.SERVER_HOST",
        "secrets.SERVER_USER",
        "secrets.SERVER_SSH_KEY",
        "secrets.DEPLOY_SSH_KNOWN_HOSTS",
        "vars.APP_DIR",
        "StrictHostKeyChecking=yes",
        "UserKnownHostsFile=",
    ):
        assert value in source
    assert "StrictHostKeyChecking=no" not in source
    assert "DATABASE_URL" not in source.split("jobs:", maxsplit=1)[0]


def test_inspect_derives_and_verifies_the_fixed_dev_database() -> None:
    source = _source()
    inspect = source.split("if: inputs.action == 'inspect'", maxsplit=1)[1]
    inspect = inspect.split("if: inputs.action == 'migrate_dev'", maxsplit=1)[0]

    for tool in ("psql", "pg_dump", "pg_restore", "sha256sum", "docker", "python3"):
        assert tool in inspect
    assert 'env_file="$app_dir/.env"' in inspect
    assert "def derive_dev_database_url" in inspect
    assert 'parts.path != "/novelwriter"' in inspect
    assert 'path="/novelwriterdev"' in inspect
    assert 'SELECT current_database()' in inspect
    assert '"$database_name" = "novelwriterdev"' in inspect
    assert "missing_tools" in inspect
    assert "DATABASE_URL" in inspect
    assert "uv" not in inspect
    assert "cat " not in inspect


def test_env_parser_is_pure_text_and_never_sources_production_env() -> None:
    source = _source()
    assert 'python3 - "$env_file"' in source
    assert "def derive_dev_database_url" in source
    assert "read_text" in source
    assert '. "$env_file"' not in source
    assert 'source "$env_file"' not in source
    assert "eval " not in source
    assert "set +x" in source


def test_embedded_database_parser_preserves_safe_url_fields_and_writes_private_pgpass() -> None:
    result = _run_embedded_database_parser(
        "DATABASE_URL='postgresql://app_user:p%40ss%25word@host.docker.internal:55432/novelwriter?sslmode=require&application_name=token-migration'\n"
    )

    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout.decode() == (
        "postgresql://app_user@127.0.0.1:55432/novelwriterdev?"
        "sslmode=require&application_name=token-migration"
    )
    assert result.pgpass == "127.0.0.1:55432:novelwriterdev:app_user:p@ss%word\n"  # type: ignore[attr-defined]
    if os.name != "nt":
        assert result.pgpass_mode == 0o600  # type: ignore[attr-defined]


def test_migrate_parser_writes_full_dev_url_only_to_private_stdin_file() -> None:
    result = _run_embedded_database_parser(
        "DATABASE_URL=postgresql+asyncpg://app_user:p%40ss@host.docker.internal:55432/novelwriter?sslmode=require\n",
        parser_index=1,
    )

    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout.decode() == (
        "postgresql://app_user@127.0.0.1:55432/novelwriterdev?sslmode=require"
    )
    assert result.database_url == (  # type: ignore[attr-defined]
        "postgresql://app_user:p%40ss@host.docker.internal:55432/novelwriterdev?sslmode=require"
    )
    if os.name != "nt":
        assert result.database_url_mode == 0o600  # type: ignore[attr-defined]


@pytest.mark.parametrize("parser_index", (0, 1))
def test_embedded_database_parser_accepts_safe_query_with_trailing_separator(
    parser_index: int,
) -> None:
    result = _run_embedded_database_parser(
        "DATABASE_URL=postgresql://app:secret@host.docker.internal/novelwriter?sslmode=require&\n",
        parser_index=parser_index,
    )

    assert result.returncode == 0, result.stderr.decode()


@pytest.mark.parametrize("parser_index", (0, 1))
def test_embedded_database_parser_rejects_duplicate_database_url(parser_index: int) -> None:
    result = _run_embedded_database_parser(
        "DATABASE_URL=postgresql://one:secret@host.docker.internal/novelwriter\n"
        "DATABASE_URL=postgresql://two:secret@host.docker.internal/novelwriter\n",
        parser_index=parser_index,
    )

    assert result.returncode != 0
    assert result.stderr.decode().strip() == "database-url-check:database_url_count"


@pytest.mark.parametrize(
    "query_key",
    (
        "dbname",
        "database",
        "host",
        "hostaddr",
        "port",
        "user",
        "password",
        "service",
        "servicefile",
    ),
)
@pytest.mark.parametrize("parser_index", (0, 1))
def test_embedded_database_parser_rejects_target_changing_query_parameters(
    query_key: str,
    parser_index: int,
) -> None:
    result = _run_embedded_database_parser(
        f"DATABASE_URL=postgresql://app:secret@host.docker.internal/novelwriter?{query_key}=unsafe\n",
        parser_index=parser_index,
    )

    assert result.returncode != 0
    assert result.stderr.decode().strip() == "database-url-check:query"


@pytest.mark.parametrize("query_key", ("sslmode", "application_name"))
@pytest.mark.parametrize("parser_index", (0, 1))
def test_embedded_database_parser_rejects_duplicate_safe_query_parameters(
    query_key: str,
    parser_index: int,
) -> None:
    result = _run_embedded_database_parser(
        "DATABASE_URL=postgresql://app:secret@host.docker.internal/novelwriter?"
        f"{query_key}=first&{query_key}=second\n",
        parser_index=parser_index,
    )

    assert result.returncode != 0
    assert result.stderr.decode().strip() == "database-url-check:query"


@pytest.mark.parametrize("source_host", ("db.example", "localhost", "127.0.0.1"))
@pytest.mark.parametrize("parser_index", (0, 1))
def test_embedded_database_parser_rejects_non_compose_source_host(
    source_host: str,
    parser_index: int,
) -> None:
    result = _run_embedded_database_parser(
        f"DATABASE_URL=postgresql://app:secret@{source_host}/novelwriter\n",
        parser_index=parser_index,
    )

    assert result.returncode != 0
    assert result.stderr.decode().strip() == "database-url-check:source_host"


def test_migration_checks_database_before_ddl_and_never_argvs_password_url() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")
    source = _source()
    first_alter = migration.index("ALTER TABLE")
    assert migration.index("current_database() <> 'novelwriterdev'") < first_alter

    migrate = source.split("if: inputs.action == 'migrate_dev'", maxsplit=1)[1]
    assert "PGPASSFILE" in migrate
    assert ".pgpass" in migrate
    assert 'psql -v ON_ERROR_STOP=1 "$DATABASE_URL"' not in migrate
    assert 'pg_restore --list "$backup_dir/database.dump"' in migrate
    assert 'printf \'%s\' "$DATABASE_URL" |' not in migrate
    assert '"$container_contract" < "$database_url_file"' in migrate
    assert 'docker exec -i "$core_container" python3 -c' in migrate
    assert source.count("SAFE_QUERY_KEYS =") == 2


def test_migration_itself_refuses_every_database_except_novelwriterdev() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")

    assert "current_database() <> 'novelwriterdev'" in migration
    assert "TokenUsage 明细迁移只允许在 novelwriterdev 执行" in migration


def test_migrate_dev_backs_up_double_runs_and_verifies_read_only_contract() -> None:
    source = _source()
    migrate = source.split("if: inputs.action == 'migrate_dev'", maxsplit=1)[1]

    for value in (
        "BACKUP_ROOT=/srv/backups/inkforge-dev sh scripts/backup.sh",
        "pg_restore",
        "sha256sum --check SHA256SUMS",
        "psql -v ON_ERROR_STOP=1",
        "for attempt in 1 2",
        'env_file="$app_dir/.env"',
        "def derive_dev_database_url",
        'SELECT current_database()',
        '"$database_name" = "novelwriterdev"',
        "set +x",
        "TokenUsage_prompt_cache_details_check",
        "TokenUsage_reasoning_details_check",
        "TokenUsage_token_details_nonnegative_check",
        "atttypid",
        "attnotnull",
        "atthasdef",
        "promptCacheMissTokens",
        "reasoningTokens",
        "docker ps",
        "docker exec -i",
        "schema_guard",
        "export_schema_contract",
        '"$container_contract" < "$database_url_file"',
        "docker cp",
        "upload-artifact",
        "trap",
    ):
        assert value in migrate
    assert "pg_restore --list" in migrate
    assert "uv run python scripts/export_schema_contract.py" not in source
    assert "details-$run_id-$run_attempt.json" in migrate
    assert "$run_id-$run_attempt.json" in migrate
    assert "reasoning_content" not in source
    assert "GITHUB_ENV" not in source
    assert "GITHUB_STEP_SUMMARY" not in source


def test_secrets_are_scoped_to_ssh_steps_and_contract_is_only_artifact() -> None:
    source = _source()
    job_env = source.split("    steps:", maxsplit=1)[0]
    assert "SERVER_SSH_KEY" not in job_env
    assert "DEPLOY_SSH_KNOWN_HOSTS" not in job_env
    assert "secrets.SERVER_SSH_KEY" in source.split("- name: 准备严格 SSH", maxsplit=1)[1].split(
        "run:", maxsplit=1
    )[0]
    assert "secrets.DEPLOY_SSH_KNOWN_HOSTS" in source.split(
        "- name: 准备严格 SSH", maxsplit=1
    )[1].split("run:", maxsplit=1)[0]

    migrate = source.split("if: inputs.action == 'migrate_dev'", maxsplit=1)[1]
    database_guard_index = migrate.index('"$database_name" = "novelwriterdev"')
    backup_index = migrate.index("BACKUP_ROOT=/srv/backups/inkforge-dev sh scripts/backup.sh")
    double_run_index = migrate.index("for attempt in 1 2")
    assert database_guard_index < backup_index
    assert backup_index < double_run_index
    assert double_run_index < migrate.index("schema_guard")
    assert migrate.index("schema_guard") < migrate.index("docker cp")

    artifact = source.split("uses: actions/upload-artifact@v4", maxsplit=1)[1]
    assert "schema-contract" in artifact
    assert "database.dump" not in artifact
    assert "SHA256SUMS" not in artifact
    assert ".env." not in artifact


def test_workflow_semantics_concurrency_timeout_and_all_shell_blocks() -> None:
    source = _source()
    workflow = yaml.safe_load(source)
    assert workflow["on"] == {
        "workflow_dispatch": {
            "inputs": {
                "action": {
                    "description": "选择只读检查或执行 dev 迁移",
                    "required": True,
                    "type": "choice",
                    "options": ["inspect", "migrate_dev"],
                }
            }
        }
    }
    job = workflow["jobs"]["migration"]
    assert job["environment"] == "production"
    assert job["concurrency"] == {
        "group": "token-usage-details-dev-migration",
        "cancel-in-progress": False,
    }
    assert job["timeout-minutes"] == 30

    run_blocks = [step["run"] for step in job["steps"] if "run" in step]
    bash_path = shutil.which("bash")
    assert bash_path is not None
    with tempfile.TemporaryDirectory() as temporary_directory:
        for index, run_block in enumerate(run_blocks):
            shell_file = Path(temporary_directory) / f"step-{index}.sh"
            shell_file.write_text(run_block, encoding="utf-8")
            result = subprocess.run(  # noqa: S603
                [bash_path, "-n"],
                input=shell_file.read_bytes().replace(b"\r", b""),
                capture_output=True,
            )
            assert result.returncode == 0, result.stderr.decode()


def test_remote_transports_have_uniform_timeouts_and_fixed_numeric_temp_paths() -> None:
    source = _source()
    transport_commands = re.findall(r"^\s+(ssh|scp)(?: -q)?\s+\\$", source, re.MULTILINE)
    assert transport_commands
    for option in (
        "-o ConnectTimeout=15",
        "-o ServerAliveInterval=15",
        "-o ServerAliveCountMax=4",
        "-o TCPKeepAlive=yes",
        "-o StrictHostKeyChecking=yes",
    ):
        assert source.count(option) >= len(transport_commands)

    assert "timeout 600 env BACKUP_ROOT=/srv/backups/inkforge-dev sh scripts/backup.sh" in source
    assert "timeout 180 psql" in source
    assert "PGOPTIONS='-c statement_timeout=120000 -c lock_timeout=30000'" in source
    assert "timeout 180 docker exec" in source
    assert "timeout 180 docker cp" in source
    assert "timeout " in source

    assert "GITHUB_RUN_ID" in source
    assert "GITHUB_RUN_ATTEMPT" in source
    assert "mktemp" not in source
    assert "case \"$run_id\" in" in source
    assert "case \"$run_attempt\" in" in source
    assert "umask 077" in source
    assert 'sh -s -- "$remote_sql" "$remote_contract"' in source
    assert "rm -f -- '$remote_sql' '$remote_contract'" not in source
