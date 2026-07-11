from __future__ import annotations

import pytest
from inkforge_core.errors import ApiError
from inkforge_core.outlines.schemas import (
    CreateForeshadowingRequest,
    UpdateForeshadowingRequest,
    UpdateOutlineNodeRequest,
)
from inkforge_core.outlines.service import OutlineService


class Repository:
    def __init__(self) -> None:
        self.call = None

    async def list_foreshadowings(self, novel_id, user_id):
        self.call = ("list", novel_id, user_id)
        return []

    async def create_foreshadowing(self, novel_id, user_id, fields):
        self.call = ("create", novel_id, user_id, fields)
        return {"id": "f-1", **fields}

    async def update_foreshadowing(self, novel_id, user_id, entity_id, fields):
        self.call = ("update", novel_id, user_id, entity_id, fields)
        return {"id": entity_id, **fields}

    async def delete_foreshadowing(self, novel_id, user_id, entity_id):
        self.call = ("delete", novel_id, user_id, entity_id)


@pytest.mark.asyncio
async def test_foreshadowing_list_is_in_outline_domain() -> None:
    repository = Repository()
    service = OutlineService(repository)  # type: ignore[arg-type]
    await service.list_foreshadowings("user-1", "novel-1")
    assert repository.call == ("list", "novel-1", "user-1")


@pytest.mark.asyncio
async def test_foreshadowing_create_preserves_text() -> None:
    repository = Repository()
    service = OutlineService(repository)  # type: ignore[arg-type]
    await service.create_foreshadowing(
        "user-1",
        "novel-1",
        CreateForeshadowingRequest(name="伏笔", plantedContent="  原文\r\n  "),
    )
    assert repository.call[3]["plantedContent"] == "  原文\r\n  "


@pytest.mark.asyncio
async def test_foreshadowing_update_keeps_omitted_fields() -> None:
    repository = Repository()
    service = OutlineService(repository)  # type: ignore[arg-type]
    await service.update_foreshadowing(
        "user-1", "novel-1", "f-1", UpdateForeshadowingRequest(status="paid_off")
    )
    assert repository.call[4] == {"status": "paid_off"}


@pytest.mark.asyncio
async def test_foreshadowing_delete_is_resource_scoped() -> None:
    repository = Repository()
    service = OutlineService(repository)  # type: ignore[arg-type]
    await service.delete_foreshadowing("user-1", "novel-1", "f-1")
    assert repository.call == ("delete", "novel-1", "user-1", "f-1")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "body"),
    [
        ("node", UpdateOutlineNodeRequest()),
        ("foreshadowing", UpdateForeshadowingRequest()),
    ],
)
async def test_empty_outline_domain_update_is_rejected(kind, body) -> None:
    service = OutlineService(Repository())  # type: ignore[arg-type]
    with pytest.raises(ApiError) as caught:
        if kind == "node":
            await service.update_node("user-1", "novel-1", "node-1", body)
        else:
            await service.update_foreshadowing("user-1", "novel-1", "f-1", body)
    assert caught.value.code == "EMPTY_UPDATE"
