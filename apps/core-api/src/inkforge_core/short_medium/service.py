from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import cast

from ..errors import ApiError
from .repository import (
    DocumentTransaction,
    VersionRecord,
    VersionRepositoryPort,
)
from .schemas import (
    AgentCandidateCreate,
    DocumentType,
    DocumentVersionPayload,
    ManualVersionRequest,
    VersionActionRequest,
    VersionDetailResponse,
    VersionDiffResponse,
    VersionListItem,
    VersionPreviewRequest,
    VersionPreviewResponse,
    VersionStatus,
    bind_confirmation_hash,
    build_document_diff,
    content_sha256,
    count_text_length,
)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _current_version(versions: list[VersionRecord]) -> VersionRecord | None:
    return max(
        (version for version in versions if version.status == "applied"),
        key=lambda version: version.version_number,
        default=None,
    )


def _find_version(
    versions: list[VersionRecord], version_id: str
) -> VersionRecord:
    for version in versions:
        if version.id == version_id:
            return version
    raise ApiError(
        status_code=404,
        code="SHORT_MEDIUM_VERSION_NOT_FOUND",
        message="中短篇版本不存在",
    )


def _require_current_base(
    current: VersionRecord | None,
    requested_base_version_id: str | None,
) -> None:
    current_id = current.id if current is not None else None
    if requested_base_version_id != current_id:
        raise ApiError(
            status_code=409,
            code="SHORT_MEDIUM_BASE_VERSION_CONFLICT",
            message="当前版本已经变化，请重新预览后再操作",
            details={"currentVersionId": current_id},
        )


def _require_clean_work_draft(
    transaction: DocumentTransaction,
    current: VersionRecord | None,
) -> None:
    expected_hash = current.payload.contentHash if current is not None else content_sha256("")
    if content_sha256(transaction.document.content) != expected_hash:
        raise ApiError(
            status_code=409,
            code="SHORT_MEDIUM_WORK_DRAFT_DIRTY",
            message="工作稿存在未提交修改，请先提交或放弃修改",
        )


def _next_version_number(versions: list[VersionRecord]) -> int:
    return max((version.version_number for version in versions), default=0) + 1


def _detail(record: VersionRecord) -> VersionDetailResponse:
    return VersionDetailResponse(
        id=record.id,
        novelId=record.novel_id,
        chapterId=record.chapter_id,
        artifactKey=record.artifact_key,
        status=cast(VersionStatus, record.status),
        summary=record.summary,
        payload=record.payload,
        documentType=record.payload.documentType,
        versionNumber=record.payload.versionNumber,
        source=record.payload.source,
        content=record.payload.content,
        contentHash=record.payload.contentHash,
        baseVersionId=record.payload.baseVersionId,
        sourceOutlineVersionId=record.payload.sourceOutlineVersionId,
        restoredFromVersionId=record.payload.restoredFromVersionId,
        diff=record.diff,
        createdByAgent=record.created_by_agent,
        taskId=record.task_id,
        createdAt=record.created_at,
        updatedAt=record.updated_at,
        appliedAt=record.applied_at,
    )


def _list_item(record: VersionRecord) -> VersionListItem:
    return VersionListItem(
        id=record.id,
        documentType=record.payload.documentType,
        versionNumber=record.version_number,
        status=cast(VersionStatus, record.status),
        source=record.payload.source,
        wordCount=count_text_length(record.content),
        baseVersionId=record.payload.baseVersionId,
        sourceOutlineVersionId=record.payload.sourceOutlineVersionId,
        restoredFromVersionId=record.payload.restoredFromVersionId,
        summary=record.summary,
        createdByAgent=record.created_by_agent,
        createdAt=record.created_at,
        updatedAt=record.updated_at,
        appliedAt=record.applied_at,
    )


def _serialized_diff(
    before: str,
    after: str,
    *,
    from_version_id: str | None,
) -> tuple[VersionDiffResponse, str]:
    diff = build_document_diff(
        before,
        after,
        from_version_id=from_version_id,
        to_version_id=None,
    )
    return diff, diff.model_dump_json()


def _require_confirmation(actual: str, expected: str) -> None:
    if actual != expected:
        raise ApiError(
            status_code=409,
            code="SHORT_MEDIUM_CONFIRMATION_CONFLICT",
            message="版本或工作稿已变化，请重新查看差异后再确认",
        )


