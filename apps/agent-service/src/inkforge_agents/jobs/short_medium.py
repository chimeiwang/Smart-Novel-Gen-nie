from __future__ import annotations

import json
import math
import re
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol, cast

from inkforge_contracts.short_medium import (
    ShortMediumCheckResult,
    ShortMediumDocumentResult,
    ShortMediumReplacementResult,
    ShortMediumRunPayload,
    validate_short_medium_result,
)
from pydantic import JsonValue, ValidationError

from ..clients.core import RunResource
from ..providers.base import ModelMessage, ModelTurnRequest, ModelTurnResult
from ..queue.consumer import NonRetryableJobError
from ..queue.repository import QueueJob
from ..runtime.model_runtime import ModelCallContext, ModelRuntime

_SINGLE_CALL_LIMIT = 15_000
_STATIC_PROMPT = """你是 InkForge 的中短篇写作执行器，只处理 6000 到 80000 字作品。
遵循中短篇方法：尽早进入变化，围绕单中心冲突组织故事，压缩人物和线索，把注意力集中在一个核心人物和一条主要因果链；
人物、设定、线索和场景都必须服务于冲突或结局，删除只负责解释、装饰或为续集铺垫的内容；
升级依靠选择、代价和后果，而不是堆叠事件；高潮必须迫使人物作出有损失的决定；
结尾兑现开篇建立的悬念、情感或命题，可以留余味，但不能把核心解决推给下一部。
忠实保留用户明确给出的开头、结尾、事实和禁区；不确定处宁可保留，不擅自补成套路。
只执行当前 operation，不启动评审、返工或其他 Agent。不得静默截断输入或输出。"""


class CoreClientPort(Protocol):
    async def call_tool(
        self,
        resource: RunResource,
        agent_id: str,
        tool_name: str,
        arguments: dict[str, JsonValue],
    ) -> dict[str, Any]: ...

    async def send_event(
        self,
        resource: RunResource,
        *,
        sequence: int,
        event: str,
        data: dict[str, Any],
    ) -> None: ...

    async def save_checkpoint(
        self,
        resource: RunResource,
        *,
        sequence: int,
        checkpoint: dict[str, Any],
    ) -> None: ...

    async def complete(
        self,
        resource: RunResource,
        *,
        sequence: int,
        result: dict[str, Any],
    ) -> None: ...

    async def fail(
        self,
        resource: RunResource,
        *,
        sequence: int,
        code: str,
        message: str,
        recoverable: bool = True,
    ) -> None: ...


class GeneratorPort(Protocol):
    async def generate(
        self,
        resource: RunResource,
        request: ModelTurnRequest,
    ) -> ModelTurnResult: ...


WritingHandler = Callable[[QueueJob], Awaitable[None]]


class WritingJobDispatcher:
    def __init__(
        self,
        long_serial: WritingHandler,
        short_medium: WritingHandler,
    ) -> None:
        self._long_serial = long_serial
        self._short_medium = short_medium

    async def __call__(self, job: QueueJob) -> None:
        if job.payload.get("workflow") == "short_medium":
            await self._short_medium(job)
            return
        await self._long_serial(job)


class ModelShortMediumGenerator:
    def __init__(self, runtime: ModelRuntime, *, max_output_tokens: int) -> None:
        self._runtime = runtime
        self._max_output_tokens = max_output_tokens

    async def generate(
        self,
        resource: RunResource,
        request: ModelTurnRequest,
    ) -> ModelTurnResult:
        return await self._runtime.run_turn(
            request.model_copy(
                update={"maxOutputTokens": self._max_output_tokens},
            ),
            context=ModelCallContext(
                userId=resource.userId,
                novelId=resource.novelId,
                taskId=resource.taskId,
                runId=resource.runId,
                agentId="写作",
            ),
        )

