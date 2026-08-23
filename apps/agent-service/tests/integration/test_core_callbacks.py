from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from inkforge_agents.clients.core import CoreServiceClient, CoreServiceError, RunResource
from inkforge_contracts.jwt_claims import ServiceScope
from inkforge_contracts.video import (
    StoryPlanStageArguments,
    VideoPlanAttemptState,
    VideoPlanCallReservationRequest,
    VideoPlanProgressQuery,
    VideoStoryPlanCheckpointCallback,
)
from inkforge_service_auth import SignedServiceRequest


class Signer:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def sign_request(self, **kwargs: object) -> SignedServiceRequest:
        self.calls.append(dict(kwargs))
        return SignedServiceRequest(
            token="signed",  # noqa: S106
            headers={
                "Authorization": "Bearer signed",
                "Idempotency-Key": str(kwargs["idempotency_key"]),
                "X-InkForge-Timestamp": "1",
                "X-InkForge-Body-SHA256": "0" * 64,
            },
        )


def _story_checkpoint() -> StoryPlanStageArguments:
    """构造 CoreClient 传输测试使用的最小规范故事。"""

    return StoryPlanStageArguments.model_validate(
        {
            "schemaVersion": "1.0",
            "title": "门前停步",
            "summary": "少女在门前停步。",
            "dramaticArc": "接近门口，在犹豫后停住。",
            "visualStyle": "写实冷调",
            "globalDirection": "保持动作克制",
            "assets": [
                {
                    "assetId": "asset01",
                    "modality": "image",
                    "duty": "scene",
                    "bindingScope": "scene_direct",
                    "settingReference": None,
                    "featureDomain": "location",
                    "keyframeRole": None,
                    "targetEntity": "雨夜木门",
                    "includeFeatures": ["湿木纹"],
                    "excludeFeatures": [],
                }
            ],
            "beats": [
                {
                    "beatId": "beat-01",
                    "startSecond": 0,
                    "endSecond": 4,
                    "dramaticPurpose": "建立犹豫",
                    "performanceDirection": "少女抬手后停顿半拍",
                    "blocking": "少女从画面左侧走到中央门前",
                    "actionUnits": [
                        {
                            "subject": "少女",
                            "action": "抬手",
                            "visibleResult": "手停在门前",
                        }
                    ],
                    "actionComplexity": "simple",
                    "sound": "雨声与衣料摩擦声",
                    "referencedAssetIds": ["asset01"],
                }
            ],
            "negativeConstraints": ["人物身份漂移"],
        }
    )


def _callback_receipt(
    *,
    disposition: str = "applied",
    reason_code: str = "CALLBACK_APPLIED",
    recoverable: bool = False,
) -> dict[str, object]:
    return {
        "protocolVersion": "1.0",
        "disposition": disposition,
        "reasonCode": reason_code,
        "recoverable": recoverable,
        "taskPhase": "active",
        "commandStatus": "processing",
        "outboxEventId": "outbox-event-1",
    }


async def _invoke_writing_boundary(
    client: CoreServiceClient,
    resource: RunResource,
    callback_name: str,
) -> None:
    if callback_name == "event":
        await client.send_event(resource, sequence=1, event="agent_start", data={})
        return
    if callback_name == "checkpoint":
        await client.save_checkpoint(
            resource,
            sequence=2,
            checkpoint={"taskId": "task-1"},
        )
        return
    if callback_name == "complete":
        await client.complete(
            resource,
            sequence=3,
            result={"finalContent": "完成"},
        )
        return
    if callback_name == "fail":
        await client.fail(
            resource,
            sequence=4,
            code="MODEL_ERROR",
            message="失败",
        )
        return
    raise AssertionError(f"未知回调类型：{callback_name}")


