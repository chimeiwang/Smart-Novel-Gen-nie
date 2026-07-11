from __future__ import annotations

from typing import Any, Protocol

from ..errors import ApiError
from .schemas import (
    CreateForeshadowingRequest,
    CreateOutlineNodeRequest,
    OutlineContentRequest,
    PlotProgressRequest,
    UpdateForeshadowingRequest,
    UpdateOutlineNodeRequest,
)


class OutlineRepositoryPort(Protocol):
    async def list_nodes(self, novel_id: str, user_id: str) -> list[dict[str, Any]]: ...
    async def upsert_outline(self, novel_id: str, user_id: str, content: str) -> dict[str, Any]: ...
    async def upsert_plot(
        self, novel_id: str, user_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]: ...
    async def create_node(
        self, novel_id: str, user_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]: ...
    async def update_node(
        self, novel_id: str, user_id: str, node_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]: ...
    async def delete_node(self, novel_id: str, user_id: str, node_id: str) -> None: ...
    async def list_foreshadowings(self, novel_id: str, user_id: str) -> list[dict[str, Any]]: ...
    async def create_foreshadowing(
        self, novel_id: str, user_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]: ...
    async def update_foreshadowing(
        self,
        novel_id: str,
        user_id: str,
        foreshadowing_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]: ...
    async def delete_foreshadowing(
        self, novel_id: str, user_id: str, foreshadowing_id: str
    ) -> None: ...


class OutlineService:
    def __init__(self, repository: OutlineRepositoryPort) -> None:
        self._repository = repository

    async def save_outline(
        self, user_id: str, novel_id: str, body: OutlineContentRequest
    ) -> dict[str, Any]:
        return await self._repository.upsert_outline(novel_id, user_id, body.content)

    async def save_plot(
        self, user_id: str, novel_id: str, body: PlotProgressRequest
    ) -> dict[str, Any]:
        return await self._repository.upsert_plot(novel_id, user_id, body.model_dump())

    async def list_nodes(self, user_id: str, novel_id: str) -> list[dict[str, Any]]:
        return await self._repository.list_nodes(novel_id, user_id)

    async def create_node(
        self, user_id: str, novel_id: str, body: CreateOutlineNodeRequest
    ) -> dict[str, Any]:
        return await self._repository.create_node(novel_id, user_id, body.model_dump())

    async def update_node(
        self, user_id: str, novel_id: str, node_id: str, body: UpdateOutlineNodeRequest
    ) -> dict[str, Any]:
        fields = body.model_dump(exclude_unset=True)
        self._require_update_fields(fields)
        if any(
            fields.get(field) is None
            for field in ("title", "kind", "status", "order")
            if field in fields
        ):
            raise ApiError(
                status_code=422,
                code="OUTLINE_FIELD_REQUIRED",
                message="标题、类型、状态和顺序不能为 null",
            )
        return await self._repository.update_node(novel_id, user_id, node_id, fields)

    async def delete_node(self, user_id: str, novel_id: str, node_id: str) -> None:
        await self._repository.delete_node(novel_id, user_id, node_id)

    async def list_foreshadowings(self, user_id: str, novel_id: str) -> list[dict[str, Any]]:
        return await self._repository.list_foreshadowings(novel_id, user_id)

    async def create_foreshadowing(
        self, user_id: str, novel_id: str, body: CreateForeshadowingRequest
    ) -> dict[str, Any]:
        if not body.name.strip():
            raise ApiError(
                status_code=422, code="FORESHADOWING_NAME_REQUIRED", message="伏笔名称不能为空"
            )
        return await self._repository.create_foreshadowing(novel_id, user_id, body.model_dump())

    async def update_foreshadowing(
        self,
        user_id: str,
        novel_id: str,
        foreshadowing_id: str,
        body: UpdateForeshadowingRequest,
    ) -> dict[str, Any]:
        fields = body.model_dump(exclude_unset=True)
        self._require_update_fields(fields)
        if any(fields.get(field) is None for field in ("name", "status") if field in fields):
            raise ApiError(
                status_code=422,
                code="FORESHADOWING_FIELD_REQUIRED",
                message="伏笔名称和状态不能为 null",
            )
        if "name" in fields and not fields["name"].strip():
            raise ApiError(
                status_code=422, code="FORESHADOWING_NAME_REQUIRED", message="伏笔名称不能为空"
            )
        return await self._repository.update_foreshadowing(
            novel_id, user_id, foreshadowing_id, fields
        )

    async def delete_foreshadowing(
        self, user_id: str, novel_id: str, foreshadowing_id: str
    ) -> None:
        await self._repository.delete_foreshadowing(novel_id, user_id, foreshadowing_id)

    @staticmethod
    def _require_update_fields(fields: dict[str, Any]) -> None:
        if not fields:
            raise ApiError(status_code=422, code="EMPTY_UPDATE", message="至少需要提供一个更新字段")
