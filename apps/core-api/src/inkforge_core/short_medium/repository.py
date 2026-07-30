from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..chapters.content_state import (
    lock_consistency_check,
    replace_chapter_content,
)
from ..db.base import utc_now
from ..db.models import (
    Chapter,
    Novel,
    Outline,
    ReviewArtifact,
    ReviewArtifactRevision,
    WritingBible,
    WritingRunCommand,
)
from ..errors import ApiError
from .schemas import DocumentVersionPayload, VersionDiffResponse

SHORT_MEDIUM_OUTLINE_PREFIX = "short-medium:outline:"
SHORT_MEDIUM_MANUSCRIPT_PREFIX = "short-medium:manuscript:"
SHORT_MEDIUM_VERSION_PREFIXES = (
    SHORT_MEDIUM_OUTLINE_PREFIX,
    SHORT_MEDIUM_MANUSCRIPT_PREFIX,
)


def is_short_medium_artifact_key(value: str | None) -> bool:
    return value is not None and value.startswith("short-medium:")


@dataclass(slots=True)
class WorkDocument:
    novel_id: str
    chapter_id: str | None
    document_type: str
    artifact_key: str
    content: str
    updated_at: datetime


@dataclass(slots=True)
class VersionRecord:
    id: str
    novel_id: str
    chapter_id: str | None
    artifact_key: str
    status: str
    summary: str | None
    payload: DocumentVersionPayload
    diff: VersionDiffResponse | None
    created_by_agent: str | None
    task_id: str | None
    created_at: datetime
    updated_at: datetime
    applied_at: datetime | None

    @property
    def content(self) -> str:
        return self.payload.content

    @property
    def version_number(self) -> int:
        return self.payload.versionNumber


class DocumentTransaction(Protocol):
    document: WorkDocument
    versions: list[VersionRecord]

    async def create_version(
        self,
        payload_json: str,
        diff_json: str,
        *,
        status: str,
        summary: str | None,
        created_by_agent: str | None,
        task_id: str | None,
        job_id: str | None,
    ) -> VersionRecord: ...

    async def save_initial_diff(
        self, record: VersionRecord, diff: VersionDiffResponse
    ) -> None: ...

    async def replace_work_content(self, content: str) -> datetime: ...

    async def mark_candidate_applied(self, record: VersionRecord) -> VersionRecord: ...

    async def find_adoption_replay(self, key: str) -> str | None: ...

    async def save_adoption_replay(
        self, key: str, candidate: VersionRecord, response_json: str
    ) -> None: ...

    async def current_outline_version(self) -> VersionRecord | None: ...


class VersionRepositoryPort(Protocol):
    def document_transaction(
        self,
        user_id: str,
        novel_id: str,
        document_type: str,
        chapter_id: str | None,
    ) -> AbstractAsyncContextManager[DocumentTransaction]: ...

    async def list_versions(
        self,
        user_id: str,
        novel_id: str,
        document_type: str,
        chapter_id: str | None,
    ) -> list[VersionRecord]: ...

    async def require_version(
        self, user_id: str, novel_id: str, version_id: str
    ) -> VersionRecord: ...


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _database_time(value: datetime) -> datetime:
    return _utc(value).replace(tzinfo=None)


def _next_updated_at(current: datetime) -> datetime:
    return max(utc_now(), _database_time(current) + timedelta(milliseconds=1))


def version_record_from_values(
    *,
    id: str,
    novel_id: str,
    chapter_id: str | None,
    artifact_key: str,
    status: str,
    summary: str | None,
    payload_json: str,
    diff_json: str | None,
    created_by_agent: str | None,
    task_id: str | None,
    created_at: datetime,
    updated_at: datetime,
    applied_at: datetime | None,
) -> VersionRecord:
    payload = DocumentVersionPayload.model_validate_json(payload_json)
    diff = (
        VersionDiffResponse.model_validate_json(diff_json)
        if diff_json is not None
        else None
    )
    if status not in {"awaiting_user", "applied"}:
        raise ApiError(
            status_code=409,
            code="SHORT_MEDIUM_VERSION_STATUS_INVALID",
            message="中短篇版本状态无效",
        )
    return VersionRecord(
        id=id,
        novel_id=novel_id,
        chapter_id=chapter_id,
        artifact_key=artifact_key,
        status=status,
        summary=summary,
        payload=payload,
        diff=diff,
        created_by_agent=created_by_agent,
        task_id=task_id,
        created_at=_utc(created_at),
        updated_at=_utc(updated_at),
        applied_at=_utc(applied_at) if applied_at is not None else None,
    )


