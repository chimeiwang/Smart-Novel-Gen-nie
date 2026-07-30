from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
from inkforge_core.errors import ApiError
from inkforge_core.short_medium.repository import (
    DocumentTransaction,
    VersionRecord,
    WorkDocument,
)
from inkforge_core.short_medium.schemas import (
    AgentCandidateCreate,
    ManualVersionRequest,
    VersionActionRequest,
    VersionPreviewRequest,
)
from inkforge_core.short_medium.service import ShortMediumVersionService

NOW = datetime(2026, 7, 30, tzinfo=UTC)


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass
class MemoryTransaction:
    document: WorkDocument
    versions: list[VersionRecord] = field(default_factory=list)
    adoption_replays: dict[str, str] = field(default_factory=dict)

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
        from inkforge_core.short_medium.repository import version_record_from_values

        record = version_record_from_values(
            id=f"version-{len(self.versions) + 1}",
            novel_id=self.document.novel_id,
            chapter_id=self.document.chapter_id,
            artifact_key=self.document.artifact_key,
            status=status,
            summary=summary,
            payload_json=payload_json,
            diff_json=diff_json,
            created_by_agent=created_by_agent,
            task_id=task_id,
            created_at=NOW + timedelta(seconds=len(self.versions)),
            updated_at=NOW + timedelta(seconds=len(self.versions)),
            applied_at=NOW if status == "applied" else None,
        )
        self.versions.append(record)
        return record

    async def replace_work_content(self, content: str) -> datetime:
        self.document.content = content
        self.document.updated_at += timedelta(milliseconds=1)
        return self.document.updated_at

    async def save_initial_diff(self, record: VersionRecord, diff: object) -> None:
        from inkforge_core.short_medium.schemas import VersionDiffResponse

        record.diff = VersionDiffResponse.model_validate(diff)

    async def mark_candidate_applied(self, record: VersionRecord) -> VersionRecord:
        record.status = "applied"
        record.applied_at = NOW
        return record

    async def find_adoption_replay(self, key: str) -> str | None:
        return self.adoption_replays.get(key)

    async def save_adoption_replay(
        self, key: str, candidate: VersionRecord, response_json: str
    ) -> None:
        del candidate
        self.adoption_replays[key] = response_json


class MemoryRepository:
    def __init__(self, transaction: MemoryTransaction) -> None:
        self.tx = transaction

    @asynccontextmanager
    async def document_transaction(
        self,
        user_id: str,
        novel_id: str,
        document_type: str,
        chapter_id: str | None,
    ) -> AsyncIterator[DocumentTransaction]:
        assert user_id == "user-1"
        assert novel_id == self.tx.document.novel_id
        assert document_type == self.tx.document.document_type
        assert chapter_id == self.tx.document.chapter_id
        yield self.tx  # type: ignore[misc]

    async def list_versions(
        self, user_id: str, novel_id: str, document_type: str, chapter_id: str | None
    ) -> list[VersionRecord]:
        del user_id, novel_id, document_type, chapter_id
        return list(self.tx.versions)

    async def require_version(
        self, user_id: str, novel_id: str, version_id: str
    ) -> VersionRecord:
        del user_id, novel_id
        for version in self.tx.versions:
            if version.id == version_id:
                return version
        raise ApiError(status_code=404, code="VERSION_NOT_FOUND", message="版本不存在")


def outline_service(content: str = "初稿") -> tuple[ShortMediumVersionService, MemoryTransaction]:
    tx = MemoryTransaction(
        WorkDocument(
            novel_id="novel-1",
            chapter_id=None,
            document_type="outline",
            artifact_key="short-medium:outline:novel-1",
            content=content,
            updated_at=NOW,
        )
    )
    return ShortMediumVersionService(MemoryRepository(tx)), tx


@pytest.mark.asyncio
async def test_manual_submit_is_idempotent_and_same_content_does_not_add_version() -> None:
    service, tx = outline_service()
    preview = await service.preview(
        "user-1",
        "novel-1",
        VersionPreviewRequest(documentType="outline", baseVersionId=None),
    )
    request = ManualVersionRequest(
        clientRequestId="request-12345678",
        documentType="outline",
        chapterId=None,
        baseVersionId=None,
        expectedUpdatedAt=NOW,
        contentHash=sha256("初稿"),
        confirmationHash=preview.confirmationHash,
        summary=None,
    )

    first = await service.submit_manual("user-1", "novel-1", request)
    replay = await service.submit_manual("user-1", "novel-1", request)

    assert first.id == replay.id
    assert first.versionNumber == 1
    assert len(tx.versions) == 1

    no_change_preview = await service.preview(
        "user-1",
        "novel-1",
        VersionPreviewRequest(documentType="outline", baseVersionId=first.id),
    )
    no_change = await service.submit_manual(
        "user-1",
        "novel-1",
        request.model_copy(
            update={
                "clientRequestId": "request-87654321",
                "baseVersionId": first.id,
                "confirmationHash": no_change_preview.confirmationHash,
            }
        ),
    )
    assert no_change.id == first.id
    assert len(tx.versions) == 1


