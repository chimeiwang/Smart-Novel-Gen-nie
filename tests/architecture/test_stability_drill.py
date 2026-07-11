from pathlib import Path

ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "scripts" / "stability_drill.sh"


def test_stability_drill_is_guarded_and_uses_only_test_compose() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "ALLOW_STABILITY_DRILL" in source
    assert "infra/compose.test.yaml" in source
    assert "TEST_DATABASE_URL" in source
    assert "DATABASE_URL" not in source.replace("TEST_DATABASE_URL", "")


def test_stability_drill_enforces_thirty_minutes_and_runs_full_e2e() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "1800" in source
    assert "npm run test:e2e" in source
    assert "docker stats" in source


def test_stability_drill_rejects_oom_restart_and_failed_e2e() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "OOMKilled" in source
    assert "RestartCount" in source
    assert "e2e_failures" in source
