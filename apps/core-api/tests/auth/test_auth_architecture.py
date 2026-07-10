from __future__ import annotations

from pathlib import Path


def test_auth_package_never_imports_or_accesses_novel_model() -> None:
    auth_root = Path(__file__).parents[2] / "src" / "inkforge_core" / "auth"
    source = "\n".join(path.read_text(encoding="utf-8") for path in auth_root.glob("*.py"))

    assert "Novel" not in source
    assert "novel" not in source.lower()
