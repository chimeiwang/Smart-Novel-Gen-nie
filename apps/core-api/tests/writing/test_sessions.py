from datetime import datetime

import pytest
from inkforge_core.writing.schemas import (
    CreateMessageRequest,
    CreateWritingSessionRequest,
)
from inkforge_core.writing.service import WritingService
from pydantic import ValidationError


class FakeWritingRepository:
    def __init__(self) -> None:
        self.created: tuple[str, str, str, str | None] | None = None

    async def create_session(
        self, user_id: str, novel_id: str, chapter_id: str, title: str | None
    ) -> dict[str, object]:
        self.created = (user_id, novel_id, chapter_id, title)
        return {
            "id": "session-1",
            "novelId": novel_id,
            "chapterId": chapter_id,
            "title": title,
            "phase": "idle",
            "createdAt": datetime(2026, 7, 11, 12, 0, 0),
            "updatedAt": datetime(2026, 7, 11, 12, 0, 0),
        }


def test_session_and_message_requests_are_strict() -> None:
    with pytest.raises(ValidationError):
        CreateWritingSessionRequest.model_validate(
            {"novelId": "novel-1", "chapterId": "chapter-1", "userId": "攻击者"}
        )
    with pytest.raises(ValidationError):
        CreateMessageRequest.model_validate({"role": "unknown", "content": "内容"})


@pytest.mark.asyncio
async def test_create_session_uses_authenticated_user_identity() -> None:
    repository = FakeWritingRepository()
    service = WritingService(repository)

    result = await service.create_session(
        "user-1",
        CreateWritingSessionRequest(
            novelId="novel-1",
            chapterId="chapter-1",
            title="第一章讨论",
        ),
    )

    assert repository.created == ("user-1", "novel-1", "chapter-1", "第一章讨论")
    assert result.id == "session-1"
