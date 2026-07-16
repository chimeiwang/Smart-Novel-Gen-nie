from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, cast

from pydantic import JsonValue

from ..clients.core import CoreServiceClient, RunResource
from ..operations.contracts import CreativeOperationKind
from ..operations.definitions import OPERATION_DEFINITIONS
from ..runtime.agent_runner import AgentRunner, AgentRunRequest
from ..runtime.execution import AgentExecutionMode
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
                jobId=context.jobId,
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

    def hydrate(
        self,
        resource: RunResource,
        state: Mapping[str, Any],
        active_artifact: Mapping[str, Any],
    ) -> None:
        artifact_id = _hydration_text(active_artifact, "id")
        task_id = _hydration_text(active_artifact, "taskId")
        novel_id = _hydration_text(active_artifact, "novelId")
        chapter_id = _hydration_text(active_artifact, "chapterId")
        artifact_key = _hydration_text(active_artifact, "artifactKey")
        kind = _hydration_text(active_artifact, "kind")
        status = _hydration_text(active_artifact, "status")
        created_by_agent = _hydration_text(active_artifact, "createdByAgent")
        revision = active_artifact.get("revision")
        payload = active_artifact.get("payload")
        if (
            isinstance(revision, bool)
            or not isinstance(revision, int)
            or revision < 1
            or not isinstance(payload, dict)
            or payload.get("kind") != kind
        ):
            raise _artifact_identity_mismatch("草案修订号或载荷无效")
        workflow_run_id = active_artifact.get("workflowRunId")
        if workflow_run_id is not None and (
            not isinstance(workflow_run_id, str) or not workflow_run_id
        ):
            raise _artifact_identity_mismatch("workflowRunId 无效")
        state_task_id = _hydration_text(state, "taskId")
        state_user_id = _hydration_text(state, "userId")
        state_novel_id = _hydration_text(state, "novelId")
        state_chapter_id = _hydration_text(state, "chapterId")
        state_artifact_id = _hydration_text(state, "activeArtifactId")
        if (
            state_user_id != resource.userId
            or state_task_id != resource.taskId
            or state_novel_id != resource.novelId
            or task_id != resource.taskId
            or novel_id != resource.novelId
            or chapter_id != state_chapter_id
            or artifact_id != state_artifact_id
        ):
            raise _artifact_identity_mismatch("草案与当前运行资源不一致")
        try:
            definition = OPERATION_DEFINITIONS[_operation_kind(dict(state))]
        except ValueError:
            raise _artifact_identity_mismatch("当前 Operation 身份无效") from None
        expected_kind = (
            "agent_updates"
            if definition.artifactPolicy == "agent_updates"
            else definition.textArtifactKind
        )
        if expected_kind is None or kind != expected_kind:
            raise _artifact_identity_mismatch("草案类型与当前 Operation 不一致")
        request = {
            "runId": resource.runId,
            "taskId": task_id,
            "novelId": novel_id,
            "chapterId": chapter_id,
            "workflowRunId": workflow_run_id,
            "artifactKey": artifact_key,
            "kind": kind,
            "status": status,
            "title": active_artifact.get("title"),
            "summary": active_artifact.get("summary"),
            "payload": dict(payload),
            "diff": active_artifact.get("diff"),
            "createdByAgent": created_by_agent,
            "reviewerAgent": active_artifact.get("reviewerAgent"),
        }
        current = self._records.get(artifact_id)
        if current is not None:
            _require_same_runtime_owner(current.resource, resource)
            for field in ("taskId", "novelId", "chapterId", "artifactKey", "kind"):
                if current.request.get(field) != request.get(field):
                    raise _artifact_identity_mismatch("同一草案的稳定身份字段发生变化")
        self._records[artifact_id] = _ArtifactRecord(resource, request, revision)

    def release(self, artifact_id: str, resource: RunResource) -> None:
        record = self._require_record(artifact_id)
        _require_same_runtime_owner(record.resource, resource)
        del self._records[artifact_id]

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
        artifact_id = _required_text(state, "activeArtifactId")
        record = self._require_record(artifact_id)
        if event.get("artifactKey") != record.request.get("artifactKey"):
            raise RuntimeError(
                "ARTIFACT_REVISION_IDENTITY_MISMATCH：返工 artifactKey 与权威草案不一致"
            )
        return await self._save(
            state,
            event,
            content,
            status="under_review",
            expected_artifact_id=artifact_id,
        )

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
        expected_artifact_id: str | None = None,
    ) -> str:
        resource = _resource(state)
        agent_id = _agent_id(state)
        kind, payload = _artifact_payload(event, content)
        artifact_key = event.get("artifactKey")
        if not isinstance(artifact_key, str) or not artifact_key:
            raise ValueError("ARTIFACT_CONTRACT_MISMATCH：待审核草案缺少 artifactKey")
        request = {
            "runId": resource.runId,
            "taskId": resource.taskId,
            "novelId": resource.novelId,
            "chapterId": state.get("chapterId"),
            "workflowRunId": None,
            "artifactKey": artifact_key,
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
        if expected_artifact_id is not None and artifact_id != expected_artifact_id:
            raise RuntimeError(
                "ARTIFACT_REVISION_IDENTITY_MISMATCH：Core 返回了不同的草案标识"
            )
        current = self._records.get(artifact_id)
        if current is not None:
            _require_same_runtime_owner(current.resource, resource)
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

    async def run(
        self,
        agent_id: str,
        state: dict[str, Any],
        *,
        execution_mode: AgentExecutionMode,
        operation_kind: CreativeOperationKind,
    ) -> dict[str, Any]:
        if _operation_kind(state) != operation_kind:
            raise ValueError("当前 Operation kind 与显式执行参数不一致")
        resource = _resource(state)
        context = ToolContext(
            userId=resource.userId,
            novelId=resource.novelId,
            taskId=resource.taskId,
            runId=resource.runId,
            jobId=resource.jobId,
            agentId=agent_id,
        )
        context_messages: list[str]
        execution_instructions: list[str]
        conversation_messages: list[dict[str, object]]
        artifact_id = state.get("activeArtifactId")
        if execution_mode == "primary":
            context_messages = [str(item) for item in state.get("contextMessages", [])]
            execution_instructions = [
                str(item) for item in state.get("executionInstructions", [])
            ]
            conversation_messages = [
                dict(item)
                for item in state.get("conversationHistory", [])
                if isinstance(item, dict)
            ]
        else:
            if not isinstance(artifact_id, str) or not artifact_id:
                raise RuntimeError("当前执行模式缺少权威待审核草案标识")
            artifact_context = self._artifacts.review_context(artifact_id)
            conversation_messages = []
            if execution_mode == "reviewer":
                context_messages = [_reviewer_context(artifact_context)]
                execution_instructions = [
                    "当前处于复审模式。只处理只读资料中的 Core 权威草案；"
                    "不要重新读取或猜测其他草案，完成后只调用一次 submit_evaluation。"
                ]
            elif execution_mode == "reviser":
                context_messages = [_reviser_context(state, artifact_context)]
                execution_instructions = [
                    "当前处于完整返工模式。根据只读资料中的修改要求重写完整草案，"
                    "保持权威 artifactKey 和原产物类型，完成后使用当前 Operation 的产物提交工具。",
                    *[
                        str(item)
                        for item in state.get("executionInstructions", [])
                    ],
                ]
            else:
                raise ValueError("CoreGraphAgentExecutor 不支持 quality 执行模式")
        result = await self._runner.run(
            AgentRunRequest(
                agentId=cast(Any, agent_id),
                executionMode=execution_mode,
                operationKind=operation_kind,
                userMessage=_required_text(state, "userMessage"),
                contextMessages=context_messages,
                executionInstructions=execution_instructions,
                conversationMessages=conversation_messages,
                toolContext=context,
            )
        )
        payload = result.model_dump()
        if execution_mode == "reviewer" and isinstance(artifact_id, str):
            for event in payload.get("controlEvents", []):
                if isinstance(event, dict) and event.get("type") == "submit_evaluation":
                    await self._artifacts.submit_evaluation(state, artifact_id, agent_id, event)
        return payload


def _operation_kind(state: dict[str, Any]) -> CreativeOperationKind:
    operation = state.get("currentOperation")
    kind = operation.get("kind") if isinstance(operation, dict) else None
    if not isinstance(kind, str) or kind not in OPERATION_DEFINITIONS:
        raise ValueError("当前 Operation kind 无效")
    return kind


def _reviewer_context(artifact: dict[str, Any]) -> str:
    readonly = {
        "artifactId": artifact.get("id"),
        "artifactKey": artifact.get("artifactKey"),
        "revision": artifact.get("revision"),
        "kind": artifact.get("kind"),
        "title": artifact.get("title"),
        "summary": artifact.get("summary"),
        "payload": artifact.get("payload"),
    }
    return "当前待审核草案权威内容：" + json.dumps(
        readonly,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _reviser_context(state: dict[str, Any], artifact: dict[str, Any]) -> str:
    pending = state.get("pendingRevision")
    if not isinstance(pending, dict):
        raise RuntimeError("返工执行缺少合并后的修改要求")
    required_changes = pending.get("requiredChanges")
    if not isinstance(required_changes, str) or not required_changes:
        raise RuntimeError("返工执行缺少合并后的修改要求")
    readonly = {
        "artifactId": artifact.get("id"),
        "artifactKey": artifact.get("artifactKey"),
        "revision": artifact.get("revision"),
        "kind": artifact.get("kind"),
        "artifactIteration": state.get("artifactIteration", 0),
        "requiredChanges": required_changes,
        "payload": artifact.get("payload"),
        "title": artifact.get("title"),
        "summary": artifact.get("summary"),
    }
    return "当前返工草案权威内容：" + json.dumps(
        readonly,
        ensure_ascii=False,
        separators=(",", ":"),
    )


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
    runtime_context = state.get("runtimeContext")
    if not isinstance(runtime_context, dict):
        raise ValueError("图状态缺少仅运行时上下文")
    raw_resource = runtime_context.get("runResource")
    if not isinstance(raw_resource, dict):
        raise ValueError("仅运行时上下文缺少运行资源")
    resource = RunResource.model_validate(raw_resource)
    if not resource.jobId:
        raise ValueError("写作运行资源缺少当前队列 jobId")
    return resource


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


def _hydration_text(value: Mapping[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise _artifact_identity_mismatch(f"缺少有效字段 {key}")
    return item


def _artifact_identity_mismatch(detail: str) -> RuntimeError:
    return RuntimeError(f"ARTIFACT_REVISION_IDENTITY_MISMATCH：{detail}")


def _require_same_runtime_owner(current: RunResource, incoming: RunResource) -> None:
    if current.runId != incoming.runId or current.jobId != incoming.jobId:
        raise RuntimeError(
            "ARTIFACT_RUNTIME_IDENTITY_MISMATCH：草案已由其他运行命令持有"
        )


def _revision(response: dict[str, Any]) -> int:
    value = response.get("revision")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise RuntimeError("核心服务未返回有效草案修订号")
    return value


def _idempotency(run_id: str, payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(f"{run_id}:{serialized}".encode()).hexdigest()[:32]
    return f"artifact-{digest}"
