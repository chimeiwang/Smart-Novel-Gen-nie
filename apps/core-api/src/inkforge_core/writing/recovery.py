from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .schemas import SessionRecoveryState, WritingTaskSummary

RESUMABLE_PHASES = ("awaiting_user_review", "active", "waiting_call")
HISTORICAL_PHASES = frozenset({"completed", "error"})
RUNTIME_ONLY_FIELDS = frozenset(
    {"runtime", "novelData", "streamCallbacks", "eventCallbacks", "controlEvents"}
)
OPERATION_KINDS = frozenset(
    {
        "answer_question",
        "create_lore",
        "revise_lore",
        "create_outline",
        "revise_outline",
        "plan_chapter",
        "write_chapter",
        "rewrite_scene",
        "review_chapter",
        "sync_lore",
        "manage_foreshadowing",
    }
)


class InvalidGraphSnapshotError(ValueError):
    """表示持久快照格式错误或包含仅运行时数据。"""


@dataclass(frozen=True, slots=True)
class GraphSnapshot:
    task_id: str
    user_id: str
    novel_id: str
    chapter_id: str
    current_operation: dict[str, Any] | None
    operation_stage: str | None
    active_artifact_id: str | None


@dataclass(frozen=True, slots=True)
class TaskCandidate:
    id: str
    phase: str
    updated_at: datetime
    generated_content: str | None
    graph_state_json: str | None


def deserialize_graph_snapshot(
    serialized: str,
    *,
    expected_task_id: str | None = None,
    expected_user_id: str | None = None,
    expected_novel_id: str | None = None,
    expected_chapter_id: str | None = None,
) -> GraphSnapshot:
    try:
        parsed = json.loads(serialized)
    except (json.JSONDecodeError, TypeError):
        raise InvalidGraphSnapshotError("写作任务快照不是有效 JSON") from None
    if not isinstance(parsed, dict) or RUNTIME_ONLY_FIELDS.intersection(parsed):
        raise InvalidGraphSnapshotError("写作任务快照包含无效字段")

    identities: dict[str, str] = {}
    for key in ("taskId", "userId", "novelId", "chapterId"):
        value = parsed.get(key)
        if not isinstance(value, str) or not value:
            raise InvalidGraphSnapshotError("写作任务快照缺少资源身份")
        identities[key] = value
    target_word_count = parsed.get("targetWordCount")
    if isinstance(target_word_count, bool) or not isinstance(target_word_count, int):
        raise InvalidGraphSnapshotError("写作任务快照缺少目标字数")
    if not isinstance(parsed.get("conversationHistory"), list):
        raise InvalidGraphSnapshotError("写作任务快照缺少会话历史")

    expectations = (
        (identities["taskId"], expected_task_id),
        (identities["userId"], expected_user_id),
        (identities["novelId"], expected_novel_id),
        (identities["chapterId"], expected_chapter_id),
    )
    if any(expected is not None and actual != expected for actual, expected in expectations):
        raise InvalidGraphSnapshotError("写作任务快照资源归属不匹配")

    operation = parsed.get("currentOperation")
    if operation is not None:
        if (
            not isinstance(operation, dict)
            or not isinstance(operation.get("kind"), str)
            or operation["kind"] not in OPERATION_KINDS
        ):
            raise InvalidGraphSnapshotError("写作任务快照的创作操作无效")
    operation_stage = parsed.get("operationStage")
    if operation_stage is not None and not isinstance(operation_stage, str):
        raise InvalidGraphSnapshotError("写作任务快照的操作阶段无效")
    artifact_review = parsed.get("artifactReview")
    artifact_id: str | None = None
    if artifact_review is not None:
        if not isinstance(artifact_review, dict):
            raise InvalidGraphSnapshotError("写作任务快照的草案状态无效")
        candidate = artifact_review.get("activeArtifactId")
        if candidate is not None and not isinstance(candidate, str):
            raise InvalidGraphSnapshotError("写作任务快照的草案标识无效")
        artifact_id = candidate
    if artifact_id is None:
        legacy_id = parsed.get("activeArtifactId")
        if legacy_id is not None and not isinstance(legacy_id, str):
            raise InvalidGraphSnapshotError("写作任务快照的兼容草案标识无效")
        artifact_id = legacy_id

    return GraphSnapshot(
        task_id=identities["taskId"],
        user_id=identities["userId"],
        novel_id=identities["novelId"],
        chapter_id=identities["chapterId"],
        current_operation=operation,
        operation_stage=operation_stage,
        active_artifact_id=artifact_id,
    )


def select_recovery_state(tasks: list[TaskCandidate]) -> SessionRecoveryState:
    ordered = sorted(tasks, key=lambda item: item.updated_at, reverse=True)
    current = next(
        (
            _to_summary(task)
            for phase in RESUMABLE_PHASES
            for task in ordered
            if task.phase == phase
        ),
        None,
    )
    last = next(
        (_to_summary(task) for task in ordered if task.phase in HISTORICAL_PHASES),
        None,
    )
    return SessionRecoveryState(currentTask=current, lastTask=last)


def validate_resume_session_binding(
    requested_session_id: str | None, task_session_id: str | None
) -> None:
    if requested_session_id is None:
        return
    if requested_session_id != task_session_id:
        raise ValueError("当前任务不属于所选写作会话")


def _to_summary(task: TaskCandidate) -> WritingTaskSummary:
    snapshot = (
        deserialize_graph_snapshot(task.graph_state_json, expected_task_id=task.id)
        if task.graph_state_json
        else None
    )
    active_artifact_id = snapshot.active_artifact_id if snapshot is not None else None
    if active_artifact_id is None and task.phase == "awaiting_user_review":
        active_artifact_id = task.generated_content
    return WritingTaskSummary(
        id=task.id,
        phase=task.phase,
        updatedAt=task.updated_at,
        hasAwaitingReviewArtifact=(
            task.phase == "awaiting_user_review" and active_artifact_id is not None
        ),
        currentOperation=(snapshot.current_operation if snapshot is not None else None),
        operationStage=(snapshot.operation_stage if snapshot is not None else None),
        activeArtifactId=active_artifact_id,
    )
