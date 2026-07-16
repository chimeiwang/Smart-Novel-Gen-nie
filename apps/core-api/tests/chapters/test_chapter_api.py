from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from inkforge_core.chapters.schemas import (
    ChapterProgressRequest,
    ChapterStatusRequest,
    UpdateChapterRequest,
)
from inkforge_core.chapters.service import ChapterService
from inkforge_core.errors import ApiError


@dataclass
class ChapterRecord:
    id: str = "chapter-1"
    novel_id: str = "novel-1"
    status: str = "drafting"
    completed_at: datetime | None = None
    updated_at: datetime = datetime(2026, 7, 11, tzinfo=UTC)


class RecordingChapterRepository:
    def __init__(self) -> None:
        self.chapter = ChapterRecord()
        self.saved_title: str | None = None
        self.saved_content: str | None = None
        self.consistency_status: str | None = None
        self.created_checks = 0
        self.has_default_check = False
        self.progress_content: str | None = None

    async def require_chapter(self, chapter_id: str, user_id: str, *, lock: bool = False):
        del chapter_id, user_id, lock
        return self.chapter

    async def update_draft(
        self,
        chapter_id: str,
        user_id: str,
        title: str,
        content: str,
        expected_updated_at: datetime,
    ):
        del chapter_id, user_id, expected_updated_at
        self.saved_title = title
        self.saved_content = content
        return datetime(2026, 7, 11, tzinfo=UTC)

    async def get_consistency_status(self, chapter_id: str):
        del chapter_id
        return self.consistency_status

    async def upsert_progress(self, chapter_id: str, user_id: str, content: str):
        del chapter_id, user_id
        self.progress_content = content
        return datetime(2026, 7, 11, tzinfo=UTC)

    async def set_status_with_default_check(
        self,
        chapter_id: str,
        user_id: str,
        status: str,
        completed_at: datetime | None,
        *,
        create_default_check: bool,
    ):
        del chapter_id, user_id
        self.chapter.status = status
        self.chapter.completed_at = completed_at
        if create_default_check and not self.has_default_check:
            self.created_checks += 1
            self.has_default_check = True
        return self.chapter

    async def transition_status(
        self,
        chapter_id: str,
        user_id: str,
        status: str,
        expected_updated_at: datetime,
    ):
        del chapter_id, user_id, expected_updated_at
        allowed = {
            "drafting": {"drafting", "review"},
            "review": {"drafting", "review", "completed"},
            "completed": {"drafting", "review", "completed"},
        }
        if status not in allowed[self.chapter.status]:
            raise ApiError(
                status_code=409,
                code="INVALID_CHAPTER_STATUS_TRANSITION",
                message="章节状态不能这样切换",
            )
        if status == "completed" and self.consistency_status not in {
            "completed",
            "skipped",
        }:
            raise ApiError(
                status_code=409,
                code="QUALITY_CHECK_REQUIRED",
                message="一致性终检完成或跳过后，才能标记章节完成",
            )
        if status == "review" and not self.has_default_check:
            self.has_default_check = True
            self.created_checks += 1
        self.chapter.status = status
        self.chapter.completed_at = (
            self.chapter.completed_at or datetime.now(UTC) if status == "completed" else None
        )
        return self.chapter


@pytest.mark.asyncio
async def test_draft_title_falls_back_and_content_is_lossless() -> None:
    repository = RecordingChapterRepository()
    service = ChapterService(repository)  # type: ignore[arg-type]
    content = "  第一行\n\n最后一行  " * 10_000

    response = await service.update_chapter(
        "user-1",
        "chapter-1",
        UpdateChapterRequest(
            title="   ",
            content=content,
            expectedUpdatedAt=datetime(2026, 7, 11, tzinfo=UTC),
        ),
    )

    assert repository.saved_title == "未命名章节"
    assert repository.saved_content == content
    assert response.updatedAt == datetime(2026, 7, 11, tzinfo=UTC)


def test_chapter_mutations_require_expected_updated_at() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        UpdateChapterRequest(title="标题", content="正文")
    with pytest.raises(ValidationError):
        ChapterStatusRequest(status="review")

    expected = datetime(2026, 7, 11, tzinfo=UTC)
    update = UpdateChapterRequest(
        title="标题",
        content="正文",
        expectedUpdatedAt=expected,
    )
    status = ChapterStatusRequest(status="review", expectedUpdatedAt=expected)

    assert update.expectedUpdatedAt == expected
    assert status.expectedUpdatedAt == expected