@pytest.mark.asyncio
async def test_manual_submit_rejects_confirmation_hash_from_another_diff() -> None:
    service, _ = outline_service()
    preview = await service.preview(
        "user-1",
        "novel-1",
        VersionPreviewRequest(documentType="outline", baseVersionId=None),
    )

    with pytest.raises(ApiError) as error:
        await service.submit_manual(
            "user-1",
            "novel-1",
            ManualVersionRequest(
                clientRequestId="request-12345678",
                documentType="outline",
                baseVersionId=None,
                expectedUpdatedAt=NOW,
                contentHash=sha256("初稿"),
                confirmationHash=("0" * 64 if preview.confirmationHash != "0" * 64 else "1" * 64),
            ),
        )

    assert error.value.code == "SHORT_MEDIUM_CONFIRMATION_CONFLICT"


@pytest.mark.asyncio
async def test_candidate_does_not_change_work_draft_and_adopt_rejects_dirty_work() -> None:
    service, tx = outline_service()
    initial_preview = await service.preview(
        "user-1",
        "novel-1",
        VersionPreviewRequest(documentType="outline", baseVersionId=None),
    )
    base = await service.submit_manual(
        "user-1",
        "novel-1",
        ManualVersionRequest(
            clientRequestId="request-12345678",
            documentType="outline",
            baseVersionId=None,
            expectedUpdatedAt=NOW,
            contentHash=sha256("初稿"),
            confirmationHash=initial_preview.confirmationHash,
        ),
    )
    candidate = await service.create_agent_candidate(
        "user-1",
        "novel-1",
        AgentCandidateCreate(
            documentType="outline",
            baseVersionId=base.id,
            baseContentHash=sha256("初稿"),
            content="候选大纲",
            sourceTaskId="task-1",
            sourceJobId="job-1",
            createdByAgent="剧情",
        ),
    )

    assert candidate.status == "awaiting_user"
    assert tx.document.content == "初稿"

    tx.document.content = "未提交人工改动"
    with pytest.raises(ApiError) as error:
        await service.adopt(
            "user-1",
            "novel-1",
            candidate.id,
            VersionActionRequest(
                clientRequestId="request-adopt-123",
                documentType="outline",
                baseVersionId=base.id,
                confirmationHash="0" * 64,
            ),
        )
    assert error.value.code == "SHORT_MEDIUM_WORK_DRAFT_DIRTY"


@pytest.mark.asyncio
async def test_first_candidate_detail_diff_can_be_adopted_and_replayed() -> None:
    service, tx = outline_service()
    preview = await service.preview(
        "user-1",
        "novel-1",
        VersionPreviewRequest(documentType="outline", baseVersionId=None),
    )
    base = await service.submit_manual(
        "user-1",
        "novel-1",
        ManualVersionRequest(
            clientRequestId="request-base-1234",
            documentType="outline",
            baseVersionId=None,
            expectedUpdatedAt=NOW,
            contentHash=sha256("初稿"),
            confirmationHash=preview.confirmationHash,
        ),
    )
    request = AgentCandidateCreate(
        documentType="outline",
        baseVersionId=base.id,
        baseContentHash=sha256("初稿"),
        content="首个候选大纲",
        sourceTaskId="task-first",
        sourceJobId="job-first",
        createdByAgent="剧情",
    )

    first = await service.create_agent_candidate(
        "user-1", "novel-1", request
    )
    replay = await service.create_agent_candidate(
        "user-1", "novel-1", request
    )

    assert first.id == replay.id
    assert first.diff is not None
    assert tx.versions[-1].diff is not None
    assert tx.versions[-1].diff.confirmationHash == first.diff.confirmationHash
    adopted = await service.adopt(
        "user-1",
        "novel-1",
        first.id,
        VersionActionRequest(
            clientRequestId="request-adopt-first",
            documentType="outline",
            baseVersionId=base.id,
            confirmationHash=first.diff.confirmationHash,
        ),
    )

    assert adopted.id == first.id
    assert adopted.status == "applied"
    assert tx.document.content == "首个候选大纲"