@pytest.mark.asyncio
async def test_core_client_signs_tools_events_checkpoint_and_completion() -> None:
    requests: list[tuple[str, str, dict[str, object]]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["content-type"] == "application/json"
        payload = json.loads(request.content) if request.content else {}
        requests.append((request.method, request.url.path, payload))
        if "/tools/" in request.url.path:
            return httpx.Response(200, json={"result": {"planning": {"taskId": "task-1"}}})
        if request.url.path.endswith("/index-context"):
            return httpx.Response(200, json={"contentHash": "a" * 64, "chunks": ["正文"]})
        if request.url.path.endswith("/portrait-context"):
            return httpx.Response(
                200,
                json={"sourceText": "完整参考正文", "originalCharCount": 6},
            )
        if request.url.path.endswith("/quality-checks/check-1/context"):
            return httpx.Response(
                200,
                json={
                    "checkId": "check-1",
                    "novelId": "novel-1",
                    "chapterId": "chapter-1",
                    "chapterContent": "完整章节",
                    "message": "检查一致性",
                },
            )
        if request.url.path.endswith(("/events", "/checkpoint", "/complete")):
            return httpx.Response(200, json=_callback_receipt())
        return httpx.Response(204)

    signer = Signer()
    http = httpx.AsyncClient(
        base_url="https://core.example",
        transport=httpx.MockTransport(handler),
    )
    client = CoreServiceClient(http, signer)  # type: ignore[arg-type]
    resource = RunResource(
        userId="user-1",
        novelId="novel-1",
        taskId="task-1",
        runId="run-1",
        jobId="job-1",
    )

    result = await client.call_tool(resource, "编辑", "get_writing_context", {})
    await client.send_event(resource, sequence=1, event="start", data={})
    await client.save_checkpoint(resource, sequence=2, checkpoint={"taskId": "task-1"})
    await client.complete(resource, sequence=3, result={"finalContent": "完成"})
    rag_context = await client.get_rag_context(resource, "reference-1", "a" * 64)
    await client.complete_rag(resource, "reference-1", "a" * 64, [[1.0]])
    portrait = await client.get_portrait_context(resource, "style-1")
    await client.mark_portrait_processing(resource, "style-1")
    await client.complete_portrait(
        resource,
        "style-1",
        {
            "creativeMethodology": "方法",
            "uniqueMarkers": "标记",
            "generationStyle": "风格",
            "expressionFeatures": "表达",
            "styleTraits": "特质",
            "originalCharCount": 6,
            "usedCharCount": 6,
            "truncated": False,
        },
    )
    quality = await client.get_quality_context(resource, "check-1", None, "检查一致性")
    await client.complete_quality(
        resource,
        "check-1",
        {
            "scores": {
                "characterConsistency": 81.0,
                "worldRuleConsistency": 82.0,
                "timelineConsistency": 83.0,
                "causalityConsistency": 84.0,
                "foreshadowingConsistency": 88.0,
            },
            "qualityGate": "pass",
            "issues": [],
            "report": "完整一致性报告",
            "rewriteBrief": None,
        },
    )

    assert result["planning"]["taskId"] == "task-1"
    assert rag_context["chunks"] == ["正文"]
    assert portrait["sourceText"] == "完整参考正文"
    assert quality["chapterContent"] == "完整章节"
    assert [call["scope"] for call in signer.calls] == [
        (ServiceScope.TOOL_READ,),
        (ServiceScope.CALLBACK_EVENT,),
        (ServiceScope.CALLBACK_CHECKPOINT,),
        (ServiceScope.CALLBACK_COMPLETE,),
        (ServiceScope.RAG_INDEX_WRITE,),
        (ServiceScope.RAG_INDEX_WRITE,),
        (ServiceScope.PORTRAIT_WRITE,),
        (ServiceScope.PORTRAIT_WRITE,),
        (ServiceScope.PORTRAIT_WRITE,),
        (ServiceScope.QUALITY_WRITE,),
        (ServiceScope.QUALITY_WRITE,),
    ]
    assert [path for _, path, _ in requests] == [
        "/internal/v1/tools/get_writing_context",
        "/internal/v1/writing/runs/run-1/events",
        "/internal/v1/writing/runs/run-1/checkpoint",
        "/internal/v1/writing/runs/run-1/complete",
        "/internal/v1/novels/novel-1/references/reference-1/index-context",
        "/internal/v1/novels/novel-1/references/reference-1/index-success",
        "/internal/v1/styles/style-1/portrait-tasks/task-1/portrait-context",
        "/internal/v1/styles/style-1/portrait-tasks/task-1/processing",
        "/internal/v1/styles/style-1/portrait-tasks/task-1/success",
        "/internal/v1/quality-checks/check-1/context",
        "/internal/v1/quality-checks/check-1/success",
    ]
    writing_callbacks = [
        payload
        for _, path, payload in requests
        if path.startswith("/internal/v1/writing/runs/")
    ]
    assert writing_callbacks == [
        {
            "protocolVersion": "1.1",
            "eventId": writing_callbacks[0]["eventId"],
            "jobId": "job-1",
            "runId": "run-1",
            "taskId": "task-1",
            "sequence": 1,
            "event": "start",
            "data": {},
            "occurredAt": writing_callbacks[0]["occurredAt"],
        },
        {
            "protocolVersion": "1.1",
            "eventId": writing_callbacks[1]["eventId"],
            "jobId": "job-1",
            "runId": "run-1",
            "taskId": "task-1",
            "sequence": 2,
            "checkpoint": {"taskId": "task-1"},
            "occurredAt": writing_callbacks[1]["occurredAt"],
        },
        {
            "protocolVersion": "1.1",
            "eventId": writing_callbacks[2]["eventId"],
            "jobId": "job-1",
            "runId": "run-1",
            "taskId": "task-1",
            "sequence": 3,
            "result": {"finalContent": "完成"},
            "occurredAt": writing_callbacks[2]["occurredAt"],
        },
    ]
    await http.aclose()


@pytest.mark.asyncio
async def test_core_client_uses_stable_idempotency_keys_for_retries() -> None:
    signer = Signer()
    http = httpx.AsyncClient(
        base_url="https://core.example",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=_callback_receipt())
        ),
    )
    client = CoreServiceClient(http, signer)  # type: ignore[arg-type]
    resource = RunResource(
        userId="user-1",
        novelId="novel-1",
        taskId="task-1",
        runId="run-1",
        jobId="job-1",
    )

    await client.fail(resource, sequence=4, code="MODEL_ERROR", message="失败")
    await client.fail(resource, sequence=4, code="MODEL_ERROR", message="失败")
    await client.fail(
        resource.model_copy(update={"jobId": "job-2"}),
        sequence=4,
        code="MODEL_ERROR",
        message="失败",
    )

    assert signer.calls[0]["idempotency_key"] == signer.calls[1]["idempotency_key"]
    assert signer.calls[0]["idempotency_key"] != signer.calls[2]["idempotency_key"]
    assert signer.calls[0]["body"] == signer.calls[1]["body"]
    failure_payload = json.loads(signer.calls[0]["body"])
    assert failure_payload["protocolVersion"] == "1.1"
    assert failure_payload["jobId"] == "job-1"
    await http.aclose()


