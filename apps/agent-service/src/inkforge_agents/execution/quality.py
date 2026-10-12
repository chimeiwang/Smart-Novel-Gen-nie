"""质量单次工具响应校验；不运行工具循环、不保存坏参数、不决定工作流接续。"""

from inkforge_contracts.execution import ExecutionStepRequest
from inkforge_contracts.quality import ConsistencyQualityReport
from inkforge_contracts.quality_execution import QualityContextV2, QualityStepInput
from pydantic import JsonValue, ValidationError

from ..providers.base import ModelTurnResult

QUALITY_ROUTE = "quality_strict_tool_v1"
QUALITY_TOOL = "submit_quality_report"
QUALITY_CORRECTION_REQUIRED = "MODEL_TOOL_PROTOCOL_CORRECTION_REQUIRED"


def validate_quality_request(request: ExecutionStepRequest) -> None:
    correction = request.purpose == "protocol_correction"
    if (
        request.workflow != "quality"
        or request.operation != "consistency"
        or request.purpose not in {"generation", "protocol_correction"}
        or request.novelId is None
        or request.lane != "interactive"
        or request.modelProfile.profile
        != ("system.quality_protocol_corrector.v2" if correction else "quality.consistency.v2")
        or request.modelProfile.version != 2
        or request.outputSchema.name != "output.consistency_quality_report.v2"
        or request.outputSchema.version != 2
        or request.evidenceBundle.policyVersion != "evidence.quality.consistency.v1"
        or request.artifactId is not None
        or request.artifactRevision is not None
    ):
        raise ValueError("质量 Step 的操作、用途或冻结资产身份不一致")
    value = QualityStepInput.model_validate(request.input)
    if correction != (value.failedStepId is not None) or value.failedStepId == request.stepId:
        raise ValueError("质量纠正只能绑定另外一个失败 Step")
    items = request.evidenceBundle.items
    if len(items) != 1:
        raise ValueError("质量检查必须只有唯一完整正文上下文")
    item = items[0]
    if (
        not item.exists
        or item.contentType != "json"
        or item.range is not None
        or item.resourceType != "quality_context"
    ):
        raise ValueError("质量检查必须读取完整 JSON Evidence")
    context = QualityContextV2.model_validate(item.contentJson)
    if item.resourceId != context.checkId or context.novelId != request.novelId:
        raise ValueError("质量来源必须属于当前小说和检查项")
    if value.userInstruction != (context.message or "检查本章一致性"):
        raise ValueError("质量检查指令必须等于冻结原始指令")


def quality_response(result: ModelTurnResult) -> tuple[dict[str, JsonValue] | None, bool]:
    """返回完整合法报告或是否可进行一次独立纠正；从不返回原始无效输出。"""
    if result.invalidToolCallCount:
        eligible = all(
            name == QUALITY_TOOL
            and code in {"json_decode_error", "provider_strict_schema_violation"}
            for name, code in zip(
                result.invalidToolCallNames, result.invalidToolCallCodes, strict=True
            )
        )
        return None, eligible
    if len(result.toolCalls) != 1:
        return None, False
    call = result.toolCalls[0]
    if call.name != QUALITY_TOOL or not call.id.strip():
        return None, False
    try:
        # 不能先以更严格的 JSON Schema 拒绝旧 Pydantic 本就接受的数值转换。
        value = ConsistencyQualityReport.model_validate(call.arguments)
    except ValidationError:
        return None, True
    return value.model_dump(mode="json"), False
