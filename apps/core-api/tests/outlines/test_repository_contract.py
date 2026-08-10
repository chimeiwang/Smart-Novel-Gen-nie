from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta

import pytest
from inkforge_core.errors import ApiError
from inkforge_core.outlines.repository import OutlineRepository
from inkforge_core.outlines.schemas import OutlineContentRequest
from inkforge_core.outlines.service import OutlineService


def test_every_outline_mutation_uses_transaction_and_owner_recheck() -> None:
    for name in ("upsert_outline", "upsert_plot", "create_node", "update_node", "delete_node"):
        source = inspect.getsource(getattr(OutlineRepository, name))
        assert "session.begin()" in source
        assert "_require_owner" in source


def test_outline_save_checks_safe_precondition_before_content_equality() -> None:
    source = inspect.getsource(OutlineRepository.upsert_outline)
    assert source.index("_require_safe_outline_precondition(") < source.index(
        "if outline.content != content:"
    )


def test_outline_mutations_take_novel_level_row_and_advisory_lock() -> None:
    for name in (
        "upsert_outline",
        "upsert_plot",
        "create_node",
        "update_node",
        "delete_node",
        "replace_nodes",
    ):
        assert "_lock_novel" in inspect.getsource(getattr(OutlineRepository, name))
    lock_source = inspect.getsource(OutlineRepository._lock_novel)
    assert "select(Novel)" in lock_source
    assert "with_for_update" in lock_source
    assert "pg_advisory_xact_lock(:key)" in lock_source
    assert "sha256" in lock_source


def test_plot_progress_uses_locked_explicit_cas_before_idempotency_check() -> None:
    source = inspect.getsource(OutlineRepository.upsert_plot)

    assert "select(PlotProgress)" in source
    assert "with_for_update()" in source
    assert "require_expected_updated_at(" in source
    assert 'code="PLOT_PROGRESS_VERSION_CONFLICT"' in source
    assert "next_utc_timestamp(" in source
    assert source.index("require_expected_updated_at(") < source.index(
        "if any("
    )
    assert "_upsert_singleton" not in source
    assert "pg_insert" not in source


def test_node_update_and_delete_are_scoped_by_id_and_novel() -> None:
    for name in ("update_node", "delete_node"):
        source = inspect.getsource(getattr(OutlineRepository, name))
        assert "OutlineNode.id == node_id" in source
        assert "OutlineNode.novelId == novel_id" in source
        assert ".with_for_update()" in source
        assert "OUTLINE_NODE_VERSION_CONFLICT" in source

    delete_source = inspect.getsource(OutlineRepository.delete_node)
    assert "rowcount != 1" in delete_source


class ScalarSession:
    async def scalar(self, statement):
        del statement
        return "novel-other"


@pytest.mark.asyncio
async def test_linked_chapter_must_belong_to_same_novel() -> None:
    with pytest.raises(ApiError) as caught:
        await OutlineRepository._validate_links(  # type: ignore[arg-type]
            ScalarSession(), "novel-1", {"linkedChapterId": "chapter-other"}
        )
    assert caught.value.code == "OUTLINE_CHAPTER_CROSS_NOVEL"


class RecordingOutlineRepository:
    def __init__(self) -> None:
        self.saved: tuple[str, str, str, datetime] | None = None

    async def upsert_outline(
        self,
        novel_id: str,
        user_id: str,
        content: str,
        expected_updated_at: datetime,
    ) -> dict[str, object]:
        self.saved = (novel_id, user_id, content, expected_updated_at)
        return {
            "id": "outline-1",
            "content": content,
            "contentHash": "hash",
            "createdAt": expected_updated_at,
            "updatedAt": expected_updated_at,
        }


@pytest.mark.asyncio
async def test_outline_service_passes_expected_updated_at_and_returns_hash() -> None:
    repository = RecordingOutlineRepository()
    service = OutlineService(repository)  # type: ignore[arg-type]
    expected = datetime(2026, 7, 30, tzinfo=UTC)

    result = await service.save_outline(
        "user-1",
        "novel-1",
        OutlineContentRequest(content="新大纲", expectedUpdatedAt=expected),
    )

    assert repository.saved == ("novel-1", "user-1", "新大纲", expected)
    assert result["contentHash"] == "hash"


def test_outline_expected_updated_at_conflict_keeps_current_value() -> None:
    from inkforge_core.outlines.repository import _require_expected_updated_at

    current = datetime(2026, 7, 30, tzinfo=UTC)
    with pytest.raises(ApiError) as caught:
        _require_expected_updated_at(current, current - timedelta(seconds=1))

    assert caught.value.status_code == 409
    assert caught.value.code == "OUTLINE_VERSION_CONFLICT"
    assert caught.value.details == {"currentUpdatedAt": current.isoformat()}


def test_outline_request_accepts_json_datetime_without_relaxing_strict_fields() -> None:
    request = OutlineContentRequest.model_validate(
        {
            "content": "大纲",
            "expectedUpdatedAt": "2026-07-30T00:00:00Z",
        }
    )

    assert request.expectedUpdatedAt == datetime(2026, 7, 30, tzinfo=UTC)


def test_legacy_outline_write_without_precondition_cannot_change_content() -> None:
    from inkforge_core.outlines.repository import _require_safe_outline_precondition

    current = datetime(2026, 7, 30, tzinfo=UTC)
    with pytest.raises(ApiError) as caught:
        _require_safe_outline_precondition(
            current,
            None,
            current_content="当前大纲",
            requested_content="旧草案覆盖",
        )

    assert caught.value.code == "OUTLINE_PRECONDITION_REQUIRED"
    _require_safe_outline_precondition(
        current,
        None,
        current_content="当前大纲",
        requested_content="当前大纲",
    )
