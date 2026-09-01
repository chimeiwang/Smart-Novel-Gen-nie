from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from inkforge_agents.clients.core import CoreServiceError, RunResource
from inkforge_agents.jobs.short_medium import (
    ModelShortMediumGenerator,
    ShortMediumWritingJobHandler,
)
from inkforge_agents.observability.human_workflow_log import HumanWorkflowLog
from inkforge_agents.observability.model_observer import WorkflowModelObserver
from inkforge_agents.providers.base import (
    ModelExecutionPolicy,
    ModelMessage,
    ModelTurnRequest,
    ModelTurnResult,
    ModelUsage,
)
from inkforge_agents.providers.fake import FakeModelProvider
from inkforge_agents.queue.consumer import NonRetryableJobError
from inkforge_agents.queue.repository import QueueJob
from inkforge_agents.runtime.model_policy import (
    CREATIVE_HIGH,
    LEGACY_PROVIDER_DEFAULT,
    REPORT_NO_THINKING,
)
from inkforge_agents.runtime.model_runtime import ModelLane, ModelRuntime


class Core:
    def __init__(
        self,
        graph_state: dict[str, Any] | None = None,
        *,
        context_failure: Exception | None = None,
        callback_failure: Exception | None = None,
    ) -> None:
        self.graph_state = graph_state
        self.context_failure = context_failure
        self.callback_failure = callback_failure
        self.events: list[tuple[str | None, int, str]] = []
        self.checkpoints: list[tuple[str | None, int, dict[str, Any]]] = []
        self.completions: list[tuple[str | None, int, dict[str, Any]]] = []
        self.failures: list[tuple[str | None, int, str, bool]] = []

    async def call_tool(
        self,
        resource: object,
        agent_id: str,
        tool_name: str,
        arguments: dict[str, object],
    ) -> dict[str, Any]:
        del resource, arguments
        if self.context_failure is not None:
            raise self.context_failure
        assert agent_id == "写作"
        assert tool_name == "get_writing_context"
        return {
            "planning": {
                "graphState": self.graph_state,
                "authoritativeContent": "Core 权威内容",
            }
        }

    async def send_event(
        self,
        resource: Any,
        *,
        sequence: int,
        event: str,
        data: dict[str, Any],
    ) -> None:
        del data
        self.events.append((resource.jobId, sequence, event))

    async def save_checkpoint(
        self,
        resource: Any,
        *,
        sequence: int,
        checkpoint: dict[str, Any],
    ) -> None:
        self.checkpoints.append((resource.jobId, sequence, checkpoint))

    async def complete(
        self,
        resource: Any,
        *,
        sequence: int,
        result: dict[str, Any],
    ) -> None:
        self.completions.append((resource.jobId, sequence, result))

    async def fail(
        self,
        resource: Any,
        *,
        sequence: int,
        code: str,
        message: str,
        recoverable: bool = True,
    ) -> None:
        del message
        self.failures.append((resource.jobId, sequence, code, recoverable))
        if self.callback_failure is not None:
            raise self.callback_failure


class Generator:
    def __init__(
        self,
        outputs: list[str],
        *,
        finish_reason: str = "stop",
        tool_calls: bool = False,
    ) -> None:
        self.outputs = list(outputs)
        self.finish_reason = finish_reason
        self.tool_calls = tool_calls
        self.requests: list[Any] = []

    async def generate(self, resource: object, request: Any) -> ModelTurnResult:
        del resource
        self.requests.append(request)
        content = self.outputs.pop(0)
        return ModelTurnResult(
            content=content,
            toolCalls=(
                [{"id": "call-1", "name": "unexpected", "arguments": {}}]
                if self.tool_calls
                else []
            ),
            finishReason=self.finish_reason,
            rawFinishReason=self.finish_reason,
            usage=ModelUsage(
                promptTokens=1,
                completionTokens=len(content),
                totalTokens=len(content) + 1,
            ),
        )


class RaisingGenerator:
    def __init__(self, failure: BaseException) -> None:
        self.failure = failure

    async def generate(
        self,
        resource: object,
        request: object,
    ) -> ModelTurnResult:
        del resource, request
        raise self.failure


