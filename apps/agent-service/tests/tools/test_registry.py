import pytest
from inkforge_agents.tools.permissions import read_only_permission
from inkforge_agents.tools.registry import (
    ToolContext,
    ToolDefinition,
    ToolRegistry,
    build_default_registry,
)
from inkforge_contracts.read_tools import READ_TOOL_NAMES
from pydantic import BaseModel, ConfigDict


class EmptyArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RecordingGateway:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def execute(
        self,
        tool_name: str,
        context: ToolContext,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        del context, arguments
        self.calls.append(tool_name)
        return {"ok": True}


async def execute_empty(
    arguments: dict[str, object],
    context: ToolContext,
) -> dict[str, object]:
    del arguments, context
    return {"ok": True}


def restricted_tool() -> ToolDefinition:
    return ToolDefinition(
        name="restricted_read",
        description="受限只读工具",
        argumentsModel=EmptyArgs,
        permission=read_only_permission("novel.read", {"设定"}),
        toolKind="read",
        handler=execute_empty,
    )


def tool_context(agent_id: str) -> ToolContext:
    return ToolContext(
        userId="user-1",
        novelId="novel-1",
        taskId="task-1",
        runId="run-1",
        agentId=agent_id,
    )


def test_registry_contains_migrated_read_proposal_and_control_tools() -> None:
    registry = build_default_registry()
    names = {tool.name for tool in registry.all()}

    assert {
        "get_novel_info",
        "get_character_detail",
        "get_active_review_artifact",
        "propose_update_character",
        "propose_updates",
        "append_outline_tree",
        "begin_artifact_output",
        "submit_evaluation",
    } <= names
    assert set(READ_TOOL_NAMES) <= names


def test_require_authorized_returns_the_registered_tool_for_known_agent() -> None:
    registry = ToolRegistry()
    tool = restricted_tool()
    registry.register(tool)

    assert registry.require_authorized(tool, tool_context("设定")) is tool


def test_require_authorized_rejects_same_name_unregistered_definition() -> None:
    registry = ToolRegistry()
    registry.register(restricted_tool())

    with pytest.raises(ValueError, match="工具定义与注册表不一致"):
        registry.require_authorized(restricted_tool(), tool_context("设定"))


@pytest.mark.parametrize("agent_id", ["写作", "未知"])
def test_require_authorized_uses_trusted_capabilities(agent_id: str) -> None:
    registry = ToolRegistry()
    tool = restricted_tool()
    registry.register(tool)

    with pytest.raises(PermissionError, match="当前智能体无权执行工具"):
        registry.require_authorized(tool, tool_context(agent_id))


@pytest.mark.asyncio
async def test_registry_refuses_control_tool_direct_execution() -> None:
    registry = build_default_registry()
    context = ToolContext(
        userId="user-1",
        novelId="novel-1",
        taskId="task-1",
        runId="run-1",
        agentId="校验",
    )

    with pytest.raises(ValueError, match="控制工具只能由智能体运行时捕获"):
        await registry.execute(
            "submit_evaluation",
            {
                "artifactKey": "task-1:write_chapter",
                "verdict": "pass",
                "summary": "通过",
            },
            context,
        )


@pytest.mark.asyncio
async def test_execute_validated_requires_the_registered_tool_definition() -> None:
    registry = ToolRegistry()
    registered = restricted_tool()
    registry.register(registered)
    same_name_but_unregistered = restricted_tool()

    with pytest.raises(ValueError, match="工具定义与注册表不一致"):
        await registry.execute_validated(
            same_name_but_unregistered,
            {},
            tool_context("设定"),
        )


@pytest.mark.asyncio
async def test_execute_validated_rechecks_agent_restriction() -> None:
    registry = ToolRegistry()
    tool = restricted_tool()
    registry.register(tool)

    with pytest.raises(PermissionError, match="当前智能体无权执行工具"):
        await registry.execute_validated(tool, {}, tool_context("写作"))


@pytest.mark.asyncio
async def test_execute_validated_rejects_capability_not_owned_by_agent() -> None:
    gateway = RecordingGateway()
    registry = build_default_registry(gateway)
    tool = registry.require("get_style_profile")

    with pytest.raises(PermissionError, match="当前智能体无权执行工具"):
        await registry.execute_validated(tool, tool.validate({}), tool_context("设定"))

    assert gateway.calls == []


@pytest.mark.asyncio
async def test_execute_validated_rejects_unknown_agent() -> None:
    gateway = RecordingGateway()
    registry = build_default_registry(gateway)
    tool = registry.require("get_novel_info")

    with pytest.raises(PermissionError, match="当前智能体无权执行工具"):
        await registry.execute_validated(tool, tool.validate({}), tool_context("未知"))

    assert gateway.calls == []


@pytest.mark.asyncio
async def test_execute_validated_refuses_control_tool() -> None:
    registry = build_default_registry()
    tool = registry.require("submit_evaluation")
    arguments = tool.validate(
        {
            "artifactKey": "task-1:write_chapter",
            "verdict": "pass",
            "summary": "通过",
        }
    )

    with pytest.raises(ValueError, match="控制工具只能由智能体运行时捕获"):
        await registry.execute_validated(tool, arguments, tool_context("校验"))


@pytest.mark.asyncio
async def test_execute_validated_refuses_tool_without_handler() -> None:
    registry = ToolRegistry()
    tool = ToolDefinition(
        name="missing_handler",
        description="缺少执行器",
        argumentsModel=EmptyArgs,
        permission=read_only_permission("novel.read"),
        toolKind="read",
        handler=None,
    )
    registry.register(tool)

    with pytest.raises(RuntimeError, match="工具缺少执行器"):
        await registry.execute_validated(tool, {}, tool_context("设定"))
