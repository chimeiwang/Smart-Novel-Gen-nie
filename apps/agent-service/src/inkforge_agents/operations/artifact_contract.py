from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..artifacts.builder import resolve_builder_artifact
from ..artifacts.updates import extract_artifact_content
from .contracts import CreativeOperationKind
from .definitions import OperationDefinition

_BUILDER_EVENT_TYPES = frozenset(
    {
        "start_update_builder",
        "append_update_batch",
        "append_outline_tree",
        "put_update_text_block",
        "put_update_item_text_block",
        "put_update_item_text_blocks",
        "finish_update_builder",
    }
)
_ARTIFACT_TERMINAL_TYPES = frozenset(
    {
        "propose_updates",
        "finish_update_builder",
        "begin_artifact_output",
        "submit_beat_plan",
    }
)
_SELECTION_OPERATIONS = frozenset(
    {"rewrite_chapter_selection", "rewrite_outline_selection"}
)
_SELECTION_IDENTITY_FIELDS = (
    "operation",
    "resourceType",
    "resourceId",
    "baseUpdatedAt",
    "selectionStart",
    "selectionEnd",
    "baseContentHash",
    "selectedTextHash",
)
_SELECTION_EVENT_FIELDS = frozenset(
    {
        "type",
        "kind",
        "summary",
        "artifactKey",
        "reviewerAgent",
        "submitForReview",
        *_SELECTION_IDENTITY_FIELDS,
        "replacement",
    }
)


@dataclass(frozen=True, slots=True)
class ValidatedArtifactSubmission:
    event: dict[str, Any]
    content: str
    artifactKey: str


def stable_artifact_key(task_id: str, operation_kind: CreativeOperationKind) -> str:
    if not task_id:
        raise ValueError("ARTIFACT_CONTRACT_MISMATCH：生成草案标识时缺少 taskId")
    source = f"artifact-{task_id}-{operation_kind}"
    return "artifact-" + hashlib.sha256(source.encode("utf-8")).hexdigest()


def validate_artifact_submission(
    *,
    definition: OperationDefinition,
    events: list[dict[str, Any]],
    visible_content: str,
    authoritative_artifact: Mapping[str, Any] | None,
    task_id: str,
    operation_kind: CreativeOperationKind,
    selection_snapshot: Mapping[str, Any] | None = None,
) -> ValidatedArtifactSubmission:
    is_selection = operation_kind in _SELECTION_OPERATIONS
    if is_selection and selection_snapshot is None:
        raise ValueError("ARTIFACT_CONTRACT_MISMATCH：选区操作缺少 Core 冻结快照")
    try:
        resolved_builder = resolve_builder_artifact(events, visible_content)
    except ValueError as exc:
        raise ValueError(f"ARTIFACT_CONTRACT_MISMATCH：更新构建器无效：{exc}") from exc

    builder_events = [
        event for event in events if event.get("type") in _BUILDER_EVENT_TYPES
    ]
    builder_keys = {event.get("artifactKey") for event in builder_events}
    if builder_events and (
        any(not isinstance(key, str) or not key for key in builder_keys)
        or len(builder_keys) != 1
    ):
        raise ValueError(
            "ARTIFACT_CONTRACT_MISMATCH：更新构建器必须使用同一个有效 artifactKey"
        )
    direct_terminal_events = [
        event
        for event in events
        if event.get("type") in _ARTIFACT_TERMINAL_TYPES
        and event.get("type") != "finish_update_builder"
    ]
    invalid_terminal_events = [
        event
        for event in events
        if event.get("type") in _ARTIFACT_TERMINAL_TYPES
        and event.get("type") not in definition.artifactEventTypes
    ]
    if invalid_terminal_events:
        invalid_types = sorted(
            {str(event.get("type")) for event in invalid_terminal_events}
        )
        raise ValueError(
            "ARTIFACT_CONTRACT_MISMATCH：当前 Operation 不允许产物事件 "
            + "、".join(invalid_types)
        )
    if builder_events and definition.artifactKeyPolicy != "builder_or_generated":
        raise ValueError("ARTIFACT_CONTRACT_MISMATCH：当前 Operation 不允许更新构建器")
    if len(
        [event for event in events if event.get("type") == "finish_update_builder"]
    ) > 1:
        raise ValueError("ARTIFACT_CONTRACT_MISMATCH：更新构建器只能完成一次")

    direct_candidates = [
        event
        for event in direct_terminal_events
        if event.get("type") in definition.artifactEventTypes
    ]
    if builder_events and direct_candidates:
        raise ValueError("ARTIFACT_CONTRACT_MISMATCH：构建器与直接产物事件不能并存")
    candidates = [*direct_candidates]
    if resolved_builder is not None:
        candidates.append(resolved_builder)
    if len(candidates) != 1:
        raise ValueError("ARTIFACT_CONTRACT_MISMATCH：终止产物事件数量必须为一")

    event = dict(candidates[0])
    event_type = event.get("type")
    if event_type == "begin_artifact_output":
        actual_kind = event.get("kind")
        if is_selection:
            content = _validate_selection_submission(
                event,
                visible_content,
                selection_snapshot,
                operation_kind,
            )
        else:
            if any(
                field in event
                for field in (*_SELECTION_IDENTITY_FIELDS, "replacement")
            ):
                raise ValueError(
                    "ARTIFACT_CONTRACT_MISMATCH：普通正文 Operation 不得提交选区 replacement 字段"
                )
            if "content" in event:
                raw_content = event["content"]
                if not isinstance(raw_content, str) or not raw_content.strip():
                    raise ValueError(
                        "ARTIFACT_CONTRACT_MISMATCH：长文本草案 content 必须是非空字符串"
                    )
                content = raw_content
            else:
                try:
                    content = extract_artifact_content(visible_content)
                except ValueError as exc:
                    raise ValueError(
                        f"ARTIFACT_CONTRACT_MISMATCH：长文本草案边界无效：{exc}"
                    ) from exc
    elif event_type == "submit_beat_plan":
        actual_kind = "beat_plan"
        event["kind"] = actual_kind
        content = visible_content
    elif event_type == "propose_updates":
        actual_kind = "agent_updates"
        event["kind"] = actual_kind
        content = visible_content
    else:
        raise ValueError("ARTIFACT_CONTRACT_MISMATCH：无法识别产物事件")

    expected_kind = (
        definition.textArtifactKind
        if definition.artifactPolicy == "text"
        else "agent_updates"
    )
    if not isinstance(actual_kind, str) or actual_kind != expected_kind:
        raise ValueError(
            "ARTIFACT_CONTRACT_MISMATCH：草案类型不匹配，"
            f"期望 {expected_kind}，实际 {actual_kind}"
        )
    if authoritative_artifact is not None:
        authoritative_id = authoritative_artifact.get("id")
        authoritative_revision = authoritative_artifact.get("revision")
        if not isinstance(authoritative_id, str) or not authoritative_id:
            raise ValueError("ARTIFACT_REVISION_IDENTITY_MISMATCH：权威草案缺少 artifactId")
        if (
            isinstance(authoritative_revision, bool)
            or not isinstance(authoritative_revision, int)
            or authoritative_revision < 1
        ):
            raise ValueError("ARTIFACT_REVISION_IDENTITY_MISMATCH：权威草案 revision 无效")
        authoritative_kind = authoritative_artifact.get("kind")
        if authoritative_kind != expected_kind:
            raise ValueError("ARTIFACT_CONTRACT_MISMATCH：权威草案类型与 Operation 不一致")

    model_key = event.get("artifactKey")
    if model_key is not None and (not isinstance(model_key, str) or not model_key):
        raise ValueError("ARTIFACT_CONTRACT_MISMATCH：artifactKey 无效")
    if authoritative_artifact is not None:
        authoritative_key = authoritative_artifact.get("artifactKey")
        if not isinstance(authoritative_key, str) or not authoritative_key:
            raise ValueError("ARTIFACT_REVISION_IDENTITY_MISMATCH：权威草案缺少 artifactKey")
        if model_key is not None and model_key != authoritative_key:
            raise ValueError("ARTIFACT_REVISION_IDENTITY_MISMATCH：返工不能改变 artifactKey")
        artifact_key = authoritative_key
    elif resolved_builder is not None:
        if not isinstance(model_key, str) or not model_key:
            raise ValueError("ARTIFACT_CONTRACT_MISMATCH：更新构建器缺少 artifactKey")
        artifact_key = model_key
    else:
        artifact_key = model_key or stable_artifact_key(task_id, operation_kind)
    event["artifactKey"] = artifact_key
    return ValidatedArtifactSubmission(event, content, artifact_key)


