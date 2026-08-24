from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_old_agent_execution_spec_is_superseded_by_model_policy_spec() -> None:
    source = (
        ROOT / "docs" / "specs" / "2026-07-15-agent-operation-execution-contract.md"
    ).read_text(encoding="utf-8")

    assert "superseded" in source
    assert "2026-08-23-model-policy-deepseek-patch.md" in source
    assert "rewrite-only" in source
    assert "仅描述历史基线" in source