class FaultyWorkflowLog:
    def __init__(
        self,
        *,
        start_failure: Exception | None = None,
        finish_failure: Exception | None = None,
    ) -> None:
        self.start_failure = start_failure
        self.finish_failure = finish_failure
        self.started = 0
        self.finished: list[tuple[str, str]] = []

    def start_run(self, **kwargs: object) -> None:
        del kwargs
        self.started += 1
        if self.start_failure is not None:
            raise self.start_failure

    def finish_run(self, run_id: str, status: str) -> None:
        self.finished.append((run_id, status))
        if self.finish_failure is not None:
            raise self.finish_failure

    def record_state(
        self,
        run_id: str,
        node: str,
        changes: dict[str, Any],
    ) -> None:
        del run_id, node, changes


def manuscript_job(target: int) -> QueueJob:
    source_outline_content = "不可变蓝图"
    return QueueJob(
        jobId="job-short-1",
        kind="writing",
        runId="run-short-1",
        taskId="task-short-1",
        novelId="novel-1",
        userId="user-1",
        priority=10,
        payload={
            "workflow": "short_medium",
            "operation": "generate_manuscript",
            "documentType": "manuscript",
            "chapterId": "chapter-1",
            "sourceOutlineVersionId": "outline-version-1",
            "sourceOutlineContent": source_outline_content,
            "sourceOutlineContentHash": hashlib.sha256(
                source_outline_content.encode("utf-8")
            ).hexdigest(),
            "targetTotalWordCount": target,
        },
        createdAt=datetime.now(UTC),
    )


def outline_job() -> QueueJob:
    return manuscript_job(15_000).model_copy(
        update={
            "payload": {
                "workflow": "short_medium",
                "operation": "generate_outline",
                "documentType": "outline",
                "targetTotalWordCount": 15_000,
                "sourceKind": "idea",
                "sourceText": "一段灵感",
            }
        }
    )


@pytest.mark.asyncio
async def test_real_model_runtime_chain_writes_and_finishes_workflow_log(
    tmp_path: Path,
) -> None:
    core = Core()
    workflow_log = HumanWorkflowLog(tmp_path)
    runtime = ModelRuntime(
        FakeModelProvider(),
        observer=WorkflowModelObserver(workflow_log),
    )
    handler = ShortMediumWritingJobHandler(
        core,
        ModelShortMediumGenerator(runtime, max_output_tokens=12_345),
        workflow_log=workflow_log,
    )

    await handler(outline_job())

    runs = workflow_log.list_runs("user-1")
    assert len(core.checkpoints) == 1
    assert len(core.completions) == 1
    assert core.failures == []
    assert len(runs) == 1
    assert runs[0].status == "完成"
    assert "模拟模型已完成本轮处理。" in workflow_log.read_run(
        "run-short-1",
        "user-1",
    ).content


@pytest.mark.asyncio
async def test_unknown_runtime_failure_is_reported_with_next_sequence(
    tmp_path: Path,
) -> None:
    core = Core()
    workflow_log = HumanWorkflowLog(tmp_path)
    handler = ShortMediumWritingJobHandler(
        core,
        RaisingGenerator(RuntimeError("模型运行异常")),
        workflow_log=workflow_log,
    )

    with pytest.raises(NonRetryableJobError):
        await handler(manuscript_job(15_000))

    assert core.completions == []
    assert core.failures == [
        ("job-short-1", 2, "SHORT_MEDIUM_RUN_FAILED", False)
    ]
    assert workflow_log.list_runs("user-1")[0].status == "错误"


