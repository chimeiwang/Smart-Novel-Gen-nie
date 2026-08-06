from __future__ import annotations

import ast
from pathlib import Path

CLI_PACKAGE = (
    Path(__file__).resolve().parents[1] / "src" / "inkforge_cli"
)


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)
    return imported


def test_long_commands_do_not_import_short_snapshot_business() -> None:
    long_root = CLI_PACKAGE / "commands" / "long"
    forbidden_names = {
        "DirtySnapshotError",
        "ensure_snapshot_clean",
        "export_snapshot",
        "load_snapshot_manifest",
    }

    for path in long_root.rglob("*.py") if long_root.exists() else ():
        imported = _imported_modules(path)
        source = path.read_text(encoding="utf-8")
        assert not any(module.endswith("short.snapshots") for module in imported), path
        assert not any(name in source for name in forbidden_names), path


def test_common_io_has_no_short_snapshot_business_symbols() -> None:
    io_path = CLI_PACKAGE / "io.py"
    source = io_path.read_text(encoding="utf-8")

    assert "DirtySnapshotError" not in source
    assert "ensure_snapshot_clean" not in source
    assert "export_snapshot" not in source
    assert "load_snapshot_manifest" not in source
