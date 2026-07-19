from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from pydantic import TypeAdapter

from .state import GraphState

SNAPSHOT_VERSION = 1
RUNTIME_ONLY_FIELDS = {
    "runtime",
    "runtimeContext",
    "callbacks",
    "novelData",
    "controlEvents",
    "streamCallbacks",
    "eventCallbacks",
}
TYPESCRIPT_COMPATIBILITY_FIELDS = {
    "operationMode",
    "pendingUserResponse",
    "generatedContent",
    "pendingUpdates",
    "pendingAgentCall",
    "qualityCheckId",
    "artifactMode",
    "reviewerAgent",
    "reviewWorkerAgent",
    "reviserAgent",
    "pendingArtifactRevision",
}


def serialize_snapshot(state: Mapping[str, Any]) -> dict[str, Any]:
    forbidden = RUNTIME_ONLY_FIELDS.intersection(state)
    if forbidden:
        raise ValueError("稳定快照包含仅运行时字段：" + "、".join(sorted(forbidden)))
    stable = dict(state)
    return {
        "version": SNAPSHOT_VERSION,
        "state": json.loads(json.dumps(stable, ensure_ascii=False, default=_json_default)),
    }


def deserialize_snapshot(serialized: str | Mapping[str, Any]) -> GraphState:
    envelope = json.loads(serialized) if isinstance(serialized, str) else dict(serialized)
    if "version" in envelope or "state" in envelope:
        if envelope.get("version") != SNAPSHOT_VERSION or not isinstance(
            envelope.get("state"), dict
        ):
            raise ValueError("不支持的图状态快照版本")
        state = envelope["state"]
    else:
        state = {
            key: value
            for key, value in envelope.items()
            if key not in TYPESCRIPT_COMPATIBILITY_FIELDS
        }
    forbidden = RUNTIME_ONLY_FIELDS.intersection(state)
    if forbidden:
        raise ValueError("稳定快照包含仅运行时字段")
    if state.get("phase") == "awaiting_user_review":
        state = {**state, "phase": "waiting_user"}
    restored = TypeAdapter(GraphState).validate_python(state)
    target_word_count = restored.get("targetWordCount")
    if restored.get("workflowKind") != "short_medium" and (
        isinstance(target_word_count, bool)
        or not isinstance(target_word_count, int)
    ):
        raise ValueError("长篇目标字数无效")
    return restored


def to_typescript_snapshot(serialized: str | Mapping[str, Any]) -> dict[str, Any]:
    state = dict(deserialize_snapshot(serialized))
    operation = state.get("currentOperation")
    reviser_agent = (
        operation.get("primaryAgent")
        if state.get("pendingRevision") and isinstance(operation, dict)
        else None
    )
    return {
        **state,
        "phase": (
            "awaiting_user_review" if state.get("phase") == "waiting_user" else state.get("phase")
        ),
        "operationMode": "operation_graph",
        "pendingUserResponse": state.get("phase") == "waiting_user",
        "generatedContent": state.get("finalResponse", ""),
        "pendingUpdates": None,
        "pendingAgentCall": None,
        "qualityCheckId": None,
        "artifactMode": "review_loop" if state.get("activeArtifactId") else "none",
        "reviewerAgent": None,
        "reviewWorkerAgent": None,
        "reviserAgent": reviser_agent,
        "pendingArtifactRevision": state.get("pendingRevision"),
    }


def _json_default(value: object) -> object:
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    raise TypeError(f"图状态包含不可序列化值：{type(value).__name__}")
