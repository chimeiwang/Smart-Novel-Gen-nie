from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast

from inkforge_contracts.short_medium import (
    ShortMediumCheckResult,
    ShortMediumDocumentResult,
    ShortMediumReplacementResult,
    ShortMediumRunPayload,
)
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import (
    Chapter,
    Novel,
    Outline,
    ReviewArtifact,
    ReviewArtifactRevision,
    WritingBible,
    WritingRunCommand,
    WritingTask,
)
from ..errors import ApiError
from ..writing.schemas import ShortMediumStartWritingRunRequest
from .repository import (
    SHORT_MEDIUM_MANUSCRIPT_PREFIX,
    SHORT_MEDIUM_OUTLINE_PREFIX,
    VersionRecord,
    version_record_from_values,
)
from .schemas import (
    DocumentVersionPayload,
    bind_confirmation_hash,
    build_document_diff,
    content_sha256,
)


@dataclass(frozen=True, slots=True)
class ShortMediumRunSource:
    chapter_id: str
    target_total_word_count: int
    source_kind: str
    source_text: str
    document_content: str
    current_document_version: VersionRecord | None
    outline_content: str
    current_outline_version: VersionRecord | None
    bound_outline_version: VersionRecord | None = None


@dataclass(frozen=True, slots=True)
class MaterializedShortMediumResult:
    content: str | None
    check_report: dict[str, Any] | None


def _require_clean(
    work_content: str,
    current: VersionRecord | None,
) -> None:
    expected_hash = (
        current.payload.contentHash if current is not None else content_sha256("")
    )
    if content_sha256(work_content) != expected_hash:
        raise ApiError(
            status_code=409,
            code="SHORT_MEDIUM_WORK_DRAFT_DIRTY",
            message="工作稿存在未提交修改，请先提交或放弃修改",
        )


def _require_base(
    current: VersionRecord | None,
    requested_id: str | None,
) -> None:
    current_id = current.id if current is not None else None
    if requested_id != current_id:
        raise ApiError(
            status_code=409,
            code="SHORT_MEDIUM_BASE_VERSION_CONFLICT",
            message="当前版本已经变化，请重新发起任务",
            details={"currentVersionId": current_id},
        )


