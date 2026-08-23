from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "token-usage-details-migration.yml"
MIGRATION = ROOT / "scripts" / "migrations" / "20260823_token_usage_details.sql"
EXPECTED_SHA256 = "1DE1CD58C589403303B40F2AA2AE9DE3C44F272E5DD6C09159327535F04C5142"


def _source() -> str:
    assert WORKFLOW.is_file(), "TokenUsage dev 迁移工作流不存在"
    return WORKFLOW.read_text(encoding="utf-8")


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


def test_inspect_fails_for_missing_tools_and_invalid_fixed_env_candidates() -> None:
    source = _source()
    inspect = source.split("if: inputs.action == 'inspect'", maxsplit=1)[1]
    inspect = inspect.split("if: inputs.action == 'migrate_dev'", maxsplit=1)[0]

    for tool in ("psql", "pg_dump", "pg_restore", "sha256sum", "docker", "python3"):
        assert tool in inspect
    assert ".env.dev" in inspect
    assert ".env.development" in inspect
    assert "missing_tools" in inspect
    assert "readable_count" in inspect
    assert "database_url_count" in inspect
    assert "DATABASE_URL" in inspect
    assert "uv" not in inspect
    assert "cat " not in inspect


def test_env_parser_is_pure_text_and_never_sources_candidate_files() -> None:
    source = _source()
    assert "python3 - \"$candidate\"" in source
    assert "def parse_database_url" in source
    assert "read_text" in source
    assert ". \"$candidate\"" not in source
    assert "source \"$candidate\"" not in source
    assert "eval " not in source
    assert "set +x" in source


def test_migrate_dev_backs_up_double_runs_and_verifies_read_only_contract() -> None:
    source = _source()
    migrate = source.split("if: inputs.action == 'migrate_dev'", maxsplit=1)[1]

    for value in (
        "BACKUP_ROOT=/srv/backups/inkforge-dev sh scripts/backup.sh",
        "pg_restore",
        "sha256sum --check SHA256SUMS",
        "psql -v ON_ERROR_STOP=1",
        "for attempt in 1 2",
        ".env.dev",
        ".env.development",
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
        'printf \'%s\' "$DATABASE_URL" | docker exec -i',
        "docker cp",
        "upload-artifact",
        "trap",
    ):
        assert value in migrate
    assert "pg_restore --list" in migrate
    assert "uv run python scripts/export_schema_contract.py" not in source
    assert "contract-$run_id.json" in migrate
    assert "$run_id.json" in migrate
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
    backup_index = migrate.index("BACKUP_ROOT=/srv/backups/inkforge-dev sh scripts/backup.sh")
    double_run_index = migrate.index("for attempt in 1 2")
    assert backup_index < double_run_index
    assert double_run_index < migrate.index("schema_guard")
    assert migrate.index("schema_guard") < migrate.index("docker cp")

    artifact = source.split("uses: actions/upload-artifact@v4", maxsplit=1)[1]
    assert "schema-contract" in artifact
    assert "database.dump" not in artifact
    assert "SHA256SUMS" not in artifact
    assert ".env." not in artifact