@pytest.mark.parametrize("attribute", ["recoverable", "retryable"])
@pytest.mark.asyncio
async def test_explicit_retry_failure_is_preserved_and_retry_appends_log_segment(
    tmp_path: Path,
    attribute: str,
) -> None:
    failure_type = type("RetryFailure", (RuntimeError,), {attribute: True})
    failure = failure_type("依赖服务暂时不可用")
    core = Core()
    workflow_log = HumanWorkflowLog(tmp_path)
    handler = ShortMediumWritingJobHandler(
        core,
        RaisingGenerator(failure),
        workflow_log=workflow_log,
    )

    with pytest.raises(failure_type) as caught:
        await handler(outline_job())

    assert caught.value is failure
    assert core.failures == []
    assert workflow_log.list_runs("user-1")[0].status == "等待重试"
    await ShortMediumWritingJobHandler(
        core,
        Generator(["故事蓝图"]),
        workflow_log=workflow_log,
    )(outline_job())

    detail = workflow_log.read_run("run-short-1", "user-1")
    assert detail.summary.status == "完成"
    assert detail.content.count("中短篇：generate_outline") == 2


@pytest.mark.asyncio
async def test_failure_callback_transport_error_remains_recoverable(
) -> None:
    callback_failure = CoreServiceError("核心服务暂时不可用", recoverable=True)
    core = Core(callback_failure=callback_failure)
    workflow_log = FaultyWorkflowLog(
        finish_failure=LookupError("运行日志不存在"),
    )
    handler = ShortMediumWritingJobHandler(
        core,
        RaisingGenerator(RuntimeError("模型运行异常")),
        workflow_log=workflow_log,
    )

    with pytest.raises(CoreServiceError) as caught:
        await handler(manuscript_job(15_000))

    assert caught.value is callback_failure
    assert core.failures == [
        ("job-short-1", 2, "SHORT_MEDIUM_RUN_FAILED", False)
    ]
    assert workflow_log.finished == [("run-short-1", "错误")]


@pytest.mark.parametrize(
    ("stage", "expected_code"),
    [
        ("payload", "SHORT_MEDIUM_PAYLOAD_INVALID"),
        ("context", "SHORT_MEDIUM_RUN_FAILED"),
    ],
)
@pytest.mark.asyncio
async def test_pre_run_failure_is_reported_instead_of_leaving_processing(
    tmp_path: Path,
    stage: str,
    expected_code: str,
) -> None:
    core = Core(
        context_failure=(
            RuntimeError("上下文响应异常") if stage == "context" else None
        )
    )
    workflow_log = HumanWorkflowLog(tmp_path)
    job = outline_job()
    if stage == "payload":
        job.payload.pop("operation")
    handler = ShortMediumWritingJobHandler(
        core,
        Generator([]),
        workflow_log=workflow_log,
    )

    with pytest.raises(NonRetryableJobError):
        await handler(job)

    assert core.failures == [("job-short-1", 1, expected_code, False)]
    assert workflow_log.list_runs("user-1")[0].status == "错误"


@pytest.mark.asyncio
async def test_start_log_failure_settles_core_without_running_model() -> None:
    core = Core()
    generator = Generator([])
    workflow_log = FaultyWorkflowLog(
        start_failure=OSError("日志目录不可写"),
        finish_failure=LookupError("运行日志不存在"),
    )
    handler = ShortMediumWritingJobHandler(
        core,
        generator,
        workflow_log=workflow_log,
    )

    with pytest.raises(NonRetryableJobError):
        await handler(outline_job())

    assert generator.requests == []
    assert core.failures == [
        ("job-short-1", 1, "SHORT_MEDIUM_RUN_FAILED", False)
    ]
    assert workflow_log.finished == [("run-short-1", "错误")]


@pytest.mark.asyncio
async def test_finish_log_failure_does_not_override_completed_result() -> None:
    core = Core()
    workflow_log = FaultyWorkflowLog(
        finish_failure=LookupError("运行日志不存在"),
    )
    handler = ShortMediumWritingJobHandler(
        core,
        Generator(["故事蓝图"]),
        workflow_log=workflow_log,
    )

    await handler(outline_job())

    assert len(core.completions) == 1
    assert core.failures == []
    assert workflow_log.finished == [("run-short-1", "完成")]