def _validate_selection_submission(
    event: Mapping[str, Any],
    visible_content: str,
    snapshot: Mapping[str, Any] | None,
    operation_kind: CreativeOperationKind,
) -> str:
    if snapshot is None:
        raise ValueError("ARTIFACT_CONTRACT_MISMATCH：选区快照缺失")
    if set(event) - _SELECTION_EVENT_FIELDS:
        raise ValueError("ARTIFACT_CONTRACT_MISMATCH：选区产物包含未知字段")
    if event.get("operation") != operation_kind:
        raise ValueError("ARTIFACT_CONTRACT_MISMATCH：选区 Operation 身份不一致")
    expected_resources = {
        "rewrite_chapter_selection": {"chapter_content"},
        "rewrite_outline_selection": {"outline_content", "outline_node_content"},
    }[operation_kind]
    if event.get("resourceType") not in expected_resources:
        raise ValueError("ARTIFACT_CONTRACT_MISMATCH：选区资源类型与 Operation 不一致")
    for field in ("selectionStart", "selectionEnd"):
        value = event.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"ARTIFACT_CONTRACT_MISMATCH：{field} 无效")
    for field in _SELECTION_IDENTITY_FIELDS[1:]:
        if event.get(field) != snapshot.get(field):
            raise ValueError(
                f"ARTIFACT_CONTRACT_MISMATCH：选区身份字段不一致：{field}"
            )
    replacement = event.get("replacement")
    if not isinstance(replacement, str) or not replacement.strip():
        raise ValueError("ARTIFACT_CONTRACT_MISMATCH：replacement 不能为空")
    if "content" in event or (
        visible_content != "" and replacement != visible_content
    ):
        raise ValueError(
            "ARTIFACT_CONTRACT_MISMATCH：选区产物只能返回 replacement，"
            "且非空可见正文必须与 replacement 完全一致"
        )
    return replacement


def has_artifact_terminal_event(events: list[dict[str, Any]]) -> bool:
    return any(event.get("type") in _ARTIFACT_TERMINAL_TYPES for event in events)
