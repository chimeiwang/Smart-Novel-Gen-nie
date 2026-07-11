from __future__ import annotations

import inspect

import pytest
from inkforge_core.errors import ApiError
from inkforge_core.outlines.repository import OutlineRepository


def test_every_outline_mutation_uses_transaction_and_owner_recheck() -> None:
    for name in ("upsert_outline", "upsert_plot", "create_node", "update_node", "delete_node"):
        source = inspect.getsource(getattr(OutlineRepository, name))
        if name.startswith("upsert_"):
            source = inspect.getsource(OutlineRepository._upsert_singleton)
        assert "session.begin()" in source
        assert "_require_owner" in source


def test_node_mutations_take_novel_level_advisory_lock() -> None:
    for name in ("create_node", "update_node", "delete_node"):
        assert "_lock_novel" in inspect.getsource(getattr(OutlineRepository, name))
    lock_source = inspect.getsource(OutlineRepository._lock_novel)
    assert "pg_advisory_xact_lock(:key)" in lock_source
    assert "sha256" in lock_source


def test_node_update_and_delete_are_scoped_by_id_and_novel() -> None:
    for name in ("update_node", "delete_node"):
        source = inspect.getsource(getattr(OutlineRepository, name))
        assert "OutlineNode.id == node_id" in source
        assert "OutlineNode.novelId == novel_id" in source
        assert "rowcount != 1" in source


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
