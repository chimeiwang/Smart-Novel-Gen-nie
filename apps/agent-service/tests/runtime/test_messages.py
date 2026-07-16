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