@pytest.mark.asyncio
async def test_cancelled_error_is_preserved_without_failure_or_fake_finish() -> None:
    core = Core()
    cancellation = asyncio.CancelledError()
    workflow_log = FaultyWorkflowLog()
    handler = ShortMediumWritingJobHandler(
        core,
        RaisingGenerator(cancellation),
        workflow_log=workflow_log,
    )

    with pytest.raises(asyncio.CancelledError) as caught:
        await handler(outline_job())

    assert caught.value is cancellation
    assert core.failures == []
    assert workflow_log.started == 1
    assert workflow_log.finished == []


@pytest.mark.asyncio
async def test_15000_chars_uses_one_model_call_and_one_final_result() -> None:
    core = Core()
    generator = Generator(["甲" * 6_000])
    handler = ShortMediumWritingJobHandler(core, generator)

    await handler(manuscript_job(15_000))

    assert len(generator.requests) == 1
    assert len(core.completions) == 1
    assert core.completions[0][2]["resultType"] == "short_medium_document"
    assert core.completions[0][2]["content"] == "甲" * 6_000
    assert all(job_id == "job-short-1" for job_id, _, _ in core.checkpoints)
    assert all(job_id == "job-short-1" for job_id, _, _ in core.completions)


@pytest.mark.asyncio
async def test_single_call_manuscript_prompt_uses_complete_creation_contract() -> None:
    core = Core()
    generator = Generator(["甲" * 6_000])
    handler = ShortMediumWritingJobHandler(core, generator)

    await handler(manuscript_job(8_000))

    prompt_context = json.loads(generator.requests[0].messages[1].content)
    operation_brief = prompt_context["operationBrief"]
    assert "创作新正文" in operation_brief
    assert "全文修订" not in operation_brief
    assert "一次性输出完整正文" in operation_brief
    assert "同一事件只完整叙述一次" in operation_brief
    assert (
        "依次服从本轮 userInstruction、当前 sourceOutlineContent、"
        "baseContent 和通用创作原则"
    ) in operation_brief
    assert "确保时间、空间和因果成立" in operation_brief
    assert "目标字数和蓝图局部估算只用于控制结构比例" in operation_brief
    assert "不因接近目标而截断场景" in operation_brief
    assert "只输出作品正文" in operation_brief
    assert "不输出幕、高潮、写作说明等蓝图标签" in operation_brief
    assert "正文换行属于硬性交付格式而非可选风格" in operation_brief
    assert "相邻普通自然段必须用一个实际换行（\\n）直接分隔" in operation_brief
    assert "禁止用两个连续换行（\\n\\n）形成空白行" in operation_brief
    assert "只有叙事发生明确的场景或时间跳转时才使用一个空白行" in operation_brief
    assert (
        "不输出作品标题、Markdown 标题、分幕标题或结构编号"
        in operation_brief
    )
    assert "完成蓝图指定的核心兑现和结尾动作后立即结束" in operation_brief


@pytest.mark.asyncio
async def test_manuscript_prompt_uses_base_content_as_revision_draft() -> None:
    core = Core()
    generator = Generator(["乙" * 6_000])
    handler = ShortMediumWritingJobHandler(core, generator)
    base_content = "原正文"
    user_instruction = "压缩重复内容并修复因果"
    job = manuscript_job(8_000)
    job.payload.update(
        {
            "baseVersionId": "manuscript-version-1",
            "baseContent": base_content,
            "baseContentHash": hashlib.sha256(
                base_content.encode("utf-8")
            ).hexdigest(),
            "userInstruction": user_instruction,
        }
    )

    await handler(job)

    prompt_context = json.loads(generator.requests[0].messages[1].content)
    operation_brief = prompt_context["operationBrief"]
    assert "全文修订" in operation_brief
    assert "以 baseContent 为内容底稿" in operation_brief
    assert "保留仍然有效的情节、事实和措辞" in operation_brief
    assert "正文内容只为满足本轮 userInstruction 和当前蓝图进行必要改动" in operation_brief
    assert "修订后的完整正文" in operation_brief
    assert "创作新正文" not in operation_brief
    assert "不存在正文基础版本" not in operation_brief
    assert "baseContent 只作为内容和叙事依据，不作为排版模板" in operation_brief
    assert "现有空白行默认不表示场景或时间跳转" in operation_brief
    assert "重新排版并完整输出" not in operation_brief
    assert (
        "除必须逐字保留的固定前后缀外，baseContent 中用于分隔普通自然段的"
        "两个连续换行（\\n\\n）必须改为一个实际换行（\\n）"
    ) in operation_brief
    assert "正文内容即使无需改动也必须执行这项格式转换" in operation_brief
    assert "正文换行属于硬性交付格式而非可选风格" in operation_brief
    assert "相邻普通自然段必须用一个实际换行（\\n）直接分隔" in operation_brief
    assert "禁止用两个连续换行（\\n\\n）形成空白行" in operation_brief
    assert "只有叙事发生明确的场景或时间跳转时才使用一个空白行" in operation_brief
    assert (
        "不输出作品标题、Markdown 标题、分幕标题或结构编号"
        in operation_brief
    )
    assert prompt_context["request"]["baseContent"] == base_content
    assert prompt_context["request"]["userInstruction"] == user_instruction


