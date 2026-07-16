from __future__ import annotations

import pytest
from inkforge_agents.operations.contracts import CreativeOperation
from inkforge_agents.operations.router import route_creative_operation


class Classifier:
    def __init__(self, operation: CreativeOperation | Exception) -> None:
        self.operation = operation

    async def classify(self, user_message: str) -> CreativeOperation:
        del user_message
        if isinstance(self.operation, Exception):
            raise self.operation
        return self.operation


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "agent_id", "kind"),
    [
        ("@设定 修改角色", "设定", "revise_lore"),
        ("@剧情顾问 调整大纲", "剧情", "revise_outline"),
        ("@作家 续写", "写作", "write_chapter"),
        ("@校验员 检查冲突", "校验", "review_chapter"),
        ("@网文编辑 看商业性", "编辑", "review_chapter"),
    ],
)
async def test_agent_commands_map_to_default_operations(
    message: str, agent_id: str, kind: str
) -> None:
    result = await route_creative_operation(message)

    assert result.usedCommand is True
    assert result.operation.primaryAgent == agent_id
    assert result.operation.kind == kind


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "agent_id", "kind"),
    [
        (
            "@剧情 请为当前章节生成一份可应用的章节计划。请拆成场景节拍，"
            "明确每场的目标、冲突、涉及角色、伏笔、预估字数和验收标准。",
            "剧情",
            "plan_chapter",
        ),
        (
            "@写作 请找出当前章节最需要加强的一场戏并重写，重点补足目标、阻力、"
            "转折、代价和余波。重写内容进入待审核草案。",
            "写作",
            "rewrite_scene",
        ),
    ],
)
async def test_agent_command_prefers_matching_explicit_operation(
    message: str, agent_id: str, kind: str
) -> None:
    result = await route_creative_operation(message)

    assert result.usedCommand is True
    assert result.operation.primaryAgent == agent_id
    assert result.operation.kind == kind


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "kind"),
    [
        ("请为当前章节生成一份可应用的章节计划。", "plan_chapter"),
        ("请根据当前章节、已确认章节计划和大纲生成当前章节正文草案。", "write_chapter"),
        ("请找出当前章节最需要加强的一场戏并重写。", "rewrite_scene"),
        ("请从网文追读角度审核当前章节。", "review_chapter"),
        ("请检查当前章节正文与角色设定是否存在冲突和逻辑断裂。", "review_chapter"),
        ("请重点检查当前章节是否存在角色 OOC。", "review_chapter"),
    ],
)
async def test_product_tasks_use_automatic_operation_routing(
    message: str, kind: str
) -> None:
    result = await route_creative_operation(message)

    assert result.usedCommand is False
    assert result.operation.kind == kind


@pytest.mark.asyncio
async def test_removed_sync_lore_request_falls_back_to_question() -> None:
    message = (
        "@设定 根据当前章节及最近几章正文，维护设定库。"
        "请只提取明确发生的事实变化。"
    )

    result = await route_creative_operation(message)

    assert result.operation.kind == "answer_question"
    assert "已移除" in result.reasoning


@pytest.mark.asyncio
async def test_classifier_cannot_restore_removed_sync_lore_operation() -> None:
    operation = CreativeOperation(
        kind="sync_lore",
        targetType="lore",
        userGoal="同步设定",
        primaryAgent="设定",
        reviewers=["校验"],
        outputKind="sync_proposal",
        requiresArtifact=True,
        requiresUserApproval=True,
        confidence=0.9,
        reasoning="分类器命中同步设定",
    )

    result = await route_creative_operation("整理最近正文事实", Classifier(operation))

    assert result.operation.kind == "answer_question"
    assert "已移除" in result.reasoning


@pytest.mark.asyncio
async def test_low_confidence_or_failed_classification_falls_back_to_question() -> None:
    low_confidence = CreativeOperation(
        kind="write_chapter",
        targetType="chapter",
        userGoal="续写",
        primaryAgent="写作",
        reviewers=[],
        outputKind="chapter_text",
        requiresArtifact=True,
        requiresUserApproval=True,
        confidence=0.2,
        reasoning="不确定",
    )

    result = await route_creative_operation("也许写点什么", Classifier(low_confidence))
    assert result.operation.kind == "answer_question"

    result = await route_creative_operation("测试", Classifier(RuntimeError("失败")))
    assert result.operation.kind == "answer_question"


@pytest.mark.asyncio
async def test_classified_operation_is_normalized_by_definition() -> None:
    untrusted = CreativeOperation(
        kind="create_outline",
        targetType="unknown",
        userGoal="创建大纲",
        primaryAgent="编辑",
        reviewers=[],
        outputKind="chat_answer",
        requiresArtifact=False,
        requiresUserApproval=False,
        confidence=0.9,
        reasoning="用户要求创建大纲",
    )
    result = await route_creative_operation("创建大纲", Classifier(untrusted))

    assert result.operation.primaryAgent == "剧情"
    assert result.operation.reviewers == ["编辑"]
    assert result.operation.requiresArtifact is True
