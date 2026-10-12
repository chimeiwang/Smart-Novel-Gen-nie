"""仅重建当前单节的完整冻结来源，不读取文件、不调度其他节。"""

from inkforge_contracts.execution import ExecutionStepRequest
from inkforge_contracts.style_execution import StylePortraitContextV2, StylePortraitStepInput


def portrait_context(request: ExecutionStepRequest) -> StylePortraitContextV2:
    if (
        request.workflow != "style"
        or request.operation != "portrait"
        or request.purpose != "generation"
        or request.novelId is not None
        or request.lane != "batch_media"
        or request.artifactId is not None
        or request.artifactRevision is not None
        or request.modelProfile.profile != "style.portrait.v2"
        or request.modelProfile.version != 2
        or request.outputSchema.name != "output.style_portrait_section.v2"
        or request.outputSchema.version != 2
        or request.evidenceBundle.policyVersion != "evidence.style.portrait.v1"
    ):
        raise ValueError("文风画像必须绑定用户级目标与精确纯文本执行资产")
    value = StylePortraitStepInput.model_validate(request.input)
    items = request.evidenceBundle.items
    if len(items) != 1:
        raise ValueError("画像只能读取唯一完整来源")
    item = items[0]
    if (
        item.resourceType != "style_portrait_context"
        or not item.exists
        or item.contentType != "json"
        or item.range is not None
    ):
        raise ValueError("画像必须读取完整 JSON 来源，不允许选区或摘要")
    context = StylePortraitContextV2.model_validate(item.contentJson)
    if (
        item.resourceId != context.styleId
        or context.section is not None
        and context.section != value.section
    ):
        raise ValueError("画像来源文风或单节目标不匹配")
    return context
