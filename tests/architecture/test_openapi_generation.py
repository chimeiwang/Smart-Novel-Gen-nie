from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_api_drift_check_normalizes_line_endings_on_both_sides() -> None:
    source = (ROOT / "scripts" / "generate_api_client.mjs").read_text(encoding="utf-8")

    assert "function normalizeLineEndings" in source
    assert "normalizeLineEndings(current) !== normalizeLineEndings(generated)" in source
