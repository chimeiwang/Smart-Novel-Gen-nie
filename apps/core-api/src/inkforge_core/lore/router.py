from __future__ import annotations

# mypy: disable-error-code="no-untyped-def"
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Request, Response, status

from ..auth.dependencies import get_current_user
from ..auth.repository import AuthUser
from ..errors import ApiError
from .schemas import (
    CharacterResponse,
    ContentRequest,
    ContentResponse,
    CreateCharacterRequest,
    CreateFactionRequest,
    CreateGlossaryRequest,
    CreateItemRequest,
    CreateLocationRequest,
    ExperienceRequest,
    ExperienceResponse,
    FactionResponse,
    GlossaryResponse,
    ItemResponse,
    LocationResponse,
    RelationRequest,
    RelationResponse,
    UpdateCharacterRequest,
    UpdateFactionRequest,
    UpdateGlossaryRequest,
    UpdateItemRequest,
    UpdateLocationRequest,
    UpdateRelationRequest,
    WritingBibleRequest,
    WritingBibleResponse,
)
from .service import LoreService

router = APIRouter(tags=["小说设定"])
User = Annotated[AuthUser, Depends(get_current_user)]


def get_lore_service(request: Request) -> LoreService:
    service = cast(LoreService | None, getattr(request.app.state, "lore_service", None))
    if service is None:
        raise ApiError(
            status_code=503, code="LORE_SERVICE_UNAVAILABLE", message="设定服务暂时不可用"
        )
    return service


Service = Annotated[LoreService, Depends(get_lore_service)]


async def _list(user: AuthUser, service: LoreService, novel_id: str, kind: str):
    return await service.list_entities(user.id, novel_id, kind)


async def _create(user: AuthUser, service: LoreService, novel_id: str, kind: str, body: Any):
    return await service.create_entity(user.id, novel_id, kind, body)


async def _update(
    user: AuthUser, service: LoreService, novel_id: str, kind: str, entity_id: str, body: Any
):
    return await service.update_entity(user.id, novel_id, kind, entity_id, body)


