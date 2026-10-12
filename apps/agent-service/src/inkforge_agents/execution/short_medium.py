"""中短篇单 Step 的冻结来源校验，不承担工作流、版本或分段调度。"""

from inkforge_contracts.execution import ExecutionStepRequest
from inkforge_contracts.short_medium_execution import (
    ShortMediumContextV2,
    ShortMediumPriorSegment,
    ShortMediumStepInput,
)

SHORT_MEDIUM_HANDLERS = {
    "generate_outline": ("plot.short_medium_outline.v2", "outline", "outline", "creative"),
    "generate_manuscript": (
        "writer.short_medium_manuscript.v2",
        "segment",
        "manuscript",
        "creative",
    ),
    "replace_selection": (
        "writer.short_medium_selection.v2",
        "replacement",
        "selection",
        "creative",
    ),
    "full_check": (
        "quality.short_medium_full_check.v2",
        "check_report",
        "full_check",
        "batch_media",
    ),
}


def validate_short_medium_request(request: ExecutionStepRequest) -> None:
    """只认完整已冻结快照；不回读 V1 Core 工具或可变工作稿。"""
    if request.operation not in SHORT_MEDIUM_HANDLERS or request.novelId is None:
        raise ValueError("中短篇必须绑定已实现操作与小说")
    profile, schema, evidence, lane = SHORT_MEDIUM_HANDLERS[request.operation]
    if (
        request.purpose != "generation"
        or request.lane != lane
        or request.modelProfile.profile != profile
        or request.modelProfile.version != 2
        or request.outputSchema.name != f"output.short_medium_{schema}.v2"
        or request.outputSchema.version != 2
        or request.evidenceBundle.policyVersion != f"evidence.short_medium.{evidence}.v1"
        or request.artifactId is not None
        or request.artifactRevision is not None
    ):
        raise ValueError("中短篇 Step 的精确操作与执行资产身份不一致")
    step = ShortMediumStepInput.model_validate(request.input)
    items = request.evidenceBundle.items
    if not items or len(items) != step.segmentIndex + 1:
        raise ValueError("中短篇来源只能包含唯一 context 与全部先前段")
    context_item = items[0]
    if (
        context_item.resourceType != "short_medium_context"
        or context_item.resourceId != request.novelId
    ):
        raise ValueError("中短篇首项必须是同小说的唯一完整 context")
    for item in items:
        if not item.exists or item.contentType != "json" or item.range is not None:
            raise ValueError("中短篇必须使用完整 JSON Evidence，不能使用摘要或范围")
    context = ShortMediumContextV2.model_validate(context_item.contentJson)
    if context.operation != request.operation or step.segmentCount != context.segment_count:
        raise ValueError("中短篇操作或段数不匹配冻结来源")
    producers: set[str] = set()
    for index, item in enumerate(items[1:]):
        if (
            item.resourceType != "short_medium_segment"
            or item.resourceId in producers
            or item.resourceId == request.stepId
        ):
            raise ValueError("先前段必须绑定唯一已完成的来源 Step")
        producers.add(item.resourceId)
        segment = ShortMediumPriorSegment.model_validate(item.contentJson)
        if segment.index != index:
            raise ValueError("先前段存在重复、缺失或顺序错误")
