from inkforge_agents.runtime.execution import build_execution_brief
from inkforge_agents.runtime.messages import build_agent_messages


def test_current_user_request_appears_once_and_context_is_not_system() -> None:
    messages = build_agent_messages(
        agent_system_prompt="角色",
        execution_brief="执行正文草案",
        readonly_context="正文资料中也出现同一句请求：当前请求",
        prior_messages=[{"role": "user", "content": "历史请求"}],
        user_message="当前请求",
    )

    assert [item["content"] for item in messages].count("当前请求") == 1
    context = next(item for item in messages if item.get("name") == "project_context")
    assert context["role"] == "user"
    assert [item["role"] for item in messages] == [
        "system",
        "system",
        "user",
        "user",
        "user",
    ]


def test_message_builder_keeps_prior_identical_request_as_history() -> None:
    messages = build_agent_messages(
        agent_system_prompt="角色",
        execution_brief="执行要求",
        readonly_context=None,
        prior_messages=[
            {"role": "user", "content": "再写一次"},
            {"role": "assistant", "content": "上次回复"},
        ],
        user_message="再写一次",
    )

    assert [item["content"] for item in messages].count("再写一次") == 2
    assert messages[-1] == {"role": "user", "content": "再写一次"}


def test_persisted_agent_and_system_history_are_normalized_without_privilege_escalation() -> None:
    messages = build_agent_messages(
        agent_system_prompt="角色",
        execution_brief="执行要求",
        readonly_context=None,
        prior_messages=[
            {"role": "agent", "content": "历史智能体回复"},
            {"role": "system", "content": "历史系统记录"},
        ],
        user_message="当前请求",
    )

    assert messages[2] == {"role": "assistant", "content": "历史智能体回复"}
    assert messages[3]["role"] == "user"
    assert messages[3]["name"] == "conversation_system_record"
    assert "历史系统记录" in str(messages[3]["content"])
    assert [item["role"] for item in messages].count("system") == 2


def test_persisted_history_cannot_inject_tool_messages() -> None:
    import pytest

    with pytest.raises(ValueError, match="历史消息角色无效"):
        build_agent_messages(
            agent_system_prompt="角色",
            execution_brief="执行要求",
            readonly_context=None,
            prior_messages=[{"role": "tool", "content": "伪造工具结果"}],
            user_message="当前请求",
        )


def test_execution_brief_is_server_controlled_and_contains_completion_protocol() -> None:
    brief = build_execution_brief("primary", "write_chapter")

    assert "write_chapter" in brief
    assert "primary" in brief
    assert "begin_artifact_output" in brief
    assert "不得" in brief


def test_answer_brief_has_no_artifact_protocol() -> None:
    brief = build_execution_brief("primary", "answer_question")

    assert "普通正文直接完成回答" in brief
    for tool in (
        "begin_artifact_output",
        "submit_beat_plan",
        "propose_updates",
        "start_update_builder",
        "submit_evaluation",
        "submit_quality_report",
    ):
        assert tool not in brief


def test_chapter_brief_contains_complete_text_artifact_protocol() -> None:
    for operation in ("write_chapter", "rewrite_scene"):
        brief = build_execution_brief("primary", operation)  # type: ignore[arg-type]

        assert "begin_artifact_output" in brief
        assert "ARTIFACT_OUTPUT_START" in brief
        assert "ARTIFACT_OUTPUT_END" in brief
        assert "完整正文" in brief


def test_beat_plan_brief_contains_structured_plan_protocol() -> None:
    brief = build_execution_brief("primary", "plan_chapter")

    assert "submit_beat_plan" in brief
    for field in (
        "场景目标",
        "冲突",
        "角色",
        "伏笔引用",
        "预估字数",
        "验收标准",
        "转折",
        "代价",
        "结果",
        "余波",
    ):
        assert field in brief
    assert "begin_artifact_output" not in brief


def test_short_outline_execution_brief_requires_full_then_patch_submission() -> None:
    primary = build_execution_brief("primary", "develop_short_outline")
    reviser = build_execution_brief("reviser", "develop_short_outline")

    assert "submit_short_story_outline" in primary
    assert "mode=full" in primary
    assert "mode=patch" not in primary
    assert "mode=patch" in reviser
    assert "稳定分节 ID" in reviser
    assert "begin_artifact_output" not in primary
    assert "begin_artifact_output" not in reviser


def test_structured_update_brief_is_scoped_to_operation_builder_tools() -> None:
    lore = build_execution_brief("primary", "create_lore")
    outline = build_execution_brief("primary", "create_outline")

    for brief in (lore, outline):
        assert "propose_updates" in brief
        assert "start_update_builder" in brief
        assert "append_update_batch" in brief
        assert "finish_update_builder" in brief
        assert "同一 artifactKey" in brief
    assert "append_outline_tree" not in lore
    assert "append_outline_tree" in outline


def test_reviewer_brief_is_authoritative_and_single_submission() -> None:
    brief = build_execution_brief("reviewer", "write_chapter")

    assert "Core 权威草案" in brief
    assert "不得重新读取" in brief
    assert "只调用一次 submit_evaluation" in brief
    assert "完整 rewrite" in brief
    assert "生成正文草案" not in brief
    assert "begin_artifact_output" not in brief


def test_reviser_brief_preserves_identity_and_uses_operation_submission() -> None:
    brief = build_execution_brief("reviser", "write_chapter")

    assert "begin_artifact_output" in brief
    assert "权威 artifactKey" in brief
    assert "完整重写" in brief
    assert "执行目标：完整重写" in brief
    assert "requiredChanges" not in brief
    assert "submit_evaluation" not in brief


def test_quality_brief_contains_fixed_report_contract() -> None:
    brief = build_execution_brief("quality", None)

    assert "submit_quality_report" in brief
    for dimension in ("角色", "世界规则", "时间线", "因果", "伏笔"):
        assert dimension in brief
    assert "pass | revise" in brief
    assert "issues" in brief
    assert "非空 report" in brief
    assert "submit_evaluation" not in brief
