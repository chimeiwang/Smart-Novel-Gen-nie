from __future__ import annotations

import hashlib
from typing import Protocol, cast
from urllib.parse import urlencode

import httpx
from inkforge_contracts.jobs import AgentJobAccepted, AgentJobRequest
from inkforge_contracts.jwt_claims import ServiceScope
from inkforge_service_auth import ServiceTokenSigner, canonical_json_body
from pydantic import JsonValue

from .errors import ApiError
from .writing.commands import WritingCommandRecord
from .writing.job_identity import build_writing_job_id
from .writing.records import TaskRecord


class AgentJobClient(Protocol):
    async def submit(self, request: AgentJobRequest) -> AgentJobAccepted: ...


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


class WritingTaskAgentSubmitter:
    def __init__(self, client: AgentJobClient) -> None:
        self._client = client

    async def submit(
        self,
        task: TaskRecord,
        *,
        resume: bool,
        resume_input: dict[str, object] | None = None,
    ) -> None:
        await self._submit(
            task,
            resume=resume,
            force=False,
            resume_input=resume_input,
        )

    async def reconcile(self, task: TaskRecord) -> None:
        await self._submit(
            task,
            resume=task.graph_state_json is not None,
            force=True,
            resume_input=None,
        )

    async def submit_command(self, command: WritingCommandRecord) -> None:
        await self._client.submit(
            AgentJobRequest(
                protocolVersion="1.0",
                jobId=command.id,
                kind="writing",
                runId=command.task.id,
                taskId=command.task.id,
                novelId=command.task.novel_id,
                userId=command.task.user_id,
                priority=10,
                payload=cast(dict[str, JsonValue], command.payload),
            )
        )

    async def _submit(
        self,
        task: TaskRecord,
        *,
        resume: bool,
        force: bool,
        resume_input: dict[str, object] | None,
    ) -> None:
        await self._client.submit(
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


class QualityAgentSubmitter:
    def __init__(self, client: AgentJobClient) -> None:
        self._client = client

    async def submit(
        self,
        *,
        user_id: str,
        check_id: str,
        novel_id: str,
        chapter_id: str,
        task_id: str | None,
        message: str | None,
    ) -> str:
        run_id = f"quality-{check_id}"
        billing_task_id = task_id or check_id
        await self._client.submit(
            AgentJobRequest(
                protocolVersion="1.0",
                jobId=run_id,
                kind="quality",
                runId=run_id,
                taskId=billing_task_id,
                novelId=novel_id,
                userId=user_id,
                priority=5,
                payload={
                    "checkId": check_id,
                    "chapterId": chapter_id,
                    "sourceTaskId": task_id,
                    "message": message,
                },
            )
        )
        return run_id


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
    ) -> None:
        await self._client.submit(
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


class RagAgentSubmitter:
    def __init__(self, client: AgentJobClient) -> None:
        self._client = client

    async def submit(
        self,
        user_id: str,
        novel_id: str,
        reference_id: str,
        content_hash: str,
    ) -> None:
        digest = hashlib.sha256(f"rag:{reference_id}:{content_hash}".encode()).hexdigest()[:32]
        run_id = f"rag-{digest}"
        await self._client.submit(
            AgentJobRequest(
                protocolVersion="1.0",
                jobId=run_id,
                kind="rag",
                runId=run_id,
                taskId=run_id,
                novelId=novel_id,
                userId=user_id,
                priority=30,
                payload={
                    "referenceId": reference_id,
                    "contentHash": content_hash,
                },
            )
        )
