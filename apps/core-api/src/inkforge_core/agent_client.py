from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Protocol, cast
from urllib.parse import urlencode

import httpx
from inkforge_contracts.jobs import (
    AgentJobAccepted,
    AgentJobCancelRequest,
    AgentJobRequest,
    AgentJobStatus,
)
from inkforge_contracts.jwt_claims import ServiceScope
from inkforge_contracts.video_render import (
    SeedanceRenderQueryRequest,
    SeedanceRenderQueryResponse,
    SeedanceRenderSubmitRequest,
    SeedanceRenderSubmitResponse,
)
from inkforge_service_auth import ServiceTokenSigner, canonical_json_body
from pydantic import JsonValue

from .errors import ApiError
from .references.job_identity import build_rag_job_identity
from .writing.commands import WritingCommandRecord
from .writing.idempotency import parse_command_envelope
from .writing.job_identity import build_writing_job_id
from .writing.records import TaskRecord

_SEEDANCE_GATEWAY_TIMEOUT = httpx.Timeout(40, connect=2)


class AgentJobClient(Protocol):
    async def submit(self, request: AgentJobRequest) -> AgentJobAccepted: ...

    async def cancel(self, job_id: str, request: AgentJobCancelRequest) -> None: ...


class SeedanceSubmissionUnknownError(RuntimeError):
    """创建请求可能已经到达供应商，调用方不得自动重提。"""


