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


def test_inspect_reports_tools_and_fixed_env_candidates_without_reading_them() -> None:
    source = _source()
    inspect = source.split("if: inputs.action == 'inspect'", maxsplit=1)[1]
    inspect = inspect.split("if: inputs.action == 'migrate_dev'", maxsplit=1)[0]

    for tool in ("psql", "pg_dump", "sha256sum", "docker", "uv"):
        assert tool in inspect
    assert ".env.dev" in inspect
    assert ".env.development" in inspect
    assert "cat " not in inspect
    assert "source " not in inspect
    assert "DATABASE_URL" not in inspect


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
        "uv run python scripts/export_schema_contract.py --database-url "
        '"$DATABASE_URL" --output "$contract_temp"',
        "upload-artifact",
        "trap",
    ):
        assert value in migrate
    assert "pg_restore --list" in migrate
    assert "reasoning_content" not in source
    assert "GITHUB_ENV" not in source
    assert "GITHUB_STEP_SUMMARY" not in source