class ShortMediumWritingJobHandler:
    def __init__(self, core: CoreClientPort, generator: GeneratorPort) -> None:
        self._core = core
        self._generator = generator

    async def __call__(self, job: QueueJob) -> None:
        if job.kind != "writing":
            raise ValueError("中短篇处理器收到非写作任务")
        try:
            payload = ShortMediumRunPayload.model_validate(job.payload)
        except ValidationError as exc:
            raise NonRetryableJobError("中短篇任务载荷无效") from exc

        resource = _resource(job)
        context = await self._core.call_tool(
            resource,
            "写作",
            "get_writing_context",
            {},
        )
        snapshot = _owned_snapshot(context, job)
        try:
            if snapshot is not None and snapshot.get("phase") == "completed":
                await self._replay_completed(resource, snapshot)
                return
            await self._run(resource, payload, snapshot)
        except _ShortMediumFailure as exc:
            sequence = exc.sequence or _next_sequence(snapshot)
            await self._core.fail(
                resource,
                sequence=sequence,
                code=exc.code,
                message=str(exc),
                recoverable=False,
            )
            raise NonRetryableJobError("中短篇运行失败已上报核心服务") from exc

    async def _run(
        self,
        resource: RunResource,
        payload: ShortMediumRunPayload,
        snapshot: dict[str, Any] | None,
    ) -> None:
        sequence = int(snapshot.get("eventSequence", 0)) if snapshot is not None else 0
        try:
            segment_count = _segment_count(payload)
            segments = _validated_segments(snapshot, segment_count)
            if snapshot is not None and snapshot.get("segmentCount") != segment_count:
                raise _ShortMediumFailure(
                    "SEGMENT_CHECKPOINT_INVALID",
                    "分段 checkpoint 与当前任务目标不一致",
                )
        except _ShortMediumFailure as exc:
            exc.sequence = sequence + 1
            raise

        sequence += 1
        await self._core.send_event(
            resource,
            sequence=sequence,
            event="agent_start",
            data={"agentId": "写作", "operation": payload.operation},
        )
        try:
            for index in range(len(segments), segment_count):
                request = _build_request(payload, segments, index, segment_count)
                turn = await self._generator.generate(resource, request)
                content = _validated_content(turn)
                segments.append({"index": index, "content": content})
                completed = len(segments) == segment_count
                result = _build_result(payload, segments) if completed else None
                sequence += 1
                checkpoint: dict[str, Any] = {
                    "workflow": "short_medium",
                    "callbackJobId": resource.jobId,
                    "phase": "completed" if completed else "generating",
                    "eventSequence": sequence,
                    "operation": payload.operation,
                    "segmentCount": segment_count,
                    "completedSegmentCount": len(segments),
                    "segments": segments,
                }
                if result is not None:
                    checkpoint["result"] = result
                await self._core.save_checkpoint(
                    resource,
                    sequence=sequence,
                    checkpoint=checkpoint,
                )
        except _ShortMediumFailure as exc:
            exc.sequence = sequence + 1
            raise

        result = _build_result(payload, segments)
        sequence += 1
        await self._core.complete(resource, sequence=sequence, result=result)

    async def _replay_completed(
        self,
        resource: RunResource,
        snapshot: dict[str, Any],
    ) -> None:
        segment_count = snapshot.get("segmentCount")
        if isinstance(segment_count, bool) or not isinstance(segment_count, int):
            raise _ShortMediumFailure(
                "SEGMENT_CHECKPOINT_INVALID",
                "完成 checkpoint 缺少分段总数",
            )
        segments = _validated_segments(snapshot, segment_count)
        if len(segments) != segment_count:
            raise _ShortMediumFailure(
                "SEGMENT_CHECKPOINT_INVALID",
                "完成 checkpoint 存在缺失分段",
            )
        result = snapshot.get("result")
        if not isinstance(result, dict):
            raise _ShortMediumFailure(
                "SEGMENT_CHECKPOINT_INVALID",
                "完成 checkpoint 缺少最终结果",
            )
        try:
            validate_short_medium_result(result)
        except (TypeError, ValueError, ValidationError) as exc:
            raise _ShortMediumFailure(
                "SEGMENT_CHECKPOINT_INVALID",
                "完成 checkpoint 的最终结果无效",
            ) from exc
        await self._core.complete(
            resource,
            sequence=int(snapshot.get("eventSequence", 0)) + 1,
            result=result,
        )


def _resource(job: QueueJob) -> RunResource:
    return RunResource(
        userId=job.userId,
        novelId=job.novelId,
        taskId=job.taskId,
        runId=job.runId,
        jobId=job.jobId,
    )


def _owned_snapshot(
    context: Mapping[str, Any],
    job: QueueJob,
) -> dict[str, Any] | None:
    planning = context.get("planning")
    if not isinstance(planning, dict):
        return None
    snapshot = planning.get("graphState")
    if (
        isinstance(snapshot, dict)
        and snapshot.get("workflow") == "short_medium"
        and snapshot.get("callbackJobId") == job.jobId
    ):
        return snapshot
    return None


def _next_sequence(snapshot: Mapping[str, Any] | None) -> int:
    if snapshot is None:
        return 1
    value = snapshot.get("eventSequence", 0)
    return int(value) + 1 if isinstance(value, int) else 1


def _segment_count(payload: ShortMediumRunPayload) -> int:
    if payload.operation != "generate_manuscript":
        return 1
    target = payload.targetTotalWordCount
    if target is None:
        raise _ShortMediumFailure(
            "TARGET_WORD_COUNT_MISSING",
            "正文生成缺少目标字数",
        )
    return max(1, math.ceil(target / _SINGLE_CALL_LIMIT))