@pytest.mark.asyncio
async def test_generate_outline_returns_one_document_result() -> None:
    core = Core()
    generator = Generator(["故事蓝图"])
    handler = ShortMediumWritingJobHandler(core, generator)
    job = manuscript_job(15_000).model_copy(
        update={
            "payload": {
                "workflow": "short_medium",
                "operation": "generate_outline",
                "documentType": "outline",
                "targetTotalWordCount": 15_000,
                "sourceKind": "idea",
                "sourceText": "一段灵感",
            }
        }
    )

    await handler(job)

    assert len(generator.requests) == 1
    assert core.completions[0][2] == {
        "resultType": "short_medium_document",
        "operation": "generate_outline",
        "documentType": "outline",
        "content": "故事蓝图",
        "sourceOutlineVersionId": None,
    }


@pytest.mark.asyncio
async def test_prompt_uses_run_snapshot_instead_of_mutable_core_document_context() -> None:
    core = Core()
    generator = Generator(["甲" * 6_000])
    handler = ShortMediumWritingJobHandler(core, generator)

    await handler(manuscript_job(15_000))

    prompt = "\n".join(message.content for message in generator.requests[0].messages)
    assert "不可变蓝图" in prompt
    assert "Core 权威内容" not in prompt


@pytest.mark.parametrize(
    ("source_kind", "required_text"),
    [
        ("opening", "逐字作为完整正文前缀"),
        ("ending", "逐字作为完整正文后缀"),
    ],
)
@pytest.mark.asyncio
async def test_prompt_marks_opening_and_ending_as_fixed_boundaries(
    source_kind: str,
    required_text: str,
) -> None:
    core = Core()
    generator = Generator(["固定素材" + "甲" * 6_000])
    handler = ShortMediumWritingJobHandler(core, generator)
    job = manuscript_job(15_000)
    job.payload["sourceKind"] = source_kind
    job.payload["sourceText"] = "固定素材"

    await handler(job)

    prompt = "\n".join(message.content for message in generator.requests[0].messages)
    assert required_text in prompt


@pytest.mark.asyncio
async def test_full_check_returns_report_without_document_candidate() -> None:
    core = Core()
    generator = Generator(["高潮选择缺少铺垫"])
    handler = ShortMediumWritingJobHandler(core, generator)
    base_content = "正文基础版本"
    job = manuscript_job(15_000).model_copy(
        update={
            "payload": {
                "workflow": "short_medium",
                "operation": "full_check",
                "documentType": "manuscript",
                "chapterId": "chapter-1",
                "baseVersionId": "manuscript-version-1",
                "baseContent": base_content,
                "baseContentHash": hashlib.sha256(
                    base_content.encode("utf-8")
                ).hexdigest(),
            }
        }
    )

    await handler(job)

    assert core.completions[0][2] == {
        "resultType": "short_medium_check",
        "operation": "full_check",
        "documentType": "manuscript",
        "baseVersionId": "manuscript-version-1",
        "report": {"text": "高潮选择缺少铺垫"},
    }


