from __future__ import annotations

from typing import Protocol

from .recovery import TaskCandidate, select_recovery_state
from .schemas import (
    CreateMessageRequest,
    CreateWritingSessionRequest,
    MessageResponse,
    UpdateWritingSessionRequest,
    WritingSessionDetail,
    WritingSessionListItem,
    WritingSessionResponse,
)


class WritingRepositoryPort(Protocol):
    async def create_session(
        self, user_id: str, novel_id: str, chapter_id: str, title: str | None
    ) -> dict[str, object]: ...
    async def list_sessions(
        self, user_id: str, novel_id: str, chapter_id: str | None
    ) -> list[dict[str, object]]: ...
    async def get_session_detail(
        self, user_id: str, session_id: str
    ) -> tuple[dict[str, object], list[TaskCandidate]]: ...
    async def update_session(
        self, user_id: str, session_id: str, request: UpdateWritingSessionRequest
    ) -> dict[str, object]: ...
    async def delete_session(self, user_id: str, session_id: str) -> None: ...
    async def add_message(
        self, user_id: str, session_id: str, request: CreateMessageRequest
    ) -> dict[str, object]: ...


class WritingService:
    def __init__(self, repository: WritingRepositoryPort) -> None:
        self._repository = repository

    async def create_session(
        self, user_id: str, request: CreateWritingSessionRequest
    ) -> WritingSessionResponse:
        value = await self._repository.create_session(
            user_id, request.novelId, request.chapterId, request.title
        )
        return WritingSessionResponse.model_validate(value)

    async def list_sessions(
        self, user_id: str, novel_id: str, chapter_id: str | None
    ) -> list[WritingSessionListItem]:
        return [
            WritingSessionListItem.model_validate(item)
            for item in await self._repository.list_sessions(user_id, novel_id, chapter_id)
        ]

    async def get_session(self, user_id: str, session_id: str) -> WritingSessionDetail:
        value, tasks = await self._repository.get_session_detail(user_id, session_id)
        recovery = select_recovery_state(tasks)
        return WritingSessionDetail.model_validate({**value, **recovery.model_dump()})

    async def update_session(
        self, user_id: str, session_id: str, request: UpdateWritingSessionRequest
    ) -> WritingSessionResponse:
        return WritingSessionResponse.model_validate(
            await self._repository.update_session(user_id, session_id, request)
        )

    async def delete_session(self, user_id: str, session_id: str) -> None:
        await self._repository.delete_session(user_id, session_id)

    async def add_message(
        self, user_id: str, session_id: str, request: CreateMessageRequest
    ) -> MessageResponse:
        return MessageResponse.model_validate(
            await self._repository.add_message(user_id, session_id, request)
        )