async def _delete(
    user: AuthUser, service: LoreService, novel_id: str, kind: str, entity_id: str
) -> Response:
    await service.delete_entity(user.id, novel_id, kind, entity_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/novels/{novel_id}/characters", response_model=list[CharacterResponse])
async def list_characters(novel_id: str, user: User, service: Service):
    return await _list(user, service, novel_id, "characters")


@router.post("/novels/{novel_id}/characters", response_model=CharacterResponse, status_code=201)
async def create_character(
    novel_id: str, body: CreateCharacterRequest, user: User, service: Service
):
    return await _create(user, service, novel_id, "characters", body)


@router.patch("/novels/{novel_id}/characters/{entity_id}", response_model=CharacterResponse)
async def update_character(
    novel_id: str, entity_id: str, body: UpdateCharacterRequest, user: User, service: Service
):
    return await _update(user, service, novel_id, "characters", entity_id, body)


@router.delete("/novels/{novel_id}/characters/{entity_id}", status_code=204)
async def delete_character(novel_id: str, entity_id: str, user: User, service: Service):
    return await _delete(user, service, novel_id, "characters", entity_id)


@router.get("/novels/{novel_id}/items", response_model=list[ItemResponse])
async def list_items(novel_id: str, user: User, service: Service):
    return await _list(user, service, novel_id, "items")


@router.post("/novels/{novel_id}/items", response_model=ItemResponse, status_code=201)
async def create_item(novel_id: str, body: CreateItemRequest, user: User, service: Service):
    return await _create(user, service, novel_id, "items", body)


@router.patch("/novels/{novel_id}/items/{entity_id}", response_model=ItemResponse)
async def update_item(
    novel_id: str, entity_id: str, body: UpdateItemRequest, user: User, service: Service
):
    return await _update(user, service, novel_id, "items", entity_id, body)


@router.delete("/novels/{novel_id}/items/{entity_id}", status_code=204)
async def delete_item(novel_id: str, entity_id: str, user: User, service: Service):
    return await _delete(user, service, novel_id, "items", entity_id)


@router.get("/novels/{novel_id}/locations", response_model=list[LocationResponse])
async def list_locations(novel_id: str, user: User, service: Service):
    return await _list(user, service, novel_id, "locations")


@router.post("/novels/{novel_id}/locations", response_model=LocationResponse, status_code=201)
async def create_location(novel_id: str, body: CreateLocationRequest, user: User, service: Service):
    return await _create(user, service, novel_id, "locations", body)


@router.patch("/novels/{novel_id}/locations/{entity_id}", response_model=LocationResponse)
async def update_location(
    novel_id: str, entity_id: str, body: UpdateLocationRequest, user: User, service: Service
):
    return await _update(user, service, novel_id, "locations", entity_id, body)


@router.delete("/novels/{novel_id}/locations/{entity_id}", status_code=204)
async def delete_location(novel_id: str, entity_id: str, user: User, service: Service):
    return await _delete(user, service, novel_id, "locations", entity_id)


@router.get("/novels/{novel_id}/factions", response_model=list[FactionResponse])
async def list_factions(novel_id: str, user: User, service: Service):
    return await _list(user, service, novel_id, "factions")


@router.post("/novels/{novel_id}/factions", response_model=FactionResponse, status_code=201)
async def create_faction(novel_id: str, body: CreateFactionRequest, user: User, service: Service):
    return await _create(user, service, novel_id, "factions", body)


@router.patch("/novels/{novel_id}/factions/{entity_id}", response_model=FactionResponse)
async def update_faction(
    novel_id: str, entity_id: str, body: UpdateFactionRequest, user: User, service: Service
):
    return await _update(user, service, novel_id, "factions", entity_id, body)


@router.delete("/novels/{novel_id}/factions/{entity_id}", status_code=204)
async def delete_faction(novel_id: str, entity_id: str, user: User, service: Service):
    return await _delete(user, service, novel_id, "factions", entity_id)


@router.get("/novels/{novel_id}/glossary", response_model=list[GlossaryResponse])
async def list_glossary(novel_id: str, user: User, service: Service):
    return await _list(user, service, novel_id, "glossary")


@router.post("/novels/{novel_id}/glossary", response_model=GlossaryResponse, status_code=201)
async def create_glossary(novel_id: str, body: CreateGlossaryRequest, user: User, service: Service):
    return await _create(user, service, novel_id, "glossary", body)


@router.patch("/novels/{novel_id}/glossary/{entity_id}", response_model=GlossaryResponse)
async def update_glossary(
    novel_id: str, entity_id: str, body: UpdateGlossaryRequest, user: User, service: Service
):
    return await _update(user, service, novel_id, "glossary", entity_id, body)


@router.delete("/novels/{novel_id}/glossary/{entity_id}", status_code=204)
async def delete_glossary(novel_id: str, entity_id: str, user: User, service: Service):
    return await _delete(user, service, novel_id, "glossary", entity_id)


@router.post(
    "/novels/{novel_id}/characters/{character_id}/experiences",
    response_model=ExperienceResponse,
    status_code=201,
)
async def create_experience(
    novel_id: str, character_id: str, body: ExperienceRequest, user: User, service: Service
):
    return await service.create_experience(user.id, novel_id, character_id, body)


@router.get(
    "/novels/{novel_id}/characters/{character_id}/experiences",
    response_model=list[ExperienceResponse],
)
async def list_experiences(novel_id: str, character_id: str, user: User, service: Service):
    return await service.list_experiences(user.id, novel_id, character_id)


@router.patch("/novels/{novel_id}/experiences/{experience_id}", response_model=ExperienceResponse)
async def update_experience(
    novel_id: str, experience_id: str, body: ExperienceRequest, user: User, service: Service
):
    return await service.update_experience(user.id, novel_id, experience_id, body)


@router.delete("/novels/{novel_id}/experiences/{experience_id}", status_code=204)
async def delete_experience(novel_id: str, experience_id: str, user: User, service: Service):
    await service.delete_experience(user.id, novel_id, experience_id)
    return Response(status_code=204)


@router.post("/novels/{novel_id}/relations", response_model=RelationResponse, status_code=201)
async def create_relation(novel_id: str, body: RelationRequest, user: User, service: Service):
    return await service.create_relation(user.id, novel_id, body)


@router.get("/novels/{novel_id}/relations", response_model=list[RelationResponse])
async def list_relations(novel_id: str, user: User, service: Service):
    return await service.list_relations(user.id, novel_id)


@router.patch("/novels/{novel_id}/relations/{relation_id}", response_model=RelationResponse)
async def update_relation(
    novel_id: str, relation_id: str, body: UpdateRelationRequest, user: User, service: Service
):
    return await service.update_relation(user.id, novel_id, relation_id, body)


@router.delete("/novels/{novel_id}/relations/{relation_id}", status_code=204)
async def delete_relation(novel_id: str, relation_id: str, user: User, service: Service):
    await service.delete_relation(user.id, novel_id, relation_id)
    return Response(status_code=204)


@router.put("/novels/{novel_id}/story-background", response_model=ContentResponse)
async def save_story_background(novel_id: str, body: ContentRequest, user: User, service: Service):
    return await service.upsert_content(user.id, novel_id, "story-background", body)


@router.put("/novels/{novel_id}/world-setting", response_model=ContentResponse)
async def save_world_setting(novel_id: str, body: ContentRequest, user: User, service: Service):
    return await service.upsert_content(user.id, novel_id, "world-setting", body)


@router.put("/novels/{novel_id}/writing-bible", response_model=WritingBibleResponse)
async def save_writing_bible(
    novel_id: str, body: WritingBibleRequest, user: User, service: Service
):
    return await service.upsert_content(user.id, novel_id, "writing-bible", body)


@router.put("/novels/{novel_id}/story-progress", response_model=ContentResponse)
async def save_story_progress(novel_id: str, body: ContentRequest, user: User, service: Service):
    return await service.upsert_content(user.id, novel_id, "story-progress", body)
