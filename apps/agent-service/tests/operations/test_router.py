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