def assemble_short_medium_run_payload(
    request: ShortMediumStartWritingRunRequest,
    source: ShortMediumRunSource,
) -> ShortMediumRunPayload:
    current = source.current_document_version
    _require_base(current, request.baseVersionId)
    _require_clean(source.document_content, current)
    base_values = (
        {
            "baseVersionId": current.id,
            "baseContent": current.content,
            "baseContentHash": current.payload.contentHash,
        }
        if current is not None
        else {}
    )
    common: dict[str, Any] = {
        "workflow": "short_medium",
        "operation": request.operation,
        "documentType": request.documentType,
        "chapterId": (
            source.chapter_id if request.documentType == "manuscript" else None
        ),
        "userInstruction": request.userInstruction,
        "targetTotalWordCount": source.target_total_word_count,
        **base_values,
    }
    if request.operation == "generate_outline":
        common.update(
            sourceKind=source.source_kind,
            sourceText=source.source_text,
        )
        return ShortMediumRunPayload.model_validate(common)

    if request.operation == "generate_manuscript":
        outline = source.current_outline_version
        if outline is None or request.sourceOutlineVersionId != outline.id:
            raise ApiError(
                status_code=409,
                code="SHORT_MEDIUM_OUTLINE_VERSION_CONFLICT",
                message="来源大纲版本已经变化，请重新发起正文生成",
            )
        _require_clean(source.outline_content, outline)
        common.update(
            sourceOutlineVersionId=outline.id,
            sourceOutlineContent=outline.content,
            sourceOutlineContentHash=outline.payload.contentHash,
            sourceKind=source.source_kind,
            sourceText=source.source_text,
        )
        return ShortMediumRunPayload.model_validate(common)

    if request.operation == "replace_selection":
        if current is None:
            raise ApiError(
                status_code=409,
                code="SHORT_MEDIUM_BASE_VERSION_REQUIRED",
                message="选区修改必须基于已确认版本",
            )
        start = cast(int, request.selectionStart)
        end = cast(int, request.selectionEnd)
        if end > len(current.content):
            raise ApiError(
                status_code=409,
                code="SHORT_MEDIUM_SELECTION_RANGE_INVALID",
                message="选区码点范围超出基础版本",
            )
        selected = current.content[start:end]
        selected_hash = content_sha256(selected)
        if selected_hash != request.selectedTextHash:
            raise ApiError(
                status_code=409,
                code="SHORT_MEDIUM_SELECTION_HASH_CONFLICT",
                message="选区内容已经变化，请重新选择",
            )
        common.update(
            selectionStart=start,
            selectionEnd=end,
            selectedText=selected,
            selectedTextHash=selected_hash,
            contextBefore=current.content[:start],
            contextAfter=current.content[end:],
        )
        if request.documentType == "manuscript":
            outline = source.bound_outline_version or source.current_outline_version
            if (
                outline is None
                or current.payload.sourceOutlineVersionId != outline.id
            ):
                raise ApiError(
                    status_code=409,
                    code="SHORT_MEDIUM_SOURCE_OUTLINE_MISSING",
                    message="正文基础版本的来源大纲不存在",
                )
            common.update(
                sourceOutlineVersionId=outline.id,
                sourceOutlineContent=outline.content,
                sourceOutlineContentHash=outline.payload.contentHash,
            )
        return ShortMediumRunPayload.model_validate(common)

    if current is None:
        raise ApiError(
            status_code=409,
            code="SHORT_MEDIUM_BASE_VERSION_REQUIRED",
            message="全文检查必须基于已确认正文版本",
        )
    if request.documentType == "manuscript":
        outline = source.bound_outline_version or source.current_outline_version
        if outline is not None:
            common.update(
                sourceOutlineVersionId=outline.id,
                sourceOutlineContent=outline.content,
                sourceOutlineContentHash=outline.payload.contentHash,
            )
    return ShortMediumRunPayload.model_validate(common)


def materialize_short_medium_result(
    payload: ShortMediumRunPayload,
    result: dict[str, Any],
) -> MaterializedShortMediumResult:
    try:
        if payload.operation in {"generate_outline", "generate_manuscript"}:
            document = ShortMediumDocumentResult.model_validate(result)
            if (
                document.operation != payload.operation
                or document.documentType != payload.documentType
                or document.sourceOutlineVersionId
                != payload.sourceOutlineVersionId
            ):
                raise ValueError("文档结果身份不一致")
            if payload.operation == "generate_manuscript":
                source_text = payload.sourceText
                if (
                    payload.sourceKind == "opening"
                    and source_text is not None
                    and not document.content.startswith(source_text)
                ) or (
                    payload.sourceKind == "ending"
                    and source_text is not None
                    and not document.content.endswith(source_text)
                ):
                    raise ApiError(
                        status_code=409,
                        code="SHORT_MEDIUM_FIXED_SOURCE_CHANGED",
                        message="生成正文改动了固定开头或结尾",
                    )
            return MaterializedShortMediumResult(
                content=document.content,
                check_report=None,
            )
        if payload.operation == "replace_selection":
            replacement = ShortMediumReplacementResult.model_validate(result)
            identities = (
                (replacement.documentType, payload.documentType),
                (replacement.baseVersionId, payload.baseVersionId),
                (replacement.baseContentHash, payload.baseContentHash),
                (replacement.selectionStart, payload.selectionStart),
                (replacement.selectionEnd, payload.selectionEnd),
                (replacement.selectedTextHash, payload.selectedTextHash),
            )
            if any(actual != expected for actual, expected in identities):
                raise ValueError("选区结果身份不一致")
            base = payload.baseContent
            start = payload.selectionStart
            end = payload.selectionEnd
            if base is None or start is None or end is None:
                raise ValueError("选区任务快照不完整")
            content = base[:start] + replacement.replacement + base[end:]
            if content[:start] != base[:start] or content[
                start + len(replacement.replacement) :
            ] != base[end:]:
                raise ValueError("选区外内容发生变化")
            return MaterializedShortMediumResult(content=content, check_report=None)
        check = ShortMediumCheckResult.model_validate(result)
        if check.baseVersionId != payload.baseVersionId:
            raise ValueError("检查结果基础版本不一致")
        return MaterializedShortMediumResult(
            content=None,
            check_report=dict(check.report),
        )
    except (ValidationError, ValueError) as exc:
        raise ApiError(
            status_code=409,
            code="SHORT_MEDIUM_COMPLETION_IDENTITY_MISMATCH",
            message="中短篇完成结果与任务快照不一致",
        ) from exc