@pytest.mark.asyncio
async def test_15001_chars_uses_serial_segments_and_only_intermediate_checkpoints() -> None:
    core = Core()
    generator = Generator(["甲" * 3_000, "乙" * 3_000])
    handler = ShortMediumWritingJobHandler(core, generator)

    await handler(manuscript_job(15_001))

    assert len(generator.requests) == 2
    assert len(core.completions) == 1
    assert core.completions[0][2]["content"] == "甲" * 3_000 + "乙" * 3_000
    assert [item[2]["completedSegmentCount"] for item in core.checkpoints] == [1, 2]
    assert core.checkpoints[0][2]["phase"] == "generating"
    assert core.checkpoints[1][2]["phase"] == "completed"
    first_context = json.loads(generator.requests[0].messages[1].content)
    second_context = json.loads(generator.requests[1].messages[1].content)
    assert "第 1/2 个连续单元" in first_context["operationBrief"]
    assert first_context["completedContent"] == ""
    assert "第 2/2 个连续单元" in second_context["operationBrief"]
    assert second_context["completedContent"] == "甲" * 3_000


@pytest.mark.asyncio
async def test_completed_checkpoint_replays_callback_without_model_call(
    tmp_path: Path,
) -> None:
    result = {
        "resultType": "short_medium_document",
        "operation": "generate_manuscript",
        "documentType": "manuscript",
        "content": "甲" * 6_000,
        "sourceOutlineVersionId": "outline-version-1",
    }
    core = Core(
        {
            "workflow": "short_medium",
            "callbackJobId": "job-short-1",
            "phase": "completed",
            "eventSequence": 7,
            "result": result,
            "segmentCount": 1,
            "segments": [{"index": 0, "content": "甲" * 6_000}],
        }
    )
    generator = Generator([])
    workflow_log = HumanWorkflowLog(tmp_path)
    handler = ShortMediumWritingJobHandler(
        core,
        generator,
        workflow_log=workflow_log,
    )

    await handler(manuscript_job(15_000))

    assert generator.requests == []
    assert core.completions == [("job-short-1", 8, result)]
    assert workflow_log.list_runs("user-1")[0].status == "完成"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "segments",
    [
        [{"index": 1, "content": "后段"}],
        [{"index": 0, "content": "首段"}, {"index": 0, "content": "重复"}],
        [{"index": 0, "content": "首段"}, {"index": 2, "content": "缺段"}],
    ],
)
async def test_corrupt_segment_checkpoint_fails_without_model_run(
    segments: list[dict[str, object]],
) -> None:
    core = Core(
        {
            "workflow": "short_medium",
            "callbackJobId": "job-short-1",
            "phase": "generating",
            "eventSequence": 3,
            "segmentCount": 3,
            "segments": segments,
        }
    )
    generator = Generator([])
    handler = ShortMediumWritingJobHandler(core, generator)

    with pytest.raises(NonRetryableJobError):
        await handler(manuscript_job(45_000))

    assert generator.requests == []
    assert core.failures[0][0] == "job-short-1"


@pytest.mark.asyncio
@pytest.mark.parametrize("finish_reason", ["length", "content_filter"])
async def test_incomplete_model_finish_reason_fails(
    finish_reason: str,
) -> None:
    core = Core()
    generator = Generator(["半截正文"], finish_reason=finish_reason)
    handler = ShortMediumWritingJobHandler(core, generator)

    with pytest.raises(NonRetryableJobError):
        await handler(manuscript_job(15_000))

    assert core.completions == []
    assert core.failures[0][2] in {
        "MODEL_OUTPUT_TRUNCATED",
        "MODEL_OUTPUT_FILTERED",
    }
    assert core.events[0][1] == 1
    assert core.failures[0][1] == 2