@pytest.mark.parametrize(
    ("request_type", "body"),
    [
        (
            UpdateChapterRequest,
            {
                "title": "标题",
                "content": "正文",
                "expectedUpdatedAt": "2026-07-16T12:58:53.791000Z",
            },
        ),
        (
            ChapterStatusRequest,
            {
                "status": "review",
                "expectedUpdatedAt": "2026-07-16T12:58:53.791000Z",
            },
        ),
    ],
)
def test_chapter_mutations_accept_json_datetime_strings(request_type, body) -> None:
    request = request_type.model_validate(body)

    assert request.expectedUpdatedAt == datetime(
        2026, 7, 16, 12, 58, 53, 791000, tzinfo=UTC
    )


@pytest.mark.asyncio
async def test_review_creates_default_consistency_check_and_is_idempotent() -> None:
    repository = RecordingChapterRepository()
    service = ChapterService(repository)  # type: ignore[arg-type]

    request = ChapterStatusRequest(
        status="review",
        expectedUpdatedAt=repository.chapter.updated_at,
    )
    await service.set_status("user-1", "chapter-1", request)
    await service.set_status("user-1", "chapter-1", request)

    assert repository.created_checks == 1


@pytest.mark.asyncio
async def test_repeated_review_repairs_missing_default_check() -> None:
    repository = RecordingChapterRepository()
    repository.chapter.status = "review"
    service = ChapterService(repository)  # type: ignore[arg-type]
    await service.set_status(
        "user-1",
        "chapter-1",
        ChapterStatusRequest(
            status="review",
            expectedUpdatedAt=repository.chapter.updated_at,
        ),
    )
    assert repository.created_checks == 1


@pytest.mark.asyncio
async def test_completed_requires_finished_consistency_check() -> None:
    repository = RecordingChapterRepository()
    repository.chapter.status = "review"
    service = ChapterService(repository)  # type: ignore[arg-type]

    with pytest.raises(ApiError, match="一致性终检") as caught:
        await service.set_status(
            "user-1",
            "chapter-1",
            ChapterStatusRequest(
                status="completed",
                expectedUpdatedAt=repository.chapter.updated_at,
            ),
        )

    assert caught.value.status_code == 409
    repository.consistency_status = "completed"
    completed = await service.set_status(
        "user-1",
        "chapter-1",
        ChapterStatusRequest(
            status="completed",
            expectedUpdatedAt=repository.chapter.updated_at,
        ),
    )
    assert completed.status == "completed"
    assert completed.completedAt is not None


@pytest.mark.asyncio
async def test_illegal_status_transition_is_rejected() -> None:
    repository = RecordingChapterRepository()
    service = ChapterService(repository)  # type: ignore[arg-type]

    with pytest.raises(ApiError, match="状态") as caught:
        await service.set_status(
            "user-1",
            "chapter-1",
            ChapterStatusRequest(
                status="completed",
                expectedUpdatedAt=repository.chapter.updated_at,
            ),
        )

    assert caught.value.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source", "target"),
    [("review", "drafting"), ("completed", "drafting")],
)
async def test_return_to_drafting_clears_completed_at(source: str, target: str) -> None:
    repository = RecordingChapterRepository()
    repository.chapter.status = source
    repository.chapter.completed_at = datetime(2026, 7, 1, tzinfo=UTC)
    service = ChapterService(repository)  # type: ignore[arg-type]

    response = await service.set_status(
        "user-1",
        "chapter-1",
        ChapterStatusRequest(
            status=target,  # type: ignore[arg-type]
            expectedUpdatedAt=repository.chapter.updated_at,
        ),
    )
    assert response.status == "drafting"
    assert response.completedAt is None


@pytest.mark.asyncio
async def test_completed_can_return_to_review_and_repairs_default_check() -> None:
    repository = RecordingChapterRepository()
    repository.chapter.status = "completed"
    repository.chapter.completed_at = datetime(2026, 7, 1, tzinfo=UTC)
    service = ChapterService(repository)  # type: ignore[arg-type]
    response = await service.set_status(
        "user-1",
        "chapter-1",
        ChapterStatusRequest(
            status="review",
            expectedUpdatedAt=repository.chapter.updated_at,
        ),
    )
    assert response.status == "review"
    assert response.completedAt is None
    assert repository.created_checks == 1


@pytest.mark.asyncio
async def test_skipped_consistency_check_allows_completion() -> None:
    repository = RecordingChapterRepository()
    repository.chapter.status = "review"
    repository.consistency_status = "skipped"
    service = ChapterService(repository)  # type: ignore[arg-type]
    response = await service.set_status(
        "user-1",
        "chapter-1",
        ChapterStatusRequest(
            status="completed",
            expectedUpdatedAt=repository.chapter.updated_at,
        ),
    )
    assert response.status == "completed"
    assert response.completedAt is not None