async def finalize_short_medium_completion(
    session: AsyncSession,
    task: WritingTask,
    command: WritingRunCommand,
    result: dict[str, Any],
) -> dict[str, Any]:
    """在完成回调事务中校验结果，并创建或重放候选版本。"""
    try:
        payload = ShortMediumRunPayload.model_validate_json(command.payloadJson)
    except ValidationError as exc:
        raise ApiError(
            status_code=409,
            code="SHORT_MEDIUM_RUN_SNAPSHOT_INVALID",
            message="中短篇任务快照无效",
        ) from exc
    if payload.chapterId is not None and payload.chapterId != task.chapterId:
        raise ApiError(
            status_code=409,
            code="SHORT_MEDIUM_COMPLETION_IDENTITY_MISMATCH",
            message="中短篇完成结果与任务身份不一致",
        )
    materialized = materialize_short_medium_result(payload, result)
    if payload.operation == "full_check":
        return {**result, "checkReport": materialized.check_report or {}}
    content = cast(str, materialized.content)
    artifact_key = (
        f"{SHORT_MEDIUM_OUTLINE_PREFIX}{task.novelId}"
        if payload.documentType == "outline"
        else f"{SHORT_MEDIUM_MANUSCRIPT_PREFIX}{task.chapterId}"
    )
    if payload.documentType == "outline":
        document = await session.scalar(
            select(Outline)
            .where(Outline.novelId == task.novelId)
            .with_for_update()
        )
    else:
        document = await session.scalar(
            select(Chapter)
            .where(
                Chapter.id == task.chapterId,
                Chapter.novelId == task.novelId,
            )
            .with_for_update()
        )
    if document is None:
        raise ApiError(
            status_code=404,
            code="SHORT_MEDIUM_DOCUMENT_NOT_FOUND",
            message="中短篇工作稿不存在",
        )
    if content_sha256(document.content) != (
        payload.baseContentHash or content_sha256("")
    ):
        raise ApiError(
            status_code=409,
            code="SHORT_MEDIUM_WORK_DRAFT_DIRTY",
            message="任务运行期间工作稿已经变化，未创建候选版本",
        )
    artifacts = list(
        (
            await session.scalars(
                select(ReviewArtifact)
                .where(
                    ReviewArtifact.novelId == task.novelId,
                    ReviewArtifact.artifactKey == artifact_key,
                )
                .order_by(ReviewArtifact.createdAt, ReviewArtifact.id)
                .with_for_update()
            )
        ).all()
    )
    versions = [
        version_record_from_values(
            id=artifact.id,
            novel_id=artifact.novelId,
            chapter_id=artifact.chapterId,
            artifact_key=artifact_key,
            status=artifact.status,
            summary=artifact.summary,
            payload_json=artifact.payloadJson,
            diff_json=artifact.diffJson,
            created_by_agent=artifact.createdByAgent,
            task_id=artifact.taskId,
            created_at=artifact.createdAt,
            updated_at=artifact.updatedAt,
            applied_at=artifact.appliedAt,
        )
        for artifact in artifacts
    ]
    replay = next(
        (
            version
            for version in versions
            if version.payload.sourceTaskId == task.id
            and version.payload.sourceJobId == command.id
        ),
        None,
    )
    if replay is not None:
        command.artifactId = replay.id
        return {**result, "candidateVersionId": replay.id}
    current = _current(versions)
    if (current.id if current is not None else None) != payload.baseVersionId:
        raise ApiError(
            status_code=409,
            code="SHORT_MEDIUM_BASE_VERSION_CONFLICT",
            message="任务完成时当前版本已经变化，未创建候选版本",
        )
    version_payload = DocumentVersionPayload(
        kind=(
            "outline_draft"
            if payload.documentType == "outline"
            else "chapter_draft"
        ),
        documentType=payload.documentType,
        versionNumber=max(
            (version.version_number for version in versions), default=0
        )
        + 1,
        baseVersionId=payload.baseVersionId,
        source="agent",
        content=content,
        contentHash=content_sha256(content),
        sourceTaskId=task.id,
        sourceJobId=command.id,
        sourceOutlineVersionId=payload.sourceOutlineVersionId,
        userInstruction=payload.userInstruction,
        sourceKind=payload.sourceKind,
        sourceText=payload.sourceText,
        createdFromSelection=payload.operation == "replace_selection",
        selectionStart=payload.selectionStart,
        selectionEnd=payload.selectionEnd,
        selectedTextHash=payload.selectedTextHash,
    )
    before = current.content if current is not None else ""
    diff = build_document_diff(
        before,
        content,
        from_version_id=current.id if current is not None else None,
        to_version_id=None,
    )
    agent_name = {
        "generate_outline": "剧情",
        "generate_manuscript": "写作",
        "replace_selection": "编辑",
    }[payload.operation]
    artifact = ReviewArtifact(
        novelId=task.novelId,
        chapterId=task.chapterId if payload.documentType == "manuscript" else None,
        taskId=task.id,
        artifactKey=artifact_key,
        kind=version_payload.kind,
        status="awaiting_user",
        title=(
            "中短篇大纲候选版本"
            if payload.documentType == "outline"
            else "中短篇正文候选版本"
        ),
        summary=payload.userInstruction,
        payloadJson=version_payload.model_dump_json(),
        diffJson=diff.model_dump_json(),
        createdByAgent=agent_name,
        updatedByAgent=agent_name,
        revision=1,
    )
    session.add(artifact)
    await session.flush()
    bound_diff = bind_confirmation_hash(
        diff.model_copy(update={"toVersionId": artifact.id}),
        document_type=payload.documentType,
        chapter_id=artifact.chapterId,
        base_version_id=payload.baseVersionId,
        current_draft_hash=payload.baseContentHash or content_sha256(""),
        target_version_id=artifact.id,
    )
    artifact.diffJson = bound_diff.model_dump_json()
    session.add(
        ReviewArtifactRevision(
            artifactId=artifact.id,
            revision=1,
            summary=payload.userInstruction,
            payloadJson=version_payload.model_dump_json(),
            diffJson=bound_diff.model_dump_json(),
            createdByAgent=agent_name,
        )
    )
    command.artifactId = artifact.id
    await session.flush()
    return {**result, "candidateVersionId": artifact.id}