@pytest.mark.asyncio
async def test_adopt_rejects_stale_candidate_and_restore_creates_monotonic_version() -> None:
    service, tx = outline_service()
    initial_preview = await service.preview(
        "user-1",
        "novel-1",
        VersionPreviewRequest(documentType="outline", baseVersionId=None),
    )
    first = await service.submit_manual(
        "user-1",
        "novel-1",
        ManualVersionRequest(
            clientRequestId="request-12345678",
            documentType="outline",
            baseVersionId=None,
            expectedUpdatedAt=NOW,
            contentHash=sha256("初稿"),
            confirmationHash=initial_preview.confirmationHash,
        ),
    )
    candidate = await service.create_agent_candidate(
        "user-1",
        "novel-1",
        AgentCandidateCreate(
            documentType="outline",
            baseVersionId=first.id,
            baseContentHash=sha256("初稿"),
            content="候选大纲",
            sourceTaskId="task-1",
            sourceJobId="job-1",
            createdByAgent="剧情",
        ),
    )
    tx.document.content = "人工第二版"
    tx.document.updated_at = NOW + timedelta(seconds=1)
    second_preview = await service.preview(
        "user-1",
        "novel-1",
        VersionPreviewRequest(documentType="outline", baseVersionId=first.id),
    )
    second = await service.submit_manual(
        "user-1",
        "novel-1",
        ManualVersionRequest(
            clientRequestId="request-87654321",
            documentType="outline",
            baseVersionId=first.id,
            expectedUpdatedAt=tx.document.updated_at,
            contentHash=sha256("人工第二版"),
            confirmationHash=second_preview.confirmationHash,
        ),
    )

    with pytest.raises(ApiError) as error:
        await service.adopt(
            "user-1",
            "novel-1",
            candidate.id,
            VersionActionRequest(
                clientRequestId="request-adopt-123",
                documentType="outline",
                baseVersionId=second.id,
                confirmationHash="0" * 64,
            ),
        )
    assert error.value.code == "SHORT_MEDIUM_CANDIDATE_STALE"

    restore_diff = await service.diff_versions(
        "user-1", "novel-1", second.id, first.id
    )
    restored = await service.restore(
        "user-1",
        "novel-1",
        first.id,
        VersionActionRequest(
            clientRequestId="request-restore-1",
            documentType="outline",
            baseVersionId=second.id,
            confirmationHash=restore_diff.confirmationHash,
        ),
    )
    assert restored.versionNumber == candidate.versionNumber + 2
    assert restored.restoredFromVersionId == first.id
    assert tx.document.content == first.content
    assert tx.versions[0].content == "初稿"


@pytest.mark.asyncio
async def test_manuscript_manual_version_inherits_outline_binding() -> None:
    tx = MemoryTransaction(
        WorkDocument(
            novel_id="novel-1",
            chapter_id="chapter-1",
            document_type="manuscript",
            artifact_key="short-medium:manuscript:chapter-1",
            content="",
            updated_at=NOW,
        )
    )
    repository = MemoryRepository(tx)
    service = ShortMediumVersionService(repository)
    first_payload = AgentCandidateCreate(
        documentType="manuscript",
        chapterId="chapter-1",
        baseVersionId=None,
        baseContentHash=sha256(""),
        content="第一稿",
        sourceTaskId="task-1",
        sourceJobId="job-1",
        sourceOutlineVersionId="outline-version-1",
        createdByAgent="写作",
    )
    first = await service.create_agent_candidate("user-1", "novel-1", first_payload)
    await service.adopt(
        "user-1",
        "novel-1",
        first.id,
        VersionActionRequest(
            clientRequestId="request-adopt-123",
            documentType="manuscript",
            chapterId="chapter-1",
            baseVersionId=None,
            confirmationHash=first.diff.confirmationHash,
        ),
    )
    tx.document.content = "第二稿"
    manuscript_preview = await service.preview(
        "user-1",
        "novel-1",
        VersionPreviewRequest(
            documentType="manuscript",
            chapterId="chapter-1",
            baseVersionId=first.id,
        ),
    )

    second = await service.submit_manual(
        "user-1",
        "novel-1",
        ManualVersionRequest(
            clientRequestId="request-12345678",
            documentType="manuscript",
            chapterId="chapter-1",
            baseVersionId=first.id,
            expectedUpdatedAt=tx.document.updated_at,
            contentHash=sha256("第二稿"),
            confirmationHash=manuscript_preview.confirmationHash,
        ),
    )

    assert second.sourceOutlineVersionId == "outline-version-1"


@pytest.mark.asyncio
async def test_cross_document_diff_is_rejected() -> None:
    service, tx = outline_service()
    preview = await service.preview(
        "user-1",
        "novel-1",
        VersionPreviewRequest(documentType="outline", baseVersionId=None),
    )
    outline = await service.submit_manual(
        "user-1",
        "novel-1",
        ManualVersionRequest(
            clientRequestId="request-12345678",
            documentType="outline",
            baseVersionId=None,
            expectedUpdatedAt=NOW,
            contentHash=sha256("初稿"),
            confirmationHash=preview.confirmationHash,
        ),
    )
    manuscript = VersionRecord(
        id="manuscript-version",
        novel_id="novel-1",
        chapter_id="chapter-1",
        artifact_key="short-medium:manuscript:chapter-1",
        status="applied",
        summary=None,
        payload=outline.payload.model_copy(
            update={
                "kind": "chapter_draft",
                "documentType": "manuscript",
                "sourceOutlineVersionId": outline.id,
            }
        ),
        diff=None,
        created_by_agent=None,
        task_id=None,
        created_at=NOW,
        updated_at=NOW,
        applied_at=NOW,
    )
    tx.versions.append(manuscript)

    with pytest.raises(ApiError) as error:
        await service.diff_versions(
            "user-1", "novel-1", outline.id, manuscript.id
        )
    assert error.value.code == "SHORT_MEDIUM_DIFF_TYPE_MISMATCH"
