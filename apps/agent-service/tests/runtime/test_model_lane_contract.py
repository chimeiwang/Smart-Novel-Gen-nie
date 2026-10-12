from __future__ import annotations

import ast
from pathlib import Path


def test_every_production_model_runtime_call_declares_lane_explicitly() -> None:
    source_root = Path(__file__).resolve().parents[2] / "src" / "inkforge_agents"
    missing: list[str] = []
    for path in source_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in {"run_turn", "run_execution_turn"}:
                continue
            if not any(keyword.arg == "lane" for keyword in node.keywords):
                missing.append(f"{path.relative_to(source_root)}:{node.lineno}")

    assert missing == []


def test_direct_v1_entrypoints_use_frozen_lane_classification() -> None:
    source_root = Path(__file__).resolve().parents[2] / "src" / "inkforge_agents"
    expected = {
        "jobs/portrait.py": "batch_media",
        "jobs/short_medium.py": "creative",
        "jobs/video.py": "batch_media",
        "jobs/video_adaptation.py": "batch_media",
    }
    for relative, lane in expected.items():
        tree = ast.parse(
            (source_root / relative).read_text(encoding="utf-8"),
            filename=relative,
        )
        declared = [
            keyword.value.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "run_turn"
            for keyword in node.keywords
            if keyword.arg == "lane" and isinstance(keyword.value, ast.Constant)
        ]
        assert declared
        assert set(declared) == {lane}