@pytest.mark.asyncio
async def test_model_generator_uses_configured_output_limit() -> None:
    class Runtime:
        def __init__(self) -> None:
            self.request: ModelTurnRequest | None = None
            self.lane: ModelLane | None = None

        async def run_turn(
            self,
            request: ModelTurnRequest,
            *,
            context: object,
            lane: ModelLane,
        ) -> ModelTurnResult:
            del context
            self.request = request
            self.lane = lane
            return ModelTurnResult(
                content="结果",
                toolCalls=[],
                finishReason="stop",
                usage=ModelUsage(promptTokens=1, completionTokens=1, totalTokens=2),
            )

    runtime = Runtime()
    generator = ModelShortMediumGenerator(runtime, max_output_tokens=12_345)  # type: ignore[arg-type]

    await generator.generate(
        RunResource(
            userId="user-1",
            novelId="novel-1",
            taskId="task-1",
            runId="run-1",
            jobId="job-1",
        ),
        ModelTurnRequest(
            messages=[ModelMessage(role="user", content="请求")],
            tools=[],
            maxOutputTokens=384_000,
            policy=LEGACY_PROVIDER_DEFAULT,
        ),
    )

    assert runtime.request is not None
    assert runtime.request.maxOutputTokens == 12_345
    assert runtime.lane == "creative"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "expected_policy"),
    [
        ("generate_outline", CREATIVE_HIGH),
        ("generate_manuscript", CREATIVE_HIGH),
        ("replace_selection", CREATIVE_HIGH),
        ("full_check", REPORT_NO_THINKING),
    ],
)
async def test_short_medium_handler_passes_operation_policy_to_real_generator(
    operation: str,
    expected_policy: ModelExecutionPolicy,
) -> None:
    class Runtime:
        def __init__(self) -> None:
            self.requests: list[ModelTurnRequest] = []
            self.lanes: list[ModelLane] = []

        async def run_turn(
            self,
            request: ModelTurnRequest,
            *,
            context: object,
            lane: ModelLane,
        ) -> ModelTurnResult:
            del context
            self.requests.append(request)
            self.lanes.append(lane)
            content = "甲" * 6_000 if operation == "generate_manuscript" else "结果"
            return ModelTurnResult(
                content=content,
                toolCalls=[],
                finishReason="stop",
                usage=ModelUsage(promptTokens=1, completionTokens=1, totalTokens=2),
            )

    base_content = "基础正文"
    selected_text = "选区"
    job = manuscript_job(15_000)
    payload: dict[str, Any] = {
        "workflow": "short_medium",
        "operation": operation,
        "documentType": "outline" if operation == "replace_selection" else "manuscript",
    }
    if operation == "generate_outline":
        payload.update(
            {
                "documentType": "outline",
                "targetTotalWordCount": 15_000,
                "sourceKind": "idea",
                "sourceText": "一段灵感",
            }
        )
    elif operation == "generate_manuscript":
        payload.update(job.payload)
    elif operation == "replace_selection":
        payload.update(
            {
                "baseVersionId": "outline-version-1",
                "baseContentHash": hashlib.sha256(base_content.encode()).hexdigest(),
                "selectionStart": 0,
                "selectionEnd": len(selected_text),
                "selectedText": selected_text,
                "selectedTextHash": hashlib.sha256(selected_text.encode()).hexdigest(),
                "contextBefore": "",
                "contextAfter": "",
                "userInstruction": "替换选区",
            }
        )
    else:
        payload.update(
            {
                "chapterId": "chapter-1",
                "baseVersionId": "manuscript-version-1",
                "baseContent": base_content,
                "baseContentHash": hashlib.sha256(base_content.encode()).hexdigest(),
            }
        )
    job = job.model_copy(update={"payload": payload})
    runtime = Runtime()
    handler = ShortMediumWritingJobHandler(
        Core(),
        ModelShortMediumGenerator(runtime, max_output_tokens=12_345),  # type: ignore[arg-type]
    )

    await handler(job)

    assert len(runtime.requests) == 1
    assert runtime.lanes == ["creative"]
    actual_policy = runtime.requests[0].policy
    assert actual_policy.policyId == expected_policy.policyId
    assert actual_policy.thinkingMode == expected_policy.thinkingMode
    assert actual_policy.reasoningEffort == expected_policy.reasoningEffort
