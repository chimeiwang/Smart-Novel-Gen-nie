from pathlib import Path

ROOT = Path(__file__).parents[2]
ROLLBACK = ROOT / "scripts" / "rollback_drill.sh"
SMOKE_SH = ROOT / "scripts" / "compose_smoke.sh"
SMOKE_PS1 = ROOT / "scripts" / "compose_smoke.ps1"


def test_production_smoke_does_not_enable_test_compose_by_default() -> None:
    shell_source = SMOKE_SH.read_text(encoding="utf-8")
    powershell_source = SMOKE_PS1.read_text(encoding="utf-8")

    assert "COMPOSE_OVERRIDE_FILE" in shell_source
    assert "COMPOSE_OVERRIDE_FILE" in powershell_source
    unsafe_default = 'compose="docker compose -f infra/compose.yaml -f infra/compose.test.yaml"'
    assert unsafe_default not in shell_source


def test_rollback_requires_distinct_current_and_previous_python_tags() -> None:
    source = ROLLBACK.read_text(encoding="utf-8")

    assert "CURRENT_IMAGE_TAG" in source
    assert "ROLLBACK_IMAGE_TAG" in source
    assert '"$CURRENT_IMAGE_TAG" != "$ROLLBACK_IMAGE_TAG"' in source
    for image in ("inkforge-web", "inkforge-core-api", "inkforge-agent-service"):
        assert f"{image}:$ROLLBACK_IMAGE_TAG" in source
        assert f"{image}:$CURRENT_IMAGE_TAG" in source


def test_rollback_restores_current_stack_when_verification_fails() -> None:
    source = ROLLBACK.read_text(encoding="utf-8")

    assert "restore_current" in source
    assert "trap" in source
    assert "scripts/compose_smoke.sh" in source
    assert "inkforge_core.db.schema_guard" in source
    assert "--no-build" in source
    assert "down -v" not in source
    assert "restore_verify.sh" not in source