def _record(artifact: ReviewArtifact) -> VersionRecord:
    if artifact.artifactKey is None:
        raise RuntimeError("中短篇版本缺少 artifactKey")
    return version_record_from_values(
        id=artifact.id,
        novel_id=artifact.novelId,
        chapter_id=artifact.chapterId,
        artifact_key=artifact.artifactKey,
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


class _SqlDocumentTransaction:
    def __init__(
        self,
        session: AsyncSession,
        document: WorkDocument,
        document_model: Outline | Chapter,
        artifacts: list[ReviewArtifact],
    ) -> None:
        self._session = session
        self._document_model = document_model
        self._artifacts = {artifact.id: artifact for artifact in artifacts}
        self._initial_revisions: dict[str, ReviewArtifactRevision] = {}
        self.document = document
        self.versions = [_record(artifact) for artifact in artifacts]

    async def create_version(
        self,
        payload_json: str,
        diff_json: str,
        *,
        status: str,
        summary: str | None,
        created_by_agent: str | None,
        task_id: str | None,
        job_id: str | None,
    ) -> VersionRecord:
        del job_id
        now = utc_now()
        artifact = ReviewArtifact(
            novelId=self.document.novel_id,
            chapterId=self.document.chapter_id,
            taskId=task_id,
            artifactKey=self.document.artifact_key,
            kind=(
                "outline_draft"
                if self.document.document_type == "outline"
                else "chapter_draft"
            ),
            status=status,
            title=(
                "中短篇大纲版本"
                if self.document.document_type == "outline"
                else "中短篇正文版本"
            ),
            summary=summary,
            payloadJson=payload_json,
            diffJson=diff_json,
            createdByAgent=created_by_agent,
            updatedByAgent=created_by_agent,
            revision=1,
            appliedAt=now if status == "applied" else None,
        )
        self._session.add(artifact)
        await self._session.flush()
        diff_payload = json.loads(diff_json)
        diff_payload["toVersionId"] = artifact.id
        diff_json = json.dumps(diff_payload, ensure_ascii=False)
        artifact.diffJson = diff_json
        revision = ReviewArtifactRevision(
            artifactId=artifact.id,
            revision=1,
            summary=summary,
            payloadJson=payload_json,
            diffJson=diff_json,
            createdByAgent=created_by_agent,
        )
        self._session.add(revision)
        await self._session.flush()
        record = _record(artifact)
        self._artifacts[artifact.id] = artifact
        self._initial_revisions[artifact.id] = revision
        self.versions.append(record)
        return record

    async def save_initial_diff(
        self, record: VersionRecord, diff: VersionDiffResponse
    ) -> None:
        artifact = self._artifacts.get(record.id)
        revision = self._initial_revisions.get(record.id)
        if artifact is None or revision is None:
            raise RuntimeError("版本初始差异模型未加载")
        diff_json = diff.model_dump_json()
        artifact.diffJson = diff_json
        revision.diffJson = diff_json
        record.diff = diff
        await self._session.flush()

    async def replace_work_content(self, content: str) -> datetime:
        if isinstance(self._document_model, Chapter):
            check = await lock_consistency_check(
                self._session, self._document_model.id
            )
            await replace_chapter_content(
                self._session,
                self._document_model,
                check,
                content,
                reopen=True,
            )
        else:
            self._document_model.content = content
            self._document_model.updatedAt = _next_updated_at(
                self._document_model.updatedAt
            )
        await self._session.flush()
        updated_at = _utc(self._document_model.updatedAt)
        self.document.content = content
        self.document.updated_at = updated_at
        return updated_at

    async def mark_candidate_applied(self, record: VersionRecord) -> VersionRecord:
        artifact = self._artifacts.get(record.id)
        if artifact is None:
            raise RuntimeError("候选版本模型未加载")
        if artifact.status != "awaiting_user":
            raise ApiError(
                status_code=409,
                code="SHORT_MEDIUM_CANDIDATE_STATUS_INVALID",
                message="该版本不是可采用的候选版本",
            )
        now = utc_now()
        artifact.status = "applied"
        artifact.appliedAt = now
        artifact.updatedAt = now
        await self._session.flush()
        record.status = "applied"
        record.applied_at = _utc(now)
        record.updated_at = _utc(now)
        return record

    async def find_adoption_replay(self, key: str) -> str | None:
        return await self._session.scalar(
            select(WritingRunCommand.resultJson).where(
                WritingRunCommand.idempotencyKey == key,
                WritingRunCommand.status == "succeeded",
            )
        )

    async def save_adoption_replay(
        self, key: str, candidate: VersionRecord, response_json: str
    ) -> None:
        if candidate.task_id is None:
            raise ApiError(
                status_code=409,
                code="SHORT_MEDIUM_CANDIDATE_TASK_MISSING",
                message="候选版本缺少来源任务，不能记录采用幂等结果",
            )
        now = utc_now()
        self._session.add(
            WritingRunCommand(
                taskId=candidate.task_id,
                artifactId=candidate.id,
                idempotencyKey=key,
                kind="short_medium_adopt",
                decision="adopt",
                payloadJson=json.dumps(
                    {"artifactId": candidate.id}, ensure_ascii=False
                ),
                resultJson=response_json,
                status="succeeded",
                submittedAt=now,
                completedAt=now,
                nextAttemptAt=now,
            )
        )
        await self._session.flush()

    async def current_outline_version(self) -> VersionRecord | None:
        artifacts = list(
            (
                await self._session.scalars(
                    select(ReviewArtifact).where(
                        ReviewArtifact.novelId == self.document.novel_id,
                        ReviewArtifact.artifactKey
                        == f"{SHORT_MEDIUM_OUTLINE_PREFIX}{self.document.novel_id}",
                        ReviewArtifact.status == "applied",
                    )
                )
            ).all()
        )
        records = [_record(artifact) for artifact in artifacts]
        return max(records, key=lambda value: value.version_number, default=None)


class ShortMediumVersionRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    @asynccontextmanager
    async def document_transaction(
        self,
        user_id: str,
        novel_id: str,
        document_type: str,
        chapter_id: str | None,
    ) -> AsyncIterator[DocumentTransaction]:
        async with self._session_factory() as session:
            async with session.begin():
                await self._require_short_medium_novel(
                    session, user_id, novel_id, lock=True
                )
                document, model = await self._load_document(
                    session,
                    novel_id,
                    document_type,
                    chapter_id,
                    lock=True,
                )
                artifacts = list(
                    (
                        await session.scalars(
                            select(ReviewArtifact)
                            .where(
                                ReviewArtifact.novelId == novel_id,
                                ReviewArtifact.artifactKey == document.artifact_key,
                            )
                            .order_by(
                                ReviewArtifact.createdAt.asc(),
                                ReviewArtifact.id.asc(),
                            )
                            .with_for_update()
                        )
                    ).all()
                )
                yield _SqlDocumentTransaction(session, document, model, artifacts)

    async def list_versions(
        self,
        user_id: str,
        novel_id: str,
        document_type: str,
        chapter_id: str | None,
    ) -> list[VersionRecord]:
        async with self._session_factory() as session:
            await self._require_short_medium_novel(
                session, user_id, novel_id, lock=False
            )
            document, _ = await self._load_document(
                session,
                novel_id,
                document_type,
                chapter_id,
                lock=False,
            )
            artifacts = list(
                (
                    await session.scalars(
                        select(ReviewArtifact)
                        .where(
                            ReviewArtifact.novelId == novel_id,
                            ReviewArtifact.artifactKey == document.artifact_key,
                        )
                        .order_by(
                            ReviewArtifact.createdAt.asc(),
                            ReviewArtifact.id.asc(),
                        )
                    )
                ).all()
            )
        return [_record(artifact) for artifact in artifacts]

    async def require_version(
        self, user_id: str, novel_id: str, version_id: str
    ) -> VersionRecord:
        async with self._session_factory() as session:
            artifact = await session.scalar(
                select(ReviewArtifact)
                .join(Novel, Novel.id == ReviewArtifact.novelId)
                .join(WritingBible, WritingBible.novelId == Novel.id)
                .where(
                    ReviewArtifact.id == version_id,
                    ReviewArtifact.novelId == novel_id,
                    Novel.userId == user_id,
                    WritingBible.storyLengthProfile == "short_medium",
                )
            )
        if artifact is None or artifact.artifactKey is None or not artifact.artifactKey.startswith(
            SHORT_MEDIUM_VERSION_PREFIXES
        ):
            raise ApiError(
                status_code=404,
                code="SHORT_MEDIUM_VERSION_NOT_FOUND",
                message="中短篇版本不存在",
            )
        return _record(artifact)

    @staticmethod
    async def _require_short_medium_novel(
        session: AsyncSession,
        user_id: str,
        novel_id: str,
        *,
        lock: bool,
    ) -> Novel:
        statement = (
            select(Novel)
            .join(WritingBible, WritingBible.novelId == Novel.id)
            .where(
                Novel.id == novel_id,
                Novel.userId == user_id,
                WritingBible.storyLengthProfile == "short_medium",
            )
        )
        if lock:
            statement = statement.with_for_update(of=Novel)
        novel = await session.scalar(statement)
        if novel is None:
            raise ApiError(
                status_code=404,
                code="SHORT_MEDIUM_NOVEL_NOT_FOUND",
                message="中短篇作品不存在",
            )
        return novel

    @staticmethod
    async def _load_document(
        session: AsyncSession,
        novel_id: str,
        document_type: str,
        chapter_id: str | None,
        *,
        lock: bool,
    ) -> tuple[WorkDocument, Outline | Chapter]:
        if document_type == "outline":
            if chapter_id is not None:
                raise ApiError(
                    status_code=422,
                    code="SHORT_MEDIUM_DOCUMENT_BINDING_INVALID",
                    message="大纲版本不能绑定章节",
                )
            outline_statement = select(Outline).where(Outline.novelId == novel_id)
            if lock:
                outline_statement = outline_statement.with_for_update()
            model = await session.scalar(outline_statement)
            if model is None:
                raise ApiError(
                    status_code=404,
                    code="SHORT_MEDIUM_OUTLINE_NOT_FOUND",
                    message="中短篇大纲工作稿不存在",
                )
            outline = model
            return (
                WorkDocument(
                    novel_id=novel_id,
                    chapter_id=None,
                    document_type="outline",
                    artifact_key=f"{SHORT_MEDIUM_OUTLINE_PREFIX}{novel_id}",
                    content=outline.content,
                    updated_at=_utc(outline.updatedAt),
                ),
                outline,
            )
        if document_type != "manuscript" or chapter_id is None:
            raise ApiError(
                status_code=422,
                code="SHORT_MEDIUM_DOCUMENT_BINDING_INVALID",
                message="正文版本必须绑定全文章节",
            )
        chapter_statement = select(Chapter).where(
            Chapter.id == chapter_id,
            Chapter.novelId == novel_id,
        )
        if lock:
            chapter_statement = chapter_statement.with_for_update()
        model = await session.scalar(chapter_statement)
        if model is None:
            raise ApiError(
                status_code=404,
                code="SHORT_MEDIUM_MANUSCRIPT_NOT_FOUND",
                message="中短篇全文工作稿不存在",
            )
        chapter = model
        return (
            WorkDocument(
                novel_id=novel_id,
                chapter_id=chapter_id,
                document_type="manuscript",
                artifact_key=f"{SHORT_MEDIUM_MANUSCRIPT_PREFIX}{chapter_id}",
                content=chapter.content,
                updated_at=_utc(chapter.updatedAt),
            ),
            chapter,
        )
