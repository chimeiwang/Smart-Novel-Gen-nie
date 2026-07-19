from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from inkforge_core.writing.schemas import (
    CreateMessageRequest,
    CreateWritingSessionRequest,
    ResumeWritingRunRequest,
    StartWritingRunRequest,
)
from inkforge_core.writing.service import WritingService
from pydantic import ValidationError


class QueryResult:
    def __init__(self, values: list[object]) -> None:
        self.values = values

    def scalars(self):
        return iter(self.values)

    def all(self) -> list[object]:
        return self.values

    def scalar_one_or_none(self):
        return None


class SessionListQuerySession:
    def __init__(self, sessions: list[object]) -> None:
        self.sessions = sessions
        self.query_count = 0
        self.statements: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback

    async def scalar(self, statement):
        self.query_count += 1
        source = str(statement)
        self.statements.append(source)
        if '"Novel".id' in source:
            return "novel-1"
        return 0

    async def execute(self, statement):
        self.query_count += 1
        source = str(statement)
        self.statements.append(source)
        if "GROUP BY" in source:
            return QueryResult([
                SimpleNamespace(sessionId="session-1", messageCount=2),
                SimpleNamespace(sessionId="session-3", messageCount=1),
            ])
        if "row_number" in source:
            return QueryResult([
                SimpleNamespace(
                    sessionId="session-1",
                    content="最后消息一",
                    role="assistant",
                    agentId="author",
                ),
                SimpleNamespace(
                    sessionId="session-3",
                    content="最后消息三",
                    role="user",
                    agentId=None,
                ),
            ])
        if 'FROM "WritingMessage"' in source:
            return QueryResult([])
        return QueryResult(self.sessions)


def writing_sessions(count: int) -> list[object]:
    from inkforge_core.db.models import WritingSession

    now = datetime(2026, 7, 14, tzinfo=UTC)
    return [
        WritingSession(
            id=f"session-{index}",
            novelId="novel-1",
            chapterId=f"chapter-{index}",
            title=f"会话 {index}",
            phase="idle",
            createdAt=now,
            updatedAt=now,
        )
        for index in range(1, count + 1)
    ]


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


def test_writing_run_requests_require_stable_client_request_id() -> None:
    start = {
        "novelId": "novel-1",
        "chapterId": "chapter-1",
        "userMessage": "开始写作",
    }
    with pytest.raises(ValidationError):
        StartWritingRunRequest.model_validate(start)
    with pytest.raises(ValidationError):
        ResumeWritingRunRequest.model_validate({"clientRequestId": "太短"})

    valid = ResumeWritingRunRequest.model_validate(
        {"clientRequestId": "request-00000001", "userMessage": "继续"}
    )
    assert valid.clientRequestId == "request-00000001"


@pytest.mark.parametrize("target", [None, 6000, 80000])
def test_short_writing_run_accepts_nullable_reference_boundaries(
    target: int | None,
) -> None:
    request = StartWritingRunRequest.model_validate(
        {
            "clientRequestId": "request-00000001",
            "novelId": "novel-1",
            "chapterId": "chapter-1",
            "workflowKind": "short_medium",
            "operation": "develop_short_outline",
            "targetWordCount": target,
            "userMessage": "根据灵感生成大纲",
        }
    )
    assert request.targetWordCount == target


@pytest.mark.parametrize("target", [5999, 80001])
def test_short_writing_run_rejects_out_of_range_target(target: int) -> None:
    with pytest.raises(ValidationError):
        StartWritingRunRequest.model_validate(
            {
                "clientRequestId": "request-00000001",
                "novelId": "novel-1",
                "chapterId": "chapter-1",
                "workflowKind": "short_medium",
                "operation": "develop_short_outline",
                "targetWordCount": target,
                "userMessage": "根据灵感生成大纲",
            }
        )


def test_long_writing_run_keeps_default_and_rejects_explicit_null_target() -> None:
    base = {
        "clientRequestId": "request-00000001",
        "novelId": "novel-1",
        "chapterId": "chapter-1",
        "workflowKind": "long_serial",
        "operation": "write_chapter",
        "userMessage": "开始写作",
    }

    request = StartWritingRunRequest.model_validate(base)
    assert request.targetWordCount == 4000
    with pytest.raises(ValidationError):
        StartWritingRunRequest.model_validate({**base, "targetWordCount": None})


@pytest.mark.parametrize(
    ("workflow_kind", "operation"),
    [
        ("short_medium", None),
        ("short_medium", "write_chapter"),
        ("long_serial", "develop_short_outline"),
        ("long_serial", "write_short_story"),
        ("long_serial", "sync_lore"),
    ],
)
def test_writing_run_rejects_cross_profile_operation(
    workflow_kind: str, operation: str | None
) -> None:
    with pytest.raises(ValidationError):
        StartWritingRunRequest.model_validate(
            {
                "clientRequestId": "request-00000001",
                "novelId": "novel-1",
                "chapterId": "chapter-1",
                "workflowKind": workflow_kind,
                "operation": operation,
                "targetWordCount": 6000,
                "userMessage": "开始",
            }
        )


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


@pytest.mark.asyncio
async def test_list_sessions_uses_fixed_queries_and_returns_stable_summaries() -> None:
    from inkforge_core.writing.repository import WritingRepository

    small_session = SessionListQuerySession(writing_sessions(1))
    large_session = SessionListQuerySession(writing_sessions(3))
    await WritingRepository(lambda: small_session).list_sessions(  # type: ignore[arg-type]
        "user-1", "novel-1", None
    )
    large = await WritingRepository(lambda: large_session).list_sessions(  # type: ignore[arg-type]
        "user-1", "novel-1", None
    )

    assert small_session.query_count == large_session.query_count == 4
    assert [value["id"] for value in large] == ["session-1", "session-2", "session-3"]
    assert large[0]["messageCount"] == 2
    assert large[0]["lastMessage"] == {
        "content": "最后消息一",
        "role": "assistant",
        "agentId": "author",
    }
    assert large[1]["messageCount"] == 0
    assert large[1]["lastMessage"] is None
    session_query = next(
        source for source in large_session.statements if '"WritingSession"' in source
    )
    assert '"WritingSession"."updatedAt" DESC' in session_query
    assert '"WritingSession".id ASC' in session_query
