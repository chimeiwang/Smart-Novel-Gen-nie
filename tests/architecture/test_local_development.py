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
    assert "npm_execpath" in launcher
    assert '".venv", "Scripts", "uvicorn.exe"' in launcher
    assert 'executable("uv")' not in launcher


def test_next_development_rewrites_api_to_core() -> None:
    config = (ROOT / "apps" / "web" / "next.config.ts").read_text(encoding="utf-8")

    assert "CORE_API_INTERNAL_URL" in config
    assert 'source: "/api/:path*"' in config


def test_next_development_allows_loopback_client_resources() -> None:
    config = (ROOT / "apps" / "web" / "next.config.ts").read_text(encoding="utf-8")

    assert 'allowedDevOrigins: ["127.0.0.1"]' in config


def test_e2e_reuses_authenticated_state_after_auth_scenario() -> None:
    config = (ROOT / "playwright.config.ts").read_text(encoding="utf-8")
    auth_spec = (ROOT / "tests" / "e2e" / "auth.spec.ts").read_text(encoding="utf-8")
    helpers = (ROOT / "tests" / "e2e" / "helpers.ts").read_text(encoding="utf-8")
    business_specs = [
        "knowledge-style.spec.ts",
        "project-editor.spec.ts",
        "quality-billing.spec.ts",
        "writing-artifact.spec.ts",
    ]

    assert "AUTH_STATE_PATH" in config
    assert 'name: "认证准备"' in config
    assert "testMatch: /auth\\.spec\\.ts/" in config
    assert "testIgnore: /auth\\.spec\\.ts/" in config
    assert 'dependencies: ["认证准备"]' in config
    assert "storageState: AUTH_STATE_PATH" in config
    assert "retries: 0" in config
    assert "storageState({ path: AUTH_STATE_PATH })" in auth_spec
    assert "registerWithApi" not in helpers
    for filename in business_specs:
        source = (ROOT / "tests" / "e2e" / filename).read_text(encoding="utf-8")
        assert "registerWithApi" not in source


def test_e2e_uses_current_project_and_writing_entry_points() -> None:
    project = (ROOT / "tests" / "e2e" / "project-editor.spec.ts").read_text(
        encoding="utf-8"
    )
    writing = (ROOT / "tests" / "e2e" / "writing-artifact.spec.ts").read_text(
        encoding="utf-8"
    )
    knowledge = (ROOT / "tests" / "e2e" / "knowledge-style.spec.ts").read_text(
        encoding="utf-8"
    )
    quality = (ROOT / "tests" / "e2e" / "quality-billing.spec.ts").read_text(
        encoding="utf-8"
    )
    helpers = (ROOT / "tests" / "e2e" / "helpers.ts").read_text(encoding="utf-8")

    assert 'page.locator("form").getByRole("button", { name: "新建小说"' in project
    assert "智能写作" not in writing
    assert writing.count('getByRole("button", { name: /生成正文/' ) == 2
    assert 'const styleName = `端到端文风-${Date.now()}`' in knowledge
    assert "expect.poll" in quality
    assert "page.reload()" in quality
    assert 'page.request.get("/api/v1/billing/usage")' in quality
    assert "body.totalUsage.totalTokens" in quality
    assert "prepareWritingOutlineWithApi" in helpers
    assert writing.count("prepareWritingOutlineWithApi(page, identity)") == 2
    assert "已应用" not in writing
    assert "已丢弃" not in writing
    assert 'getByRole("button", { name: "待确认 0" })' in writing


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
