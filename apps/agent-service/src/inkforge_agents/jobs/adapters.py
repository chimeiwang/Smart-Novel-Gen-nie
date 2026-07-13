from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Protocol, cast

from pydantic import JsonValue

from ..clients.core import CoreServiceClient, RunResource
from ..runtime.agent_runner import AgentRunner, AgentRunRequest
from ..tools.registry import ToolContext


class CoreToolGateway:
    def __init__(
        self,
        core: CoreServiceClient,
        embeddings: QueryEmbeddingPort | None = None,
    ) -> None:
        self._core = core
        self._embeddings = embeddings

    async def execute(
        self,
        tool_name: str,
        context: ToolContext,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        forwarded = dict(arguments)
        if tool_name == "semantic_search_references" and self._embeddings is not None:
            query = forwarded.get("query")
            if not isinstance(query, str) or not query.strip():
                raise ValueError("语义检索必须提供非空 query")
            vectors = await self._embeddings.embed([query])
            if len(vectors) != 1:
                raise RuntimeError("嵌入服务返回数量与查询数量不一致")
            forwarded["query_embedding"] = vectors[0]
        return await self._core.call_tool(
            RunResource(
                userId=context.userId,
                novelId=context.novelId,
                taskId=context.taskId,
                runId=context.runId,
            ),
            context.agentId,
            tool_name,
            cast(dict[str, JsonValue], forwarded),
        )


class QueryEmbeddingPort(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


@dataclass(slots=True)
class _ArtifactRecord:
    resource: RunResource
    request: dict[str, Any]
    revision: int


class CoreArtifactPort:
    def __init__(self, core: CoreServiceClient) -> None:
        self._core = core
        self._records: dict[str, _ArtifactRecord] = {}

    async def submit(
        self,
        state: dict[str, Any],
        event: dict[str, Any],
        content: str,
    ) -> str:
        return await self._save(state, event, content, status="under_review")

    async def revise(
        self,
        state: dict[str, Any],
        event: dict[str, Any],
        content: str,
    ) -> str:
        return await self._save(state, event, content, status="under_review")

    async def mark_awaiting_user(self, artifact_id: str) -> None:
        record = self._require_record(artifact_id)
        request = {**record.request, "status": "awaiting_user"}
        response = await self._core.create_artifact(
            record.resource,
            request,
            idempotency_key=_idempotency(record.resource.runId, request),
        )
        record.request = request
        record.revision = _revision(response)

    async def apply_patch(self, artifact_id: str, patches: list[dict[str, Any]]) -> None:
        del artifact_id, patches
        raise RuntimeError("跨服务草案补丁暂未启用，将改用完整返工")

    async def apply(self, artifact_id: str) -> None:
        del artifact_id
        # 正式写入只能由浏览器授权的 Core 决策接口完成。

    async def discard(self, artifact_id: str) -> None:
        del artifact_id
        # 丢弃也由 Core 的用户决策接口完成，恢复图只收敛运行状态。

    async def submit_evaluation(
        self,
        state: dict[str, Any],
        artifact_id: str,
        evaluator: str,
        event: dict[str, Any],
    ) -> None:
        record = self._require_record(artifact_id)
        payload = {
            "runId": record.resource.runId,
            "taskId": record.resource.taskId,
            "novelId": record.resource.novelId,
            "revision": record.revision,
            "evaluatorAgent": evaluator,
            "verdict": event["verdict"],
            "summary": event["summary"],
            "requiredChanges": event.get("requiredChanges"),
        }
        await self._core.submit_evaluation(
            record.resource,
            artifact_id,
            payload,
            idempotency_key=_idempotency(record.resource.runId, payload),
        )

    def review_context(self, artifact_id: str) -> dict[str, Any]:
        record = self._require_record(artifact_id)
        return {
            "id": artifact_id,
            "revision": record.revision,
            **dict(record.request),
        }

    async def _save(
        self,
        state: dict[str, Any],
        event: dict[str, Any],
        content: str,
        *,
        status: str,
    ) -> str:
        resource = _resource(state)
        agent_id = _agent_id(state)
        kind, payload = _artifact_payload(event, content)
        request = {
            "runId": resource.runId,
            "taskId": resource.taskId,
            "novelId": resource.novelId,
            "chapterId": state.get("chapterId"),
            "workflowRunId": None,
            "artifactKey": event.get("artifactKey"),
            "kind": kind,
            "status": status,
            "title": event.get("title"),
            "summary": event.get("summary"),
            "payload": payload,
            "diff": None,
            "createdByAgent": agent_id,
            "reviewerAgent": event.get("reviewerAgent"),
        }
        response = await self._core.create_artifact(
            resource,
            request,
            idempotency_key=_idempotency(resource.runId, request),
        )
        artifact_id = response.get("id")
        if not isinstance(artifact_id, str) or not artifact_id:
            raise RuntimeError("核心服务未返回待审核草案标识")
        self._records[artifact_id] = _ArtifactRecord(resource, request, _revision(response))
        return artifact_id

    def _require_record(self, artifact_id: str) -> _ArtifactRecord:
        record = self._records.get(artifact_id)
        if record is None:
            raise RuntimeError("当前运行缺少待审核草案上下文")
        return record


class CoreGraphAgentExecutor:
    def __init__(self, runner: AgentRunner, artifacts: CoreArtifactPort) -> None:
        self._runner = runner
        self._artifacts = artifacts

    async def run(self, agent_id: str, state: dict[str, Any]) -> dict[str, Any]:
        context = ToolContext(
            userId=_required_text(state, "userId"),
            novelId=_required_text(state, "novelId"),
            taskId=_required_text(state, "taskId"),
            runId=_required_text(state, "taskId"),
            agentId=agent_id,
        )
        context_messages = [str(item) for item in state.get("contextMessages", [])]
        artifact_context: dict[str, Any] | None = None
        artifact_id = state.get("activeArtifactId")
        if isinstance(artifact_id, str):
            try:
                artifact_context = self._artifacts.review_context(artifact_id)
            except RuntimeError:
                artifact_context = None
        if artifact_context is not None:
            context_messages.append(
                "当前待审核草案权威内容："
                + json.dumps(artifact_context, ensure_ascii=False, separators=(",", ":"))
                + "\n读取工具不可用，请直接审阅以上草案并调用 submit_evaluation。"
            )
        result = await self._runner.run(
            AgentRunRequest(
                agentId=cast(Any, agent_id),
                userMessage=_required_text(state, "userMessage"),
                contextMessages=context_messages,
                conversationMessages=[
                    dict(item)
                    for item in state.get("conversationHistory", [])
                    if isinstance(item, dict)
                ],
                toolMode=("control_only" if artifact_context is not None else "all"),
                toolContext=context,
            )
        )
        payload = result.model_dump()
        if isinstance(artifact_id, str):
            for event in payload.get("controlEvents", []):
                if isinstance(event, dict) and event.get("type") == "submit_evaluation":
                    await self._artifacts.submit_evaluation(state, artifact_id, agent_id, event)
        return payload


def _artifact_payload(event: dict[str, Any], content: str) -> tuple[str, dict[str, Any]]:
    event_type = event.get("type")
    if event_type == "propose_updates":
        return "agent_updates", {"kind": "agent_updates", "updates": event.get("updates", {})}
    if event_type == "submit_beat_plan":
        beat_plan = {key: value for key, value in event.items() if key not in {"type"}}
        return "beat_plan", {"kind": "beat_plan", "beatPlan": beat_plan}
    kind = event.get("kind")
    if not isinstance(kind, str) or not kind:
        raise ValueError("待审核草案控制事件缺少 kind")
    return kind, {"kind": kind, "content": content}


def _resource(state: dict[str, Any]) -> RunResource:
    task_id = _required_text(state, "taskId")
    return RunResource(
        userId=_required_text(state, "userId"),
        novelId=_required_text(state, "novelId"),
        taskId=task_id,
        runId=task_id,
    )


def _agent_id(state: dict[str, Any]) -> str:
    value = state.get("activeAgent")
    if value not in {"设定", "剧情", "写作", "校验", "编辑"}:
        operation = state.get("currentOperation")
        value = operation.get("primaryAgent") if isinstance(operation, dict) else None
    if value not in {"设定", "剧情", "写作", "校验", "编辑"}:
        raise ValueError("图状态缺少有效智能体身份")
    return cast(str, value)


def _required_text(state: dict[str, Any], key: str) -> str:
    value = state.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"图状态缺少 {key}")
    return value


def _revision(response: dict[str, Any]) -> int:
    value = response.get("revision")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise RuntimeError("核心服务未返回有效草案修订号")
    return value


def _idempotency(run_id: str, payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(f"{run_id}:{serialized}".encode()).hexdigest()[:32]
    return f"artifact-{digest}"