async def load_short_medium_run_source(
    session: AsyncSession,
    user_id: str,
    request: ShortMediumStartWritingRunRequest,
) -> ShortMediumRunSource:
    row = (
        await session.execute(
            select(Novel, WritingBible)
            .join(WritingBible, WritingBible.novelId == Novel.id)
            .where(
                Novel.id == request.novelId,
                Novel.userId == user_id,
                WritingBible.storyLengthProfile == "short_medium",
            )
            .with_for_update(of=Novel)
        )
    ).one_or_none()
    if row is None:
        raise ApiError(
            status_code=404,
            code="SHORT_MEDIUM_NOVEL_NOT_FOUND",
            message="中短篇作品不存在",
        )
    _novel, bible = row
    target = bible.targetTotalWordCount
    if target is None or not 6_000 <= target <= 80_000:
        raise ApiError(
            status_code=409,
            code="SHORT_MEDIUM_TARGET_INVALID",
            message="中短篇目标字数无效",
        )
    chapters = list(
        (
            await session.scalars(
                select(Chapter)
                .where(Chapter.novelId == request.novelId)
                .order_by(Chapter.order, Chapter.id)
                .with_for_update()
            )
        ).all()
    )
    if len(chapters) != 1 or (
        request.chapterId is not None and request.chapterId != chapters[0].id
    ):
        raise ApiError(
            status_code=409,
            code="SHORT_MEDIUM_CHAPTER_INVALID",
            message="中短篇必须且只能绑定唯一全文章节",
        )
    chapter = chapters[0]
    outline = await session.scalar(
        select(Outline)
        .where(Outline.novelId == request.novelId)
        .with_for_update()
    )
    if outline is None:
        raise ApiError(
            status_code=404,
            code="SHORT_MEDIUM_OUTLINE_NOT_FOUND",
            message="中短篇大纲工作稿不存在",
        )
    source_artifact = await session.scalar(
        select(ReviewArtifact).where(
            ReviewArtifact.novelId == request.novelId,
            ReviewArtifact.artifactKey == f"short-medium:source:{request.novelId}",
            ReviewArtifact.status == "applied",
        )
    )
    if source_artifact is None:
        raise ApiError(
            status_code=409,
            code="SHORT_MEDIUM_SOURCE_MISSING",
            message="中短篇起始素材不存在",
        )
    source_payload = _json_object(source_artifact.payloadJson)
    source_kind = source_payload.get("sourceKind")
    source_text = source_payload.get("sourceText")
    if not isinstance(source_kind, str) or not isinstance(source_text, str):
        raise ApiError(
            status_code=409,
            code="SHORT_MEDIUM_SOURCE_INVALID",
            message="中短篇起始素材格式无效",
        )
    outline_versions = await _load_versions(
        session, f"{SHORT_MEDIUM_OUTLINE_PREFIX}{request.novelId}"
    )
    manuscript_versions = await _load_versions(
        session, f"{SHORT_MEDIUM_MANUSCRIPT_PREFIX}{chapter.id}"
    )
    current_outline = _current(outline_versions)
    current_document = (
        current_outline
        if request.documentType == "outline"
        else _current(manuscript_versions)
    )
    bound_outline: VersionRecord | None = None
    if (
        current_document is not None
        and current_document.payload.documentType == "manuscript"
        and current_document.payload.sourceOutlineVersionId is not None
    ):
        bound_outline = next(
            (
                version
                for version in outline_versions
                if version.id == current_document.payload.sourceOutlineVersionId
            ),
            None,
        )
    return ShortMediumRunSource(
        chapter_id=chapter.id,
        target_total_word_count=target,
        source_kind=source_kind,
        source_text=source_text,
        document_content=(
            outline.content if request.documentType == "outline" else chapter.content
        ),
        current_document_version=current_document,
        outline_content=outline.content,
        current_outline_version=current_outline,
        bound_outline_version=bound_outline,
    )