class SeedanceGatewayRejectedError(RuntimeError):
    def __init__(self, *, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class SeedanceGatewayQueryError(RuntimeError):
    """短查询失败，可由耐久任务稍后再次查询同一 providerTaskId。"""


class AgentClient:
    def __init__(self, http: httpx.AsyncClient, signer: ServiceTokenSigner) -> None:
        self._http = http
        self._signer = signer

    async def submit(self, request: AgentJobRequest) -> AgentJobAccepted:
        path = "/internal/v1/runs"
        body = canonical_json_body(request.model_dump(mode="json"))
        signed = self._signer.sign_request(
            body=body,
            http_method="POST",
            http_path=path,
            query_string=b"",
            idempotency_key=request.jobId,
            scope=(ServiceScope.AGENT_RUN,),
            task_id=request.taskId,
            run_id=request.runId,
            novel_id=request.novelId,
        )
        try:
            response = await self._http.post(
                path,
                content=body,
                headers={**signed.headers, "Content-Type": "application/json"},
            )
            response.raise_for_status()
            return AgentJobAccepted.model_validate(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            raise ApiError(
                status_code=503,
                code="AGENT_RUN_SUBMIT_FAILED",
                message="智能体运行提交失败",
            ) from exc

    async def cancel(self, job_id: str, request: AgentJobCancelRequest) -> None:
        path = f"/internal/v1/runs/{job_id}"
        body = canonical_json_body(request.model_dump(mode="json"))
        signed = self._signer.sign_request(
            body=body,
            http_method="DELETE",
            http_path=path,
            query_string=b"",
            idempotency_key=job_id,
            scope=(ServiceScope.AGENT_CANCEL,),
            task_id=request.taskId,
            run_id=request.runId,
            novel_id=request.novelId,
        )
        try:
            response = await self._http.request(
                "DELETE",
                path,
                content=body,
                headers={**signed.headers, "Content-Type": "application/json"},
            )
            if response.status_code != 204:
                response.raise_for_status()
                raise ValueError("智能体取消接口未返回 204")
        except (httpx.HTTPError, ValueError) as exc:
            raise ApiError(
                status_code=503,
                code="AGENT_RUN_CANCEL_FAILED",
                message="智能体运行取消投递失败",
            ) from exc

    async def get_workflow_runs(
        self,
        user_id: str,
        run_id: str | None = None,
    ) -> dict[str, object]:
        path = "/internal/v1/debug/workflow-runs"
        if run_id is not None:
            path += f"/{run_id}"
        query = urlencode({"userId": user_id}).encode()
        idempotency_key = "debug-" + hashlib.sha256(
            f"{user_id}:{run_id or 'list'}".encode()
        ).hexdigest()[:32]
        signed = self._signer.sign_request(
            body=b"",
            http_method="GET",
            http_path=path,
            query_string=query,
            idempotency_key=idempotency_key,
            scope=(ServiceScope.AGENT_DEBUG_READ,),
            task_id="debug",
            run_id="debug",
            novel_id="debug",
        )
        try:
            response = await self._http.get(
                path,
                params={"userId": user_id},
                headers=signed.headers,
            )
            response.raise_for_status()
            value = response.json()
            if not isinstance(value, dict):
                raise ValueError("智能体调试接口返回值不是对象")
            return cast(dict[str, object], value)
        except (httpx.HTTPError, ValueError) as exc:
            raise ApiError(
                status_code=503,
                code="AGENT_DEBUG_READ_FAILED",
                message="读取智能体工作流日志失败",
            ) from exc

    async def submit_seedance_render(
        self,
        request: SeedanceRenderSubmitRequest,
    ) -> SeedanceRenderSubmitResponse:
        """执行一次不可自动重放的 Seedance 创建短调用。"""

        path = "/internal/v1/video/seedance/tasks"
        body = canonical_json_body(request.model_dump(mode="json"))
        signed = self._signer.sign_request(
            body=body,
            http_method="POST",
            http_path=path,
            query_string=b"",
            idempotency_key=f"render-submit-{request.taskId}",
            scope=(ServiceScope.VIDEO_RENDER,),
            task_id=request.taskId,
            run_id=request.taskId,
            novel_id=request.novelId,
        )
        try:
            response = await self._http.post(
                path,
                content=body,
                headers={**signed.headers, "Content-Type": "application/json"},
                timeout=_SEEDANCE_GATEWAY_TIMEOUT,
            )
        except httpx.HTTPError as exc:
            # 创建请求可能已经被供应商接收，网络错误时禁止 Core 自动重提。
            raise SeedanceSubmissionUnknownError() from exc
        if response.status_code >= 500:
            # Agent 可能已把创建请求送达供应商，只是在回传前失败；此时不能判定为
            # 明确拒绝，否则用户重试可能造成供应商重复计费。
            raise SeedanceSubmissionUnknownError()
        if response.status_code >= 400:
            raise SeedanceGatewayRejectedError(
                status_code=response.status_code,
                detail=_internal_error_detail(response),
            )
        try:
            return SeedanceRenderSubmitResponse.model_validate(response.json())
        except ValueError as exc:
            raise SeedanceSubmissionUnknownError() from exc

    async def query_seedance_render(
        self,
        request: SeedanceRenderQueryRequest,
    ) -> SeedanceRenderQueryResponse:
        path = (
            f"/internal/v1/video/seedance/tasks/{request.providerTaskId}/query"
        )
        body = canonical_json_body(request.model_dump(mode="json"))
        signed = self._signer.sign_request(
            body=body,
            http_method="POST",
            http_path=path,
            query_string=b"",
            idempotency_key=f"render-query-{request.taskId}-{request.pollCount}",
            scope=(ServiceScope.VIDEO_RENDER,),
            task_id=request.taskId,
            run_id=request.taskId,
            novel_id=request.novelId,
        )
        try:
            response = await self._http.post(
                path,
                content=body,
                headers={**signed.headers, "Content-Type": "application/json"},
                timeout=_SEEDANCE_GATEWAY_TIMEOUT,
            )
            response.raise_for_status()
            return SeedanceRenderQueryResponse.model_validate(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            raise SeedanceGatewayQueryError() from exc


class WritingTaskAgentSubmitter:
    def __init__(self, client: AgentJobClient) -> None:
        self._client = client

    async def submit(
        self,
        task: TaskRecord,
        *,
        resume: bool,
        resume_input: dict[str, object] | None = None,
    ) -> AgentJobStatus:
        return await self._submit(
            task,
            resume=resume,
            force=False,
            resume_input=resume_input,
        )

    async def reconcile(self, task: TaskRecord) -> AgentJobStatus:
        return await self._submit(
            task,
            resume=task.graph_state_json is not None,
            force=True,
            resume_input=None,
        )

    async def submit_command(self, command: WritingCommandRecord) -> AgentJobStatus:
        payload = command_job_payload(command.payload)
        accepted = await self._client.submit(
            AgentJobRequest(
                protocolVersion="1.0",
                jobId=command.id,
                kind="writing",
                runId=command.task.id,
                taskId=command.task.id,
                novelId=command.task.novel_id,
                userId=command.task.user_id,
                priority=10,
                payload=payload,
                force=payload.get("force") is True,
            )
        )
        return accepted.status

    async def cancel_command(self, command: WritingCommandRecord) -> None:
        if command.kind != "cancel":
            raise ValueError("只有取消命令可以调用取消投递")
        payload = command_job_payload(command.payload)
        cancelled_job_id = payload.get("cancelledJobId")
        if not isinstance(cancelled_job_id, str):
            raise ValueError("取消命令缺少被取消的 job 标识")
        await self._client.cancel(
            cancelled_job_id,
            AgentJobCancelRequest(
                protocolVersion="1.0",
                runId=command.task.id,
                taskId=command.task.id,
                novelId=command.task.novel_id,
            ),
        )

    async def _submit(
        self,
        task: TaskRecord,
        *,
        resume: bool,
        force: bool,
        resume_input: dict[str, object] | None,
    ) -> AgentJobStatus:
        accepted = await self._client.submit(
            AgentJobRequest(
                protocolVersion="1.0",
                jobId=build_writing_job_id(
                    task.id,
                    resume=resume,
                    graph_state_json=task.graph_state_json,
                ),
                kind="writing",
                runId=task.id,
                taskId=task.id,
                novelId=task.novel_id,
                userId=task.user_id,
                priority=10,
                payload={
                    "resume": resume,
                    "chapterId": task.chapter_id,
                    "writingSessionId": task.writing_session_id,
                    "resumeInput": cast(JsonValue, resume_input),
                },
                force=force,
            )
        )
        return accepted.status


class QualityAgentSubmitter:
    def __init__(self, client: AgentJobClient) -> None:
        self._client = client

    async def submit(
        self,
        *,
        run_id: str,
        user_id: str,
        check_id: str,
        novel_id: str,
        chapter_id: str,
        source_task_id: str | None,
        message: str | None,
    ) -> AgentJobStatus:
        billing_task_id = source_task_id or run_id
        accepted = await self._client.submit(
            AgentJobRequest(
                protocolVersion="1.0",
                jobId=f"quality-{run_id}",
                kind="quality",
                runId=run_id,
                taskId=billing_task_id,
                novelId=novel_id,
                userId=user_id,
                priority=5,
                payload={
                    "checkId": check_id,
                    "chapterId": chapter_id,
                    "sourceTaskId": source_task_id,
                    "message": message,
                },
            )
        )
        return accepted.status


class PortraitAgentSubmitter:
    def __init__(self, client: AgentJobClient) -> None:
        self._client = client

    async def submit(
        self,
        *,
        user_id: str,
        style_id: str,
        task_id: str,
        run_id: str,
        section: str | None,
    ) -> AgentJobStatus:
        accepted = await self._client.submit(
            AgentJobRequest(
                protocolVersion="1.0",
                jobId=f"portrait-{task_id}",
                kind="portrait",
                runId=run_id,
                taskId=task_id,
                novelId=f"style:{style_id}",
                userId=user_id,
                priority=20,
                payload={"styleId": style_id, "section": section},
            )
        )
        return accepted.status


class RagAgentSubmitter:
    def __init__(self, client: AgentJobClient) -> None:
        self._client = client

    async def submit(
        self,
        user_id: str,
        novel_id: str,
        reference_id: str,
        content_hash: str,
        generation: datetime,
    ) -> AgentJobStatus:
        identity = build_rag_job_identity(reference_id, content_hash, generation)
        accepted = await self._client.submit(
            AgentJobRequest(
                protocolVersion="1.0",
                jobId=identity.run_id,
                kind="rag",
                runId=identity.run_id,
                taskId=identity.task_id,
                novelId=novel_id,
                userId=user_id,
                priority=30,
                payload={
                    "referenceId": reference_id,
                    "contentHash": content_hash,
                },
            )
        )
        return accepted.status

def command_job_payload(payload: dict[str, object]) -> dict[str, JsonValue]:
    if "_inkforgeCommand" not in payload:
        return cast(dict[str, JsonValue], payload)
    parse_command_envelope(payload)
    if set(payload) != {"_inkforgeCommand", "job"}:
        raise ValueError("新写作命令 envelope 必须且只能包含 _inkforgeCommand 和 job")
    job = payload.get("job")
    if not isinstance(job, dict) or any(not isinstance(key, str) for key in job):
        raise ValueError("新写作命令 envelope 的 job 必须是 JSON 对象")
    return cast(dict[str, JsonValue], job)


class VideoAgentSubmitter:
    """把数据库中的视频规划任务投递到共享 Agent 队列。"""

    def __init__(self, client: AgentJobClient) -> None:
        self._client = client

    async def submit(
        self,
        *,
        user_id: str,
        novel_id: str,
        task_id: str,
        job_id: str,
        payload: dict[str, JsonValue],
    ) -> AgentJobStatus:
        """使用任务 ID 作为运行 ID，保证计费、回调和重试资源一致。"""

        accepted = await self._client.submit(
            AgentJobRequest(
                protocolVersion="1.0",
                jobId=job_id,
                kind="video",
                runId=task_id,
                taskId=task_id,
                novelId=novel_id,
                userId=user_id,
                priority=15,
                payload=payload,
            )
        )
        return accepted.status


def _internal_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return "Seedance 内部网关拒绝请求"
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str) and detail:
            return detail[:2_000]
    return "Seedance 内部网关拒绝请求"