class ShortMediumVersionService:
    def __init__(self, repository: VersionRepositoryPort) -> None:
        self._repository = repository

    async def preview(
        self,
        user_id: str,
        novel_id: str,
        request: VersionPreviewRequest,
    ) -> VersionPreviewResponse:
        async with self._repository.document_transaction(
            user_id,
            novel_id,
            request.documentType,
            request.chapterId,
        ) as transaction:
            current = _current_version(transaction.versions)
            _require_current_base(current, request.baseVersionId)
            base_content = current.content if current is not None else ""
            work_content = transaction.document.content
            diff = build_document_diff(
                base_content,
                work_content,
                from_version_id=current.id if current is not None else None,
                to_version_id=None,
            )
            diff = bind_confirmation_hash(
                diff,
                document_type=request.documentType,
                chapter_id=request.chapterId,
                base_version_id=current.id if current is not None else None,
                current_draft_hash=content_sha256(work_content),
                target_version_id=None,
            )
            dirty = content_sha256(work_content) != content_sha256(base_content)
            return VersionPreviewResponse(
                documentType=cast(DocumentType, transaction.document.document_type),
                chapterId=transaction.document.chapter_id,
                baseVersionId=current.id if current is not None else None,
                expectedUpdatedAt=transaction.document.updated_at,
                contentHash=content_sha256(work_content),
                dirty=dirty,
                confirmationSummary=(
                    f"将提交{diff.toWordCount}字，字数变化{diff.wordCountDelta:+d}"
                    if dirty
                    else "工作稿与当前版本一致，没有可提交的变化"
                ),
                confirmationHash=diff.confirmationHash,
                diff=diff,
            )

    async def submit_manual(
        self,
        user_id: str,
        novel_id: str,
        request: ManualVersionRequest,
    ) -> VersionDetailResponse:
        async with self._repository.document_transaction(
            user_id,
            novel_id,
            request.documentType,
            request.chapterId,
        ) as transaction:
            replay = next(
                (
                    version
                    for version in transaction.versions
                    if version.payload.clientRequestId == request.clientRequestId
                ),
                None,
            )
            if replay is not None:
                return _detail(replay)
            current = _current_version(transaction.versions)
            _require_current_base(current, request.baseVersionId)
            if _utc(request.expectedUpdatedAt) != _utc(
                transaction.document.updated_at
            ):
                raise ApiError(
                    status_code=409,
                    code="SHORT_MEDIUM_WORK_DRAFT_CONFLICT",
                    message="工作稿已在其他位置更新，请重新预览",
                    details={
                        "currentUpdatedAt": transaction.document.updated_at.isoformat()
                    },
                )
            work_content = transaction.document.content
            work_hash = content_sha256(work_content)
            if request.contentHash != work_hash:
                raise ApiError(
                    status_code=409,
                    code="SHORT_MEDIUM_WORK_DRAFT_HASH_CONFLICT",
                    message="工作稿内容已经变化，请重新预览",
                    details={"currentContentHash": work_hash},
                )
            confirmation_diff = bind_confirmation_hash(
                build_document_diff(
                    current.content if current is not None else "",
                    work_content,
                    from_version_id=current.id if current is not None else None,
                    to_version_id=None,
                ),
                document_type=request.documentType,
                chapter_id=request.chapterId,
                base_version_id=current.id if current is not None else None,
                current_draft_hash=work_hash,
                target_version_id=None,
            )
            _require_confirmation(
                request.confirmationHash, confirmation_diff.confirmationHash
            )
            if current is not None and current.payload.contentHash == work_hash:
                return _detail(current)
            source_outline_version_id: str | None = None
            if request.documentType == "manuscript":
                if current is not None:
                    source_outline_version_id = (
                        current.payload.sourceOutlineVersionId
                    )
                else:
                    outline = await transaction.current_outline_version()
                    if outline is None:
                        raise ApiError(
                            status_code=409,
                            code="SHORT_MEDIUM_OUTLINE_VERSION_REQUIRED",
                            message="提交首个正文版本前必须先确认一份大纲版本",
                        )
                    source_outline_version_id = outline.id
            payload = DocumentVersionPayload(
                kind=(
                    "outline_draft"
                    if request.documentType == "outline"
                    else "chapter_draft"
                ),
                documentType=request.documentType,
                versionNumber=_next_version_number(transaction.versions),
                baseVersionId=current.id if current is not None else None,
                clientRequestId=request.clientRequestId,
                source="manual",
                content=work_content,
                contentHash=work_hash,
                sourceOutlineVersionId=source_outline_version_id,
            )
            _, diff_json = _serialized_diff(
                current.content if current is not None else "",
                work_content,
                from_version_id=current.id if current is not None else None,
            )
            created = await transaction.create_version(
                payload.model_dump_json(),
                diff_json,
                status="applied",
                summary=request.summary,
                created_by_agent=None,
                task_id=None,
                job_id=None,
            )
            return _detail(created)

    async def create_agent_candidate(
        self,
        user_id: str,
        novel_id: str,
        request: AgentCandidateCreate,
    ) -> VersionDetailResponse:
        async with self._repository.document_transaction(
            user_id,
            novel_id,
            request.documentType,
            request.chapterId,
        ) as transaction:
            replay = next(
                (
                    version
                    for version in transaction.versions
                    if version.payload.sourceTaskId == request.sourceTaskId
                    and version.payload.sourceJobId == request.sourceJobId
                ),
                None,
            )
            if replay is not None:
                return _detail(replay)
            current = _current_version(transaction.versions)
            _require_current_base(current, request.baseVersionId)
            expected_base_hash = (
                current.payload.contentHash
                if current is not None
                else content_sha256("")
            )
            if request.baseContentHash != expected_base_hash:
                raise ApiError(
                    status_code=409,
                    code="SHORT_MEDIUM_AGENT_BASE_HASH_CONFLICT",
                    message="Agent 任务基础内容已经变化",
                )
            _require_clean_work_draft(transaction, current)
            payload = DocumentVersionPayload(
                kind=(
                    "outline_draft"
                    if request.documentType == "outline"
                    else "chapter_draft"
                ),
                documentType=request.documentType,
                versionNumber=_next_version_number(transaction.versions),
                baseVersionId=current.id if current is not None else None,
                source="agent",
                content=request.content,
                contentHash=content_sha256(request.content),
                sourceTaskId=request.sourceTaskId,
                sourceJobId=request.sourceJobId,
                sourceOutlineVersionId=request.sourceOutlineVersionId,
                userInstruction=request.userInstruction,
                createdFromSelection=request.createdFromSelection,
                selectionStart=request.selectionStart,
                selectionEnd=request.selectionEnd,
                selectedTextHash=request.selectedTextHash,
            )
            _, diff_json = _serialized_diff(
                current.content if current is not None else "",
                request.content,
                from_version_id=current.id if current is not None else None,
            )
            created = await transaction.create_version(
                payload.model_dump_json(),
                diff_json,
                status="awaiting_user",
                summary=request.userInstruction,
                created_by_agent=request.createdByAgent,
                task_id=request.sourceTaskId,
                job_id=request.sourceJobId,
            )
            if created.diff is not None:
                created.diff = created.diff.model_copy(
                    update={"toVersionId": created.id}
                )
                created.diff = bind_confirmation_hash(
                    created.diff,
                    document_type=request.documentType,
                    chapter_id=request.chapterId,
                    base_version_id=current.id if current is not None else None,
                    current_draft_hash=request.baseContentHash,
                    target_version_id=created.id,
                )
                await transaction.save_initial_diff(created, created.diff)
            return _detail(created)

    async def adopt(
        self,
        user_id: str,
        novel_id: str,
        version_id: str,
        request: VersionActionRequest,
    ) -> VersionDetailResponse:
        async with self._repository.document_transaction(
            user_id,
            novel_id,
            request.documentType,
            request.chapterId,
        ) as transaction:
            candidate = _find_version(transaction.versions, version_id)
            idempotency_key = (
                f"short-medium:adopt:{candidate.id}:{request.clientRequestId}"
            )
            replay = await transaction.find_adoption_replay(idempotency_key)
            if replay is not None:
                replay_id = json.loads(replay).get("versionId")
                if replay_id != candidate.id:
                    raise RuntimeError("采用幂等结果与候选版本不一致")
                return _detail(candidate)
            if candidate.status != "awaiting_user":
                raise ApiError(
                    status_code=409,
                    code="SHORT_MEDIUM_CANDIDATE_STATUS_INVALID",
                    message="该版本不是可采用的候选版本",
                )
            current = _current_version(transaction.versions)
            _require_current_base(current, request.baseVersionId)
            if candidate.payload.baseVersionId != (
                current.id if current is not None else None
            ):
                raise ApiError(
                    status_code=409,
                    code="SHORT_MEDIUM_CANDIDATE_STALE",
                    message="候选版本的基础版本已经过期，请改用恢复操作",
                )
            _require_clean_work_draft(transaction, current)
            confirmation_diff = bind_confirmation_hash(
                build_document_diff(
                    current.content if current is not None else "",
                    candidate.content,
                    from_version_id=current.id if current is not None else None,
                    to_version_id=candidate.id,
                ),
                document_type=request.documentType,
                chapter_id=request.chapterId,
                base_version_id=current.id if current is not None else None,
                current_draft_hash=content_sha256(transaction.document.content),
                target_version_id=candidate.id,
            )
            _require_confirmation(
                request.confirmationHash, confirmation_diff.confirmationHash
            )
            await transaction.replace_work_content(candidate.content)
            adopted = await transaction.mark_candidate_applied(candidate)
            await transaction.save_adoption_replay(
                idempotency_key,
                candidate,
                json.dumps({"versionId": candidate.id}, ensure_ascii=False),
            )
            return _detail(adopted)

    async def restore(
        self,
        user_id: str,
        novel_id: str,
        version_id: str,
        request: VersionActionRequest,
    ) -> VersionDetailResponse:
        async with self._repository.document_transaction(
            user_id,
            novel_id,
            request.documentType,
            request.chapterId,
        ) as transaction:
            replay = next(
                (
                    version
                    for version in transaction.versions
                    if version.payload.clientRequestId == request.clientRequestId
                    and version.payload.source == "restore"
                ),
                None,
            )
            if replay is not None:
                return _detail(replay)
            historical = _find_version(transaction.versions, version_id)
            current = _current_version(transaction.versions)
            _require_current_base(current, request.baseVersionId)
            _require_clean_work_draft(transaction, current)
            confirmation_diff = bind_confirmation_hash(
                build_document_diff(
                    current.content if current is not None else "",
                    historical.content,
                    from_version_id=current.id if current is not None else None,
                    to_version_id=historical.id,
                ),
                document_type=request.documentType,
                chapter_id=request.chapterId,
                base_version_id=current.id if current is not None else None,
                current_draft_hash=content_sha256(transaction.document.content),
                target_version_id=historical.id,
            )
            _require_confirmation(
                request.confirmationHash, confirmation_diff.confirmationHash
            )
            payload = DocumentVersionPayload(
                kind=historical.payload.kind,
                documentType=historical.payload.documentType,
                versionNumber=_next_version_number(transaction.versions),
                baseVersionId=current.id if current is not None else None,
                clientRequestId=request.clientRequestId,
                source="restore",
                content=historical.content,
                contentHash=historical.payload.contentHash,
                sourceOutlineVersionId=historical.payload.sourceOutlineVersionId,
                restoredFromVersionId=historical.id,
            )
            _, diff_json = _serialized_diff(
                current.content if current is not None else "",
                historical.content,
                from_version_id=current.id if current is not None else None,
            )
            await transaction.replace_work_content(historical.content)
            restored = await transaction.create_version(
                payload.model_dump_json(),
                diff_json,
                status="applied",
                summary=f"恢复自版本 v{historical.version_number}",
                created_by_agent=None,
                task_id=None,
                job_id=None,
            )
            return _detail(restored)

    async def list_versions(
        self,
        user_id: str,
        novel_id: str,
        document_type: DocumentType,
        chapter_id: str | None,
    ) -> list[VersionListItem]:
        versions = await self._repository.list_versions(
            user_id, novel_id, document_type, chapter_id
        )
        return [
            _list_item(version)
            for version in sorted(
                versions, key=lambda value: value.version_number, reverse=True
            )
        ]

    async def get_version(
        self, user_id: str, novel_id: str, version_id: str
    ) -> VersionDetailResponse:
        record = await self._repository.require_version(
            user_id, novel_id, version_id
        )
        if record.diff is not None:
            record.diff = record.diff.model_copy(update={"toVersionId": record.id})
            base_hash = content_sha256("")
            if record.payload.baseVersionId is not None:
                base = await self._repository.require_version(
                    user_id, novel_id, record.payload.baseVersionId
                )
                base_hash = base.payload.contentHash
            record.diff = bind_confirmation_hash(
                record.diff,
                document_type=record.payload.documentType,
                chapter_id=record.chapter_id,
                base_version_id=record.payload.baseVersionId,
                current_draft_hash=base_hash,
                target_version_id=record.id,
            )
        return _detail(record)

    async def diff_versions(
        self,
        user_id: str,
        novel_id: str,
        from_version_id: str,
        to_version_id: str,
    ) -> VersionDiffResponse:
        before = await self._repository.require_version(
            user_id, novel_id, from_version_id
        )
        after = await self._repository.require_version(
            user_id, novel_id, to_version_id
        )
        if (
            before.payload.documentType != after.payload.documentType
            or before.artifact_key != after.artifact_key
        ):
            raise ApiError(
                status_code=409,
                code="SHORT_MEDIUM_DIFF_TYPE_MISMATCH",
                message="只能比较同一文档的版本",
            )
        diff = build_document_diff(
            before.content,
            after.content,
            from_version_id=before.id,
            to_version_id=after.id,
        )
        return bind_confirmation_hash(
            diff,
            document_type=before.payload.documentType,
            chapter_id=before.chapter_id,
            base_version_id=before.id,
            current_draft_hash=before.payload.contentHash,
            target_version_id=after.id,
        )
