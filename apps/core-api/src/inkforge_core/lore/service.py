from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel

from ..errors import ApiError
from .schemas import ContentRequest, DeleteEntityRequest, WritingBibleRequest


class LoreRepositoryPort(Protocol):
    async def list_entities(
        self, novel_id: str, user_id: str, kind: str
    ) -> list[dict[str, Any]]: ...
    async def create_entity(
        self,
        novel_id: str,
        user_id: str,
        kind: str,
        client_request_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]: ...
    async def update_entity(
        self,
        novel_id: str,
        user_id: str,
        kind: str,
        entity_id: str,
        fields: dict[str, Any],
        expected_updated_at: datetime,
    ) -> dict[str, Any]: ...
    async def upsert_content(
        self,
        novel_id: str,
        user_id: str,
        kind: str,
        content: Any,
        expected_updated_at: datetime | None,
    ) -> dict[str, Any]: ...
    async def delete_entity(
        self,
        novel_id: str,
        user_id: str,
        kind: str,
        entity_id: str,
        expected_updated_at: datetime,
    ) -> dict[str, Any]: ...
    async def create_experience(
        self,
        novel_id: str,
        user_id: str,
        character_id: str,
        client_request_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]: ...
    async def list_experiences(
        self, novel_id: str, user_id: str, character_id: str
    ) -> list[dict[str, Any]]: ...
    async def update_experience(
        self,
        novel_id: str,
        user_id: str,
        experience_id: str,
        fields: dict[str, Any],
        expected_updated_at: datetime,
    ) -> dict[str, Any]: ...
    async def delete_experience(
        self,
        novel_id: str,
        user_id: str,
        experience_id: str,
        expected_updated_at: datetime,
    ) -> dict[str, Any]: ...
    async def create_relation(
        self,
        novel_id: str,
        user_id: str,
        client_request_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]: ...
    async def list_relations(self, novel_id: str, user_id: str) -> list[dict[str, Any]]: ...
    async def update_relation(
        self,
        novel_id: str,
        user_id: str,
        relation_id: str,
        fields: dict[str, Any],
        expected_updated_at: datetime,
    ) -> dict[str, Any]: ...
    async def delete_relation(
        self,
        novel_id: str,
        user_id: str,
        relation_id: str,
        expected_updated_at: datetime,
    ) -> dict[str, Any]: ...