@pytest.mark.asyncio
async def test_artifact_writes_bind_job_to_signed_body_and_idempotency_key() -> None:
    signer = Signer()
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": "artifact-1", "revision": 1})

    http = httpx.AsyncClient(
        base_url="https://core.example",
        transport=httpx.MockTransport(handler),
    )
    client = CoreServiceClient(http, signer)  # type: ignore[arg-type]
    resource = RunResource(
        userId="user-1",
        novelId="novel-1",
        taskId="task-1",
        runId="run-1",
        jobId="job-1",
    )
    payload = {
        "runId": "run-1",
        "taskId": "task-1",
        "novelId": "novel-1",
        "jobId": "untrusted-job",
        "kind": "chapter_draft",
    }

    await client.create_artifact(resource, payload, idempotency_key="artifact-job-1")
    await client.create_artifact(
        resource.model_copy(update={"jobId": "job-2"}),
        payload,
        idempotency_key="artifact-job-2",
    )

    first_body = json.loads(requests[0].content)
    assert first_body["jobId"] == "job-1"
    assert signer.calls[0]["body"] == requests[0].content
    assert signer.calls[0]["idempotency_key"] != signer.calls[1]["idempotency_key"]
    await http.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("callback_name", ["event", "checkpoint", "complete", "fail"])
async def test_writing_boundary_rejects_missing_callback_receipt(
    callback_name: str,
) -> None:
    http = httpx.AsyncClient(
        base_url="https://core.example",
        transport=httpx.MockTransport(lambda request: httpx.Response(204)),
    )
    client = CoreServiceClient(http, Signer())  # type: ignore[arg-type]
    resource = RunResource(
        userId="user-1",
        novelId="novel-1",
        taskId="task-1",
        runId="run-1",
        jobId="job-1",
    )

    with pytest.raises(CoreServiceError) as caught:
        await _invoke_writing_boundary(client, resource, callback_name)

    assert caught.value.code == "CALLBACK_RECEIPT_MISSING"
    assert caught.value.recoverable is True
    await http.aclose()