def _validated_segments(
    snapshot: Mapping[str, Any] | None,
    segment_count: int,
) -> list[dict[str, Any]]:
    if snapshot is None:
        return []
    raw_segments = snapshot.get("segments")
    if not isinstance(raw_segments, list):
        raise _ShortMediumFailure(
            "SEGMENT_CHECKPOINT_INVALID",
            "分段 checkpoint 缺少分段清单",
        )
    segments: list[dict[str, Any]] = []
    for expected_index, item in enumerate(raw_segments):
        if (
            not isinstance(item, dict)
            or item.get("index") != expected_index
            or not isinstance(item.get("content"), str)
            or not item["content"]
        ):
            raise _ShortMediumFailure(
                "SEGMENT_CHECKPOINT_INVALID",
                "分段 checkpoint 存在重复、缺失或顺序错误",
            )
        segments.append({"index": expected_index, "content": item["content"]})
    if len(segments) > segment_count:
        raise _ShortMediumFailure(
            "SEGMENT_CHECKPOINT_INVALID",
            "分段 checkpoint 超出分段总数",
        )
    return segments


def _build_request(
    payload: ShortMediumRunPayload,
    segments: list[dict[str, Any]],
    index: int,
    segment_count: int,
) -> ModelTurnRequest:
    operation_brief = {
        "generate_outline": (
            "输出一份完整、可人工编辑的故事蓝图，不使用长篇卷、阶段或章节组。"
            "蓝图至少明确人物当前处境与欲望、触发变化、阻力与升级、不可逆转折、高潮选择、"
            "实际代价和结尾兑现；所有节点写清前因后果，不写空泛创作建议。"
        ),
        "generate_manuscript": (
            f"只输出正文内部第 {index + 1}/{segment_count} 段；"
            "使用场景、行动、误判和后果呈现信息，避免先解释世界再开始故事；"
            "与已完成正文自然衔接，不总结、不重复既有段落。"
        ),
        "replace_selection": (
            "只返回替换文本，不返回完整大纲或正文，不复述前后文，选区外内容不得改变。"
        ),
        "full_check": (
            "只输出检查报告，给出具体位置、证据和建议，不改写正文。"
        ),
    }[payload.operation]
    prompt_context = {
        "operation": payload.operation,
        "operationBrief": operation_brief,
        "request": payload.model_dump(mode="json"),
        "completedContent": "".join(str(item["content"]) for item in segments),
    }
    return ModelTurnRequest(
        messages=[
            ModelMessage(role="system", content=_STATIC_PROMPT),
            ModelMessage(
                role="user",
                content=json.dumps(prompt_context, ensure_ascii=False),
            ),
        ],
        tools=[],
        maxOutputTokens=384_000,
    )


def _validated_content(turn: ModelTurnResult) -> str:
    if turn.finishReason == "length":
        raise _ShortMediumFailure("MODEL_OUTPUT_TRUNCATED", "模型输出因长度被截断")
    if turn.finishReason == "content_filter":
        raise _ShortMediumFailure("MODEL_OUTPUT_FILTERED", "模型输出被内容过滤")
    if turn.finishReason != "stop" or turn.toolCalls:
        raise _ShortMediumFailure("MODEL_PROTOCOL_INVALID", "模型没有返回完整纯文本结果")
    if not turn.content:
        raise _ShortMediumFailure("MODEL_OUTPUT_EMPTY", "模型返回空内容")
    return turn.content


def _build_result(
    payload: ShortMediumRunPayload,
    segments: list[dict[str, Any]],
) -> dict[str, Any]:
    content = "".join(str(item["content"]) for item in segments)
    if payload.operation == "generate_outline":
        return ShortMediumDocumentResult(
            resultType="short_medium_document",
            operation="generate_outline",
            documentType="outline",
            content=content,
        ).model_dump(mode="json")
    if payload.operation == "generate_manuscript":
        length = _count_text_length(content)
        if length < 6_000 or length > 80_000:
            raise _ShortMediumFailure(
                "MANUSCRIPT_LENGTH_INVALID",
                f"完整正文字数 {length} 不在 6000 到 80000 之间",
            )
        return ShortMediumDocumentResult(
            resultType="short_medium_document",
            operation="generate_manuscript",
            documentType="manuscript",
            content=content,
            sourceOutlineVersionId=payload.sourceOutlineVersionId,
        ).model_dump(mode="json")
    if payload.operation == "replace_selection":
        return ShortMediumReplacementResult(
            resultType="short_medium_replacement",
            operation="replace_selection",
            documentType=payload.documentType,
            replacement=content,
            baseVersionId=cast(str, payload.baseVersionId),
            baseContentHash=cast(str, payload.baseContentHash),
            selectionStart=cast(int, payload.selectionStart),
            selectionEnd=cast(int, payload.selectionEnd),
            selectedTextHash=cast(str, payload.selectedTextHash),
        ).model_dump(mode="json")
    return ShortMediumCheckResult(
        resultType="short_medium_check",
        operation="full_check",
        documentType="manuscript",
        baseVersionId=cast(str, payload.baseVersionId),
        report={"text": content},
    ).model_dump(mode="json")


def _count_text_length(content: str) -> int:
    return len(re.sub(r"[\s\ufeff]", "", content))


class _ShortMediumFailure(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.sequence: int | None = None
