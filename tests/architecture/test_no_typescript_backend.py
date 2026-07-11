from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[2]
WEB = ROOT / "apps" / "web"


def test_web_contains_no_backend_entrypoints_or_database_layer() -> None:
    forbidden = (
        WEB / "src" / "agents",
        WEB / "src" / "shared" / "db",
        WEB / "src" / "app" / "api",
        WEB / "src" / "app" / "actions.ts",
    )
    assert not [path for path in forbidden if path.exists()]


def test_web_runtime_has_no_node_backend_dependencies() -> None:
    manifest = json.loads((WEB / "package.json").read_text(encoding="utf-8"))
    dependencies = set(manifest.get("dependencies", {})) | set(manifest.get("devDependencies", {}))
    forbidden = {
        "@langchain/core",
        "@langchain/langgraph",
        "@langchain/langgraph-sdk",
        "@langchain/openai",
        "@prisma/client",
        "bcryptjs",
        "langsmith",
        "openai",
        "prisma",
    }
    assert dependencies.isdisjoint(forbidden)


def test_next_uses_proxy_convention_and_has_no_server_actions() -> None:
    assert (WEB / "src" / "proxy.ts").is_file()
    assert not (WEB / "src" / "middleware.ts").exists()

    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (WEB / "src").rglob("*.ts")
        if ".next" not in path.parts
    )
    assert '"use server"' not in sources
    assert "'use server'" not in sources
    assert "DATABASE_URL" not in sources