async def _load_versions(
    session: AsyncSession,
    artifact_key: str,
) -> list[VersionRecord]:
    artifacts = list(
        (
            await session.scalars(
                select(ReviewArtifact)
                .where(ReviewArtifact.artifactKey == artifact_key)
                .order_by(ReviewArtifact.createdAt, ReviewArtifact.id)
                .with_for_update()
            )
        ).all()
    )
    return [
        version_record_from_values(
            id=artifact.id,
            novel_id=artifact.novelId,
            chapter_id=artifact.chapterId,
            artifact_key=artifact_key,
            status=artifact.status,
            summary=artifact.summary,
            payload_json=artifact.payloadJson,
            diff_json=artifact.diffJson,
            created_by_agent=artifact.createdByAgent,
            task_id=artifact.taskId,
            created_at=artifact.createdAt,
            updated_at=artifact.updatedAt,
            applied_at=artifact.appliedAt,
        )
        for artifact in artifacts
    ]


def _current(versions: list[VersionRecord]) -> VersionRecord | None:
    return max(
        (item for item in versions if item.status == "applied"),
        key=lambda item: item.version_number,
        default=None,
    )


def _json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ApiError(
            status_code=409,
            code="SHORT_MEDIUM_PERSISTED_JSON_INVALID",
            message="中短篇持久数据格式无效",
        ) from exc
    if not isinstance(parsed, dict):
        raise ApiError(
            status_code=409,
            code="SHORT_MEDIUM_PERSISTED_JSON_INVALID",
            message="中短篇持久数据格式无效",
        )
    return parsed