@pytest.mark.asyncio
async def test_core_http_error_keeps_safe_code_without_echoing_details() -> None:
    """跨服务失败要可定位，但不能把校验细节中的请求内容写入任务错误。"""

    http = httpx.AsyncClient(
        base_url="https://core.example",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                422,
                json={
                    "code": "VALIDATION_ERROR",
                    "message": "请求参数校验失败",
                    "details": [{"input": "不得回显的完整回调载荷"}],
                    "requestId": "request-1",
                },
            )
        ),
    )
    client = CoreServiceClient(http, Signer())  # type: ignore[arg-type]
    resource = RunResource(
        userId="user-1",
        novelId="novel-1",
        taskId="task-1",
        runId="run-1",
        jobId="job-1",
    )

    with pytest.raises(CoreServiceError) as caught:
        await client.complete(resource, sequence=3, result={"finalContent": "完整结果"})

    assert caught.value.code == "VALIDATION_ERROR"
    assert "HTTP 422" in str(caught.value)
    assert "请求参数校验失败" in str(caught.value)
    assert "不得回显" not in str(caught.value)
    assert caught.value.recoverable is False
    await http.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"{"),
        httpx.Response(200, json={"disposition": "applied"}),
    ],
)
async def test_writing_boundary_rejects_invalid_callback_receipt(
    response: httpx.Response,
) -> None:
    http = httpx.AsyncClient(
        base_url="https://core.example",
        transport=httpx.MockTransport(lambda request: response),
    )
    client = CoreServiceClient(http, Signer())  # type: ignore[arg-type]
    resource = RunResource(
        userId="user-1",
        novelId="novel-1",
        taskId="task-1",
        runId="run-1",
        jobId="job-1",
    )

    with pytest.raises(CoreServiceError) as caught:
        await client.save_checkpoint(
            resource,
            sequence=2,
            checkpoint={"taskId": "task-1"},
        )

    assert caught.value.code == "CALLBACK_RECEIPT_INVALID"
    assert caught.value.recoverable is True
    await http.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("recoverable", [True, False])
async def test_writing_boundary_maps_rejected_receipt_recoverability(
    recoverable: bool,
) -> None:
    http = httpx.AsyncClient(
        base_url="https://core.example",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json=_callback_receipt(
                    disposition="rejected",
                    reason_code="CALLBACK_IDENTITY_REJECTED",
                    recoverable=recoverable,
                ),
            )
        ),
    )
    client = CoreServiceClient(http, Signer())  # type: ignore[arg-type]
    resource = RunResource(
        userId="user-1",
        novelId="novel-1",
        taskId="task-1",
        runId="run-1",
        jobId="job-1",
    )

    with pytest.raises(CoreServiceError) as caught:
        await client.complete(
            resource,
            sequence=3,
            result={"finalContent": "完成"},
        )

    assert caught.value.code == "CALLBACK_IDENTITY_REJECTED"
    assert caught.value.recoverable is recoverable
    await http.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("callback_name", ["event", "checkpoint", "complete", "fail"])
@pytest.mark.parametrize("disposition", ["applied", "already_applied"])
async def test_writing_boundary_accepts_applied_receipts(
    callback_name: str,
    disposition: str,
) -> None:
    http = httpx.AsyncClient(
        base_url="https://core.example",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json=_callback_receipt(disposition=disposition),
            )
        ),
    )
    client = CoreServiceClient(http, Signer())  # type: ignore[arg-type]
    resource = RunResource(
        userId="user-1",
        novelId="novel-1",
        taskId="task-1",
        runId="run-1",
        jobId="job-1",
    )

    await _invoke_writing_boundary(client, resource, callback_name)

    await http.aclose()


@pytest.mark.asyncio
async def test_core_client_reads_progress_and_saves_story_checkpoint() -> None:
    """视频进度与故事检查点必须使用固定 POST 端点、六重身份和 VIDEO_WRITE。"""

    captured: list[tuple[str, str, dict[str, object]]] = []
    story = _story_checkpoint()

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        captured.append((request.method, request.url.path, payload))
        if request.url.path.endswith("/progress"):
            return httpx.Response(
                200,
                json={
                    **payload,
                    "inputFingerprint": "a" * 64,
                    "status": "active",
                    "checkpointStage": "story",
                    "sceneAssetsPlan": None,
                    "storyPlan": story.model_dump(mode="json"),
                    "attemptState": {"reservedCalls": 2, "pendingStage": None},
                },
            )
        return httpx.Response(204)

    signer = Signer()
    http = httpx.AsyncClient(
        base_url="https://core.example",
        transport=httpx.MockTransport(handler),
    )
    client = CoreServiceClient(http, signer)  # type: ignore[arg-type]
    resource = RunResource(
        userId="user-1",
        novelId="novel-1",
        taskId="task-1",
        runId="run-1",
        jobId="job-1",
    )
    query = VideoPlanProgressQuery(
        protocolVersion="1.0",
        jobId="job-1",
        runId="run-1",
        taskId="task-1",
        novelId="novel-1",
        projectId="project-1",
        sceneId="scene-1",
    )

    progress = await client.get_video_plan_progress(resource, query)
    await client.save_story_plan_checkpoint(
        resource,
        VideoStoryPlanCheckpointCallback(
            protocolVersion="1.0",
            eventId="checkpoint-1",
            jobId="job-1",
            runId="run-1",
            taskId="task-1",
            novelId="novel-1",
            projectId="project-1",
            sceneId="scene-1",
            checkpointStage="story",
            sceneAssetsPlan=None,
            storyPlan=story,
            attemptState=VideoPlanAttemptState(reservedCalls=2, pendingStage=None),
        ),
    )

    assert progress.storyPlan == story
    assert progress.attemptState.reservedCalls == 2
    assert [(method, path) for method, path, _ in captured] == [
        ("POST", "/internal/v1/video/scenes/scene-1/progress"),
        ("POST", "/internal/v1/video/scenes/scene-1/story-checkpoint"),
    ]
    assert [call["scope"] for call in signer.calls] == [
        (ServiceScope.VIDEO_WRITE,),
        (ServiceScope.VIDEO_WRITE,),
    ]
    assert captured[1][2]["checkpointStage"] == "story"
    assert captured[1][2]["attemptState"] == {
        "reservedCalls": 2,
        "inheritedCalls": 0,
        "pendingStage": None,
    }
    assert captured[1][2]["storyPlan"] == story.model_dump(mode="json")
    await http.aclose()