@pytest.mark.asyncio
async def test_completed_status_is_idempotent_and_keeps_timestamp() -> None:
    completed_at = datetime(2026, 7, 10, tzinfo=UTC)
    repository = RecordingChapterRepository()
    repository.chapter.status = "completed"
    repository.chapter.completed_at = completed_at
    repository.consistency_status = "completed"
    service = ChapterService(repository)  # type: ignore[arg-type]
    response = await service.set_status(
        "user-1",
        "chapter-1",
        ChapterStatusRequest(
            status="completed",
            expectedUpdatedAt=repository.chapter.updated_at,
        ),
    )
    assert response.completedAt == completed_at
    assert repository.created_checks == 0


@pytest.mark.asyncio
async def test_idempotent_completed_revalidates_quality_gate() -> None:
    repository = RecordingChapterRepository()
    repository.chapter.status = "completed"
    repository.chapter.completed_at = datetime(2026, 7, 10, tzinfo=UTC)
    service = ChapterService(repository)  # type: ignore[arg-type]
    with pytest.raises(ApiError) as caught:
        await service.set_status(
            "user-1",
            "chapter-1",
            ChapterStatusRequest(
                status="completed",
                expectedUpdatedAt=repository.chapter.updated_at,
            ),
        )
    assert caught.value.code == "QUALITY_CHECK_REQUIRED"


@pytest.mark.asyncio
async def test_chapter_progress_is_saved_without_truncation() -> None:
    repository = RecordingChapterRepository()
    service = ChapterService(repository)  # type: ignore[arg-type]
    content = "进展\n" * 100_000
    await service.update_progress("user-1", "chapter-1", ChapterProgressRequest(content=content))
    assert repository.progress_content == content


@pytest.mark.parametrize(
    ("request_type", "body"),
    [
        (
            UpdateChapterRequest,
            {
                "title": "标题",
                "content": "正文",
                "expectedUpdatedAt": datetime(2026, 7, 11, tzinfo=UTC),
                "novelId": "越权",
            },
        ),
        (ChapterProgressRequest, {"content": "进展", "userId": "越权"}),
        (
            ChapterStatusRequest,
            {
                "status": "review",
                "expectedUpdatedAt": datetime(2026, 7, 11, tzinfo=UTC),
                "completedAt": "越权",
            },
        ),
    ],
)
def test_chapter_requests_reject_unknown_fields(request_type, body) -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="extra_forbidden"):
        request_type.model_validate(body)


@pytest.mark.parametrize(
    ("request_type", "body"),
    [
        (
            UpdateChapterRequest,
            {
                "title": 123,
                "content": "正文",
                "expectedUpdatedAt": datetime(2026, 7, 11, tzinfo=UTC),
            },
        ),
        (ChapterProgressRequest, {"content": 123}),
        (
            ChapterStatusRequest,
            {"status": 1, "expectedUpdatedAt": datetime(2026, 7, 11, tzinfo=UTC)},
        ),
        (
            UpdateChapterRequest,
            {"title": "标题", "content": "正文", "expectedUpdatedAt": 123},
        ),
    ],
)
def test_chapter_requests_reject_coerced_values(request_type, body) -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        request_type.model_validate(body)


def test_openapi_publishes_exact_chapter_and_workspace_enums() -> None:
    from inkforge_core.app import create_app

    schemas = create_app(testing=True).openapi()["components"]["schemas"]
    request_status_ref = schemas["ChapterStatusRequest"]["properties"]["status"]["$ref"]
    assert schemas[request_status_ref.rsplit("/", 1)[-1]]["enum"] == [
        "drafting",
        "review",
        "completed",
    ]
    chapter_status_ref = schemas["WorkspaceChapter"]["properties"]["status"]["$ref"]
    quality_status_ref = schemas["QualityCheckDto"]["properties"]["status"]["$ref"]
    assert schemas[chapter_status_ref.rsplit("/", 1)[-1]]["enum"] == [
        "drafting",
        "review",
        "completed",
    ]
    assert schemas[quality_status_ref.rsplit("/", 1)[-1]]["enum"] == [
        "pending",
        "running",
        "completed",
        "skipped",
        "failed",
    ]


def test_chapter_creation_uses_owner_lock_and_exact_numbering() -> None:
    import inspect

    from inkforge_core.chapters.repository import ChapterRepository

    source = inspect.getsource(ChapterRepository.create_chapter)
    assert ".with_for_update()" in source
    assert "func.max(Chapter.order)" in source
    assert 'title=f"第 {next_order} 章"' in source
    assert ".limit(" not in source


@pytest.mark.asyncio
async def test_legacy_null_owner_is_forbidden() -> None:
    from inkforge_core.chapters.repository import ChapterRepository
    from inkforge_core.db.models import Novel

    class Session:
        async def get(self, model, identity):
            del model, identity
            return Novel(id="novel-1", userId=None, name="旧小说")

    repository = ChapterRepository(lambda: None)  # type: ignore[arg-type]
    with pytest.raises(ApiError) as caught:
        await repository._require_novel(Session(), "novel-1", "user-1")  # type: ignore[arg-type]
    assert caught.value.status_code == 403