class LoreService:
    def __init__(self, repository: LoreRepositoryPort) -> None:
        self._repository = repository

    async def list_entities(self, user_id: str, novel_id: str, kind: str) -> list[dict[str, Any]]:
        return await self._repository.list_entities(novel_id, user_id, kind)

    async def create_entity(
        self, user_id: str, novel_id: str, kind: str, request: BaseModel
    ) -> dict[str, Any]:
        client_request_id = getattr(request, "clientRequestId", None)
        if not isinstance(client_request_id, str):
            raise TypeError("实体创建请求缺少 clientRequestId")
        fields = request.model_dump(exclude={"clientRequestId"})
        self._require_name(kind, fields)
        return await self._repository.create_entity(
            novel_id, user_id, kind, client_request_id, fields
        )

    async def update_entity(
        self, user_id: str, novel_id: str, kind: str, entity_id: str, request: BaseModel
    ) -> dict[str, Any]:
        expected_updated_at = getattr(request, "expectedUpdatedAt", None)
        if not isinstance(expected_updated_at, datetime):
            raise TypeError("实体更新请求缺少 expectedUpdatedAt")
        fields = request.model_dump(exclude={"expectedUpdatedAt"}, exclude_unset=True)
        self._require_update_fields(fields)
        self._require_name(kind, fields)
        return await self._repository.update_entity(
            novel_id,
            user_id,
            kind,
            entity_id,
            fields,
            expected_updated_at,
        )

    async def delete_entity(
        self,
        user_id: str,
        novel_id: str,
        kind: str,
        entity_id: str,
        request: DeleteEntityRequest,
    ) -> dict[str, Any]:
        return await self._repository.delete_entity(
            novel_id,
            user_id,
            kind,
            entity_id,
            request.expectedUpdatedAt,
        )

    async def create_experience(
        self, user_id: str, novel_id: str, character_id: str, request: BaseModel
    ) -> dict[str, Any]:
        client_request_id = getattr(request, "clientRequestId", None)
        if not isinstance(client_request_id, str):
            raise TypeError("角色经历创建请求缺少 clientRequestId")
        return await self._repository.create_experience(
            novel_id,
            user_id,
            character_id,
            client_request_id,
            request.model_dump(exclude={"clientRequestId"}),
        )

    async def list_experiences(
        self, user_id: str, novel_id: str, character_id: str
    ) -> list[dict[str, Any]]:
        return await self._repository.list_experiences(novel_id, user_id, character_id)

    async def update_experience(
        self, user_id: str, novel_id: str, experience_id: str, request: BaseModel
    ) -> dict[str, Any]:
        expected_updated_at = getattr(request, "expectedUpdatedAt", None)
        if not isinstance(expected_updated_at, datetime):
            raise TypeError("角色经历更新请求缺少 expectedUpdatedAt")
        fields = request.model_dump(exclude={"expectedUpdatedAt"}, exclude_unset=True)
        self._require_update_fields(fields)
        if any(fields.get(field) is None for field in ("content", "order") if field in fields):
            raise ApiError(
                status_code=422,
                code="LORE_FIELD_REQUIRED",
                message="经历内容和顺序不能为 null",
            )
        return await self._repository.update_experience(
            novel_id,
            user_id,
            experience_id,
            fields,
            expected_updated_at,
        )

    async def delete_experience(
        self,
        user_id: str,
        novel_id: str,
        experience_id: str,
        request: DeleteEntityRequest,
    ) -> dict[str, Any]:
        return await self._repository.delete_experience(
            novel_id, user_id, experience_id, request.expectedUpdatedAt
        )

    async def create_relation(
        self, user_id: str, novel_id: str, request: BaseModel
    ) -> dict[str, Any]:
        client_request_id = getattr(request, "clientRequestId", None)
        if not isinstance(client_request_id, str):
            raise TypeError("人物关系创建请求缺少 clientRequestId")
        return await self._repository.create_relation(
            novel_id,
            user_id,
            client_request_id,
            request.model_dump(exclude={"clientRequestId"}),
        )

    async def list_relations(self, user_id: str, novel_id: str) -> list[dict[str, Any]]:
        return await self._repository.list_relations(novel_id, user_id)

    async def update_relation(
        self, user_id: str, novel_id: str, relation_id: str, request: BaseModel
    ) -> dict[str, Any]:
        expected_updated_at = getattr(request, "expectedUpdatedAt", None)
        if not isinstance(expected_updated_at, datetime):
            raise TypeError("人物关系更新请求缺少 expectedUpdatedAt")
        fields = request.model_dump(exclude={"expectedUpdatedAt"}, exclude_unset=True)
        self._require_update_fields(fields)
        if any(
            fields.get(field) is None for field in ("relationType", "intimacy") if field in fields
        ):
            raise ApiError(
                status_code=422,
                code="LORE_FIELD_REQUIRED",
                message="关系类型和亲密度不能为 null",
            )
        return await self._repository.update_relation(
            novel_id, user_id, relation_id, fields, expected_updated_at
        )

    async def delete_relation(
        self,
        user_id: str,
        novel_id: str,
        relation_id: str,
        request: DeleteEntityRequest,
    ) -> dict[str, Any]:
        return await self._repository.delete_relation(
            novel_id, user_id, relation_id, request.expectedUpdatedAt
        )

    async def upsert_content(
        self,
        user_id: str,
        novel_id: str,
        kind: str,
        request: ContentRequest | WritingBibleRequest,
    ) -> dict[str, Any]:
        if kind == "writing-bible":
            if not isinstance(request, WritingBibleRequest):
                raise TypeError("作品圣经请求类型无效")
            story_length_profile = request.storyLengthProfile
            if story_length_profile not in {None, "long_serial"}:
                raise ApiError(
                    status_code=422,
                    code="WRITING_BIBLE_PROFILE_MISMATCH",
                    message="长篇作品不能改为中短篇模式",
                )
            content: Any = request.model_dump(
                exclude={"expectedUpdatedAt"},
                exclude_unset=True,
            )
            if content.get("storyLengthProfile") is None:
                content.pop("storyLengthProfile", None)
            self._require_update_fields(content)
        else:
            if not isinstance(request, ContentRequest):
                raise TypeError("内容请求类型无效")
            content = request.content
        if kind == "story-progress" and content is not None and len(content) > 30_000:
            raise ApiError(
                status_code=422,
                code="STORY_PROGRESS_TOO_LONG",
                message="故事进度不能超过 30000 个字符",
            )
        expected_updated_at = request.expectedUpdatedAt
        return await self._repository.upsert_content(
            novel_id,
            user_id,
            kind,
            content,
            expected_updated_at,
        )

    @staticmethod
    def _require_name(kind: str, fields: dict[str, Any]) -> None:
        required_fields = {
            "characters": ("name", "currentStatus"),
            "items": ("name",),
            "locations": ("name",),
            "factions": ("name",),
            "glossary": ("term", "definition"),
        }.get(kind, ())
        if any(field in fields and fields[field] is None for field in required_fields):
            raise ApiError(
                status_code=422,
                code="LORE_FIELD_REQUIRED",
                message="该字段不能为 null",
            )
        name_field = {"glossary": "term"}.get(kind, "name")
        value = fields.get(name_field)
        if value is not None and not value.strip():
            raise ApiError(status_code=422, code="LORE_NAME_REQUIRED", message="名称不能为空")

    @staticmethod
    def _require_update_fields(fields: dict[str, Any]) -> None:
        if not fields:
            raise ApiError(status_code=422, code="EMPTY_UPDATE", message="至少需要提供一个更新字段")
