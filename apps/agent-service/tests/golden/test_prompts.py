from pathlib import Path

from inkforge_agents.definitions.agents import AGENT_DEFINITIONS
from inkforge_agents.prompts.author import SYSTEM_PROMPT as AUTHOR_SYSTEM_PROMPT
from inkforge_agents.prompts.editor import SYSTEM_PROMPT as EDITOR_SYSTEM_PROMPT
from inkforge_agents.prompts.lore import SYSTEM_PROMPT as LORE_SYSTEM_PROMPT
from inkforge_agents.prompts.plot import SYSTEM_PROMPT as PLOT_SYSTEM_PROMPT
from inkforge_agents.prompts.validator import SYSTEM_PROMPT as VALIDATOR_SYSTEM_PROMPT

GOLDEN_DIR = Path(__file__).parent / "prompts"
ALL_SYSTEM_PROMPTS = (
    AUTHOR_SYSTEM_PROMPT,
    EDITOR_SYSTEM_PROMPT,
    LORE_SYSTEM_PROMPT,
    PLOT_SYSTEM_PROMPT,
    VALIDATOR_SYSTEM_PROMPT,
)

RUNTIME_PROTOCOL_FRAGMENTS = (
    "get_active_review_artifact",
    "submit_evaluation",
    "submit_quality_report",
    "submit_validation_report",
    "begin_artifact_output",
    "ARTIFACT_OUTPUT_START",
    "ARTIFACT_OUTPUT_END",
    "start_update_builder",
    "finish_update_builder",
    "submit_beat_plan",
    "artifactKey",
    "精确小修使用 patch",
    "局部修改使用 patch",
    "必须使用 rewrite",
    "使用 rewrite",
    "完整返工",
    "系统会先提供摘要索引",
)


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


def test_all_static_prompts_exclude_runtime_protocol() -> None:
    for prompt in ALL_SYSTEM_PROMPTS:
        for forbidden in RUNTIME_PROTOCOL_FRAGMENTS:
            assert forbidden not in prompt


def test_plot_prompt_has_no_fixed_short_story_section_or_chapter_assumption() -> None:
    for forbidden in (
        "三到十万字",
        "八到二十五章",
        "三到五个剧情单元",
        "固定节数",
        "每节字数",
    ):
        assert forbidden not in PLOT_SYSTEM_PROMPT
    assert "分节数量完全由故事需要决定" in PLOT_SYSTEM_PROMPT
    assert "不映射为章节" in PLOT_SYSTEM_PROMPT
