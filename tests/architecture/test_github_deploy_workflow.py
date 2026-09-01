from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "token-usage-details-migration.yml"
MIGRATION = ROOT / "scripts" / "migrations" / "20260823_token_usage_details.sql"


def _source() -> str:
    assert WORKFLOW.is_file(), "TokenUsage 迁移退役工作流不存在"
    return WORKFLOW.read_text(encoding="utf-8")


def test_completed_one_time_migration_workflow_is_permanently_fail_closed() -> None:
    source = _source()
    workflow = yaml.safe_load(source)

    assert workflow["on"] == {"workflow_dispatch": None}
    assert workflow["permissions"] == {"contents": "read"}
    assert set(workflow["jobs"]) == {"retired"}
    job = workflow["jobs"]["retired"]
    assert "environment" not in job
    assert job["timeout-minutes"] == 5
    assert len(job["steps"]) == 1
    run = job["steps"][0]["run"]
    assert "workflow-retired" in run
    assert re.search(r"^exit 1$", run, re.MULTILINE)


def test_retired_workflow_has_no_ssh_or_production_mutation_capability() -> None:
    source = _source()

    for forbidden in (
        "SERVER_SSH_KEY",
        "DURABLE_AGENT_V2_RELEASE_SSH_PRIVATE_KEY",
        "DEPLOY_SSH_KNOWN_HOSTS",
        "environment: production",
        "secrets.",
        "vars.APP_DIR",
        "ssh ",
        "scp ",
        "docker ",
        "psql ",
        "pg_dump",
        "ALTER TABLE",
        "scripts/migrations/",
    ):
        assert forbidden not in source


def test_retired_workflow_shell_is_syntactically_valid() -> None:
    workflow = yaml.safe_load(_source())
    run = workflow["jobs"]["retired"]["steps"][0]["run"]
    bash = shutil.which("bash")
    assert bash is not None
    with tempfile.TemporaryDirectory() as temporary_directory:
        shell_file = Path(temporary_directory) / "retired.sh"
        shell_file.write_text(run, encoding="utf-8")
        result = subprocess.run(  # noqa: S603
            [bash, "-n", str(shell_file)],
            capture_output=True,
            check=False,
        )
    assert result.returncode == 0, result.stderr.decode()


def test_migration_itself_refuses_every_database_except_novelwriterdev() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")

    assert "current_database() <> 'novelwriterdev'" in migration
    assert "TokenUsage 明细迁移只允许在 novelwriterdev 执行" in migration


def test_migration_compares_constraints_using_postgres_canonical_definitions() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")

    assert "CREATE TEMP TABLE token_usage_details_constraint_contract" in migration
    assert "ON COMMIT DROP" in migration
    assert "pg_temp.token_usage_details_constraint_contract" in migration
    assert "pg_get_constraintdef" in migration
    assert "expected_constraint.definition" in migration
    assert "$constraint$CHECK" not in migration
