from pathlib import Path

from inkforge_agents.definitions.agents import AGENT_DEFINITIONS

GOLDEN_DIR = Path(__file__).parent / "prompts"


def test_agent_prompts_match_reviewed_golden_text() -> None:
    for agent_id, filename in {
        "设定": "lore.txt",
        "剧情": "plot.txt",
        "写作": "author.txt",
        "校验": "validator.txt",
        "编辑": "editor.txt",
    }.items():
        expected = (GOLDEN_DIR / filename).read_text(encoding="utf-8").strip()
        assert AGENT_DEFINITIONS[agent_id].systemPrompt.strip() == expected
