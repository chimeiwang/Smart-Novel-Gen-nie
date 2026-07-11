import json
from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_root_dev_script_starts_all_three_services() -> None:
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    launcher = (ROOT / "scripts" / "dev.mjs").read_text(encoding="utf-8")

    assert package["scripts"]["dev"] == "node scripts/dev.mjs"
    assert "@inkforge/web" in launcher
    assert "inkforge_core.app:create_app" in launcher
    assert "inkforge_agents.app:create_app" in launcher
    assert ".env.local" in launcher


def test_next_development_rewrites_api_to_core() -> None:
    config = (ROOT / "apps" / "web" / "next.config.ts").read_text(encoding="utf-8")

    assert "CORE_API_INTERNAL_URL" in config
    assert 'source: "/api/:path*"' in config


def test_local_environment_example_contains_required_service_boundaries() -> None:
    source = (ROOT / ".env.local.example").read_text(encoding="utf-8")

    for key in (
        "DATABASE_URL",
        "REDIS_URL",
        "JWT_SECRET",
        "AGENT_SERVICE_URL",
        "CORE_API_URL",
        "CORE_SERVICE_PRIVATE_KEY_PATH",
        "AGENT_SERVICE_PRIVATE_KEY_PATH",
    ):
        assert f"{key}=" in source
    assert "MODEL_PROVIDER=fake" in source
