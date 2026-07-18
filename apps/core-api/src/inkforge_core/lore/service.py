from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel

from ..errors import ApiError
from .schemas import ContentRequest


class LoreRepositoryPort(Protocol):
    async def get_writing_bible_profile(
        self, novel_id: str, user_id: str
    ) -> str | None: ...

    async def list_entities(
        self, novel_id: str, user_id: str, kind: str
    ) -> list[dict[str, Any]]: ...
    async def create_entity(
        self, novel_id: str, user_id: str, kind: str, fields: dict[str, Any]
    ) -> dict[str, Any]: ...
    async def update_entity(
        self, novel_id: str, user_id: str, kind: str, entity_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]: ...
    async def upsert_content(
        self, novel_id: str, user_id: str, kind: str, content: Any
    ) -> dict[str, Any]: ...
    async def delete_entity(
        self, novel_id: str, user_id: str, kind: str, entity_id: str
    ) -> None: ...
    async def create_experience(
        self, novel_id: str, user_id: str, character_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]: ...
    async def list_experiences(
        self, novel_id: str, user_id: str, character_id: str
    ) -> list[dict[str, Any]]: ...
    async def update_experience(
        self, novel_id: str, user_id: str, experience_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]: ...
    async def delete_experience(self, novel_id: str, user_id: str, experience_id: str) -> None: ...
    async def create_relation(
        self, novel_id: str, user_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]: ...
    async def list_relations(self, novel_id: str, user_id: str) -> list[dict[str, Any]]: ...
    async def update_relation(
        self, novel_id: str, user_id: str, relation_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]: ...
    async def delete_relation(self, novel_id: str, user_id: str, relation_id: str) -> None: ...


class LoreService:
    def __init__(self, repository: LoreRepositoryPort) -> None:
        self._repository = repository

    async def list_entities(self, user_id: str, novel_id: str, kind: str) -> list[dict[str, Any]]:
        return await self._repository.list_entities(novel_id, user_id, kind)

    async def create_entity(
        self, user_id: str, novel_id: str, kind: str, request: BaseModel
    ) -> dict[str, Any]:
        fields = request.model_dump(exclude_unset=True)
        self._require_update_fields(fields)
        self._require_name(kind, fields)
        return await self._repository.create_entity(novel_id, user_id, kind, fields)

    async def update_entity(
        self, user_id: str, novel_id: str, kind: str, entity_id: str, request: BaseModel
    ) -> dict[str, Any]:
        fields = request.model_dump(exclude_unset=True)
        self._require_update_fields(fields)
        self._require_name(kind, fields)
        return await self._repository.update_entity(novel_id, user_id, kind, entity_id, fields)

    async def delete_entity(self, user_id: str, novel_id: str, kind: str, entity_id: str) -> None:
        await self._repository.delete_entity(novel_id, user_id, kind, entity_id)

    async def create_experience(
        self, user_id: str, novel_id: str, character_id: str, request: BaseModel
    ) -> dict[str, Any]:
        return await self._repository.create_experience(
            novel_id, user_id, character_id, request.model_dump()
        )

    async def list_experiences(
        self, user_id: str, novel_id: str, character_id: str
    ) -> list[dict[str, Any]]:
        return await self._repository.list_experiences(novel_id, user_id, character_id)

    async def update_experience(
        self, user_id: str, novel_id: str, experience_id: str, request: BaseModel
    ) -> dict[str, Any]:
        return await self._repository.update_experience(
            novel_id, user_id, experience_id, request.model_dump(exclude_unset=True)
        )

    async def delete_experience(self, user_id: str, novel_id: str, experience_id: str) -> None:
        await self._repository.delete_experience(novel_id, user_id, experience_id)

    async def create_relation(
        self, user_id: str, novel_id: str, request: BaseModel
    ) -> dict[str, Any]:
        return await self._repository.create_relation(novel_id, user_id, request.model_dump())

    async def list_relations(self, user_id: str, novel_id: str) -> list[dict[str, Any]]:
        return await self._repository.list_relations(novel_id, user_id)

    async def update_relation(
        self, user_id: str, novel_id: str, relation_id: str, request: BaseModel
    ) -> dict[str, Any]:
        fields = request.model_dump(exclude_unset=True)
        self._require_update_fields(fields)
        if any(
            fields.get(field) is None for field in ("relationType", "intimacy") if field in fields
        ):
            raise ApiError(
                status_code=422,
                code="LORE_FIELD_REQUIRED",
                message="关系类型和亲密度不能为 null",
            )
        return await self._repository.update_relation(novel_id, user_id, relation_id, fields)

    async def delete_relation(self, user_id: str, novel_id: str, relation_id: str) -> None:
        await self._repository.delete_relation(novel_id, user_id, relation_id)

    async def upsert_content(
        self, user_id: str, novel_id: str, kind: str, request: ContentRequest | BaseModel
    ) -> dict[str, Any]:
        if kind == "writing-bible":
            content: Any = request.model_dump(exclude_unset=True)
            self._require_update_fields(content)
            if "targetTotalWordCount" in content:
                profile = await self._repository.get_writing_bible_profile(
                    novel_id,
                    user_id,
                )
                self._require_target_for_profile(
                    profile,
                    content["targetTotalWordCount"],
                )
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
        return await self._repository.upsert_content(novel_id, user_id, kind, content)

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

    @staticmethod
    def _require_target_for_profile(profile: str | None, target: object) -> None:
        if profile == "short_medium" and (
            not isinstance(target, int)
            or isinstance(target, bool)
            or not 6_000 <= target <= 80_000
        ):
            raise ApiError(
                status_code=422,
                code="SHORT_STORY_TARGET_WORD_COUNT_INVALID",
                message="中短篇目标总字数必须在 6000 到 80000 之间",
            )