@pytest.mark.asyncio
async def test_core_client_reserves_video_plan_call_before_provider() -> None:
    """模型调用预留必须走固定 VIDEO_WRITE 端点并核对完整回执绑定。"""

    captured: list[tuple[str, str, dict[str, object]]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        captured.append((request.method, request.url.path, payload))
        response = {
            key: value
            for key, value in payload.items()
            if key not in {"expectedReservedCalls", "inheritedCalls"}
        }
        response.update(
            {
                "reservedCallsBefore": payload["expectedReservedCalls"],
                "attemptState": {
                    "reservedCalls": payload["expectedReservedCalls"] + 1,
                    "inheritedCalls": payload["inheritedCalls"],
                    "pendingStage": payload["stage"],
                },
            }
        )
        return httpx.Response(200, json=response)

    signer = Signer()
    http = httpx.AsyncClient(
        base_url="https://core.example",
        transport=httpx.MockTransport(handler),
    )
    client = CoreServiceClient(http, signer)  # type: ignore[arg-type]
    resource = RunResource(
        userId="user-1",
        novelId="novel-1",
        taskId="task-1",
        runId="run-1",
        jobId="job-1",
    )
    request = VideoPlanCallReservationRequest(
        protocolVersion="1.0",
        eventId="reserve-story-3",
        jobId="job-1",
        runId="run-1",
        taskId="task-1",
        novelId="novel-1",
        projectId="project-1",
        sceneId="scene-1",
        checkpointStage="story",
        stage="cinematography",
        expectedReservedCalls=2,
    )

    response = await client.reserve_video_plan_call(resource, request)

    assert response.attemptState == VideoPlanAttemptState(
        reservedCalls=3,
        pendingStage="cinematography",
    )
    assert [(method, path) for method, path, _ in captured] == [
        ("POST", "/internal/v1/video/scenes/scene-1/call-reservations")
    ]
    assert signer.calls[0]["scope"] == (ServiceScope.VIDEO_WRITE,)
    assert captured[0][2]["expectedReservedCalls"] == 2
    assert captured[0][2]["inheritedCalls"] == 0
    await http.aclose()


@pytest.mark.asyncio
async def test_core_client_rejects_mismatched_video_progress_identity() -> None:
    """CoreClient 必须在契约解析后再次核对响应六重资源身份。"""

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                **payload,
                "sceneId": "scene-other",
                "inputFingerprint": "a" * 64,
                "status": "active",
                "checkpointStage": "empty",
                "sceneAssetsPlan": None,
                "storyPlan": None,
                "attemptState": {"reservedCalls": 0, "pendingStage": None},
            },
        )

    http = httpx.AsyncClient(
        base_url="https://core.example",
        transport=httpx.MockTransport(handler),
    )
    client = CoreServiceClient(http, Signer())  # type: ignore[arg-type]
    resource = RunResource(
        userId="user-1",
        novelId="novel-1",
        taskId="task-1",
        runId="run-1",
        jobId="job-1",
    )
    query = VideoPlanProgressQuery(
        protocolVersion="1.0",
        jobId="job-1",
        runId="run-1",
        taskId="task-1",
        novelId="novel-1",
        projectId="project-1",
        sceneId="scene-1",
    )

    with pytest.raises(CoreServiceError) as exc_info:
        await client.get_video_plan_progress(resource, query)

    assert exc_info.value.code == "VIDEO_PLAN_PROGRESS_RESOURCE_MISMATCH"
    assert exc_info.value.recoverable is False
    await http.aclose()
