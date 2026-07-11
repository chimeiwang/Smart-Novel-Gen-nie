from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, cast

import httpx
import pytest
from inkforge_core.app import create_app
from inkforge_core.auth.dependencies import get_current_user
from inkforge_core.auth.repository import AuthUser
from inkforge_core.errors import ApiError
from inkforge_core.novels.schemas import CreateNovelRequest
from inkforge_core.novels.service import NovelCreation as ServiceNovelCreation
from inkforge_core.novels.service import NovelService
from pydantic import ValidationError


@dataclass
class NovelCreation:
    user_id: str
    name: str
    summary: str | None
    story_progress: str | None
    story_length_profile: str
    target_total_word_count: int
    genre: str | None
    core_selling_point: str | None
    reader_promise: str | None
    notes: str | None
    first_chapter_title: str
    first_chapter_order: int
    outline_content: str
    current_stage: str
    current_goal: str | None


class RecordingNovelRepository:
    def __init__(self) -> None:
        self.creation: NovelCreation | None = None

    async def create_novel(self, creation: NovelCreation):
        self.creation = creation
        return {"novelId": "novel-1", "chapterId": "chapter-1"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("profile", "expected_words"),
    [("short_medium", 80_000), ("long_serial", 1_000_000)],
)
async def test_create_novel_builds_all_required_defaults(
    profile: str,
    expected_words: int,
) -> None:
    repository = RecordingNovelRepository()
    service = NovelService(repository)  # type: ignore[arg-type]

    result = await service.create_novel(
        "user-1",
        CreateNovelRequest(
            name="  新作品  ",
            storyLengthProfile=profile,  # type: ignore[arg-type]
            firstChapterGoal="  主角离开故乡  ",
            protagonist="  林川  ",
        ),
    )

    assert result.model_dump() == {"novelId": "novel-1", "chapterId": "chapter-1"}
    assert repository.creation is not None
    assert repository.creation.name == "新作品"
    assert repository.creation.story_progress == "第一章目标：主角离开故乡"
    assert repository.creation.first_chapter_title == "第一章"
    assert repository.creation.first_chapter_order == 1
    assert repository.creation.outline_content == ""
    assert repository.creation.current_stage == "开篇"
    assert repository.creation.current_goal == "主角离开故乡"
    assert repository.creation.target_total_word_count == expected_words
    assert repository.creation.notes == "主角起点：林川\n第一章目标：主角离开故乡"


def test_create_novel_request_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        CreateNovelRequest.model_validate(
            {"name": "作品", "storyLengthProfile": "short_medium", "userId": "越权"}
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [("targetTotalWordCount", "80000"), ("name", 123)],
)
def test_create_novel_request_rejects_coerced_values(field: str, value: object) -> None:
    body: dict[str, object] = {
        "name": "作品",
        "storyLengthProfile": "short_medium",
        field: value,
    }
    with pytest.raises(ValidationError):
        CreateNovelRequest.model_validate(body)


class ApiNovelService:
    def __init__(self) -> None:
        self.user_id: str | None = None

    async def create_novel(self, user_id: str, body: CreateNovelRequest):
        self.user_id = user_id
        assert not hasattr(body, "userId")
        from inkforge_core.novels.schemas import CreateNovelResponse

        return CreateNovelResponse(novelId="novel-1", chapterId="chapter-1")


@asynccontextmanager
async def novel_api_client(service: ApiNovelService) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(testing=True)
    app.state.novel_service = service
    app.dependency_overrides[get_current_user] = lambda: AuthUser(
        id="cookie-user",
        username="alice",
        password_hash="",  # noqa: S106
        credit_balance_micros=0,
    )
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.mark.asyncio
async def test_create_novel_api_only_uses_cookie_owner() -> None:
    service = ApiNovelService()
    async with novel_api_client(service) as client:
        response = await client.post(
            "/api/v1/novels",
            json={"name": "作品", "storyLengthProfile": "short_medium"},
        )

    assert response.status_code == 201
    assert response.json() == {"novelId": "novel-1", "chapterId": "chapter-1"}
    assert service.user_id == "cookie-user"


@pytest.mark.asyncio
async def test_novel_api_rejects_owner_and_unknown_fields() -> None:
    async with novel_api_client(ApiNovelService()) as client:
        response = await client.post(
            "/api/v1/novels",
            json={
                "name": "作品",
                "storyLengthProfile": "short_medium",
                "userId": "attacker",
            },
        )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_novel_http_rejects_string_encoded_number() -> None:
    async with novel_api_client(ApiNovelService()) as client:
        response = await client.post(
            "/api/v1/novels",
            json={
                "name": "作品",
                "storyLengthProfile": "short_medium",
                "targetTotalWordCount": "80000",
            },
        )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_domain_openapi_has_routes_and_does_not_publish_owner_input() -> None:
    schema = create_app(testing=True).openapi()
    assert "/api/v1/novels/{novel_id}/workspace" in schema["paths"]
    assert "/api/v1/chapters/{chapter_id}/progress" in schema["paths"]
    assert "/api/v1/quality-checks/{check_id}/run" in schema["paths"]
    properties = schema["components"]["schemas"]["CreateNovelRequest"]["properties"]
    assert "userId" not in properties


@pytest.mark.parametrize("profile", ["short", "serial", "LONG_SERIAL", ""])
def test_create_novel_rejects_invalid_profile(profile: str) -> None:
    with pytest.raises(ValidationError):
        CreateNovelRequest.model_validate({"name": "作品", "storyLengthProfile": profile})


@pytest.mark.asyncio
async def test_explicit_target_words_override_profile_default() -> None:
    repository = RecordingNovelRepository()
    service = NovelService(repository)  # type: ignore[arg-type]
    await service.create_novel(
        "user-1",
        CreateNovelRequest(
            name="作品",
            storyLengthProfile="long_serial",
            targetTotalWordCount=345_678,
        ),
    )
    assert repository.creation is not None
    assert repository.creation.target_total_word_count == 345_678


@pytest.mark.asyncio
async def test_blank_optional_inputs_are_saved_as_null() -> None:
    repository = RecordingNovelRepository()
    service = NovelService(repository)  # type: ignore[arg-type]
    await service.create_novel(
        "user-1",
        CreateNovelRequest(
            name="作品",
            summary="  ",
            storyLengthProfile="short_medium",
            genre="  ",
            firstChapterGoal="  ",
        ),
    )
    assert repository.creation is not None
    assert repository.creation.summary is None
    assert repository.creation.genre is None
    assert repository.creation.story_progress is None
    assert repository.creation.notes is None


@pytest.mark.asyncio
async def test_blank_novel_name_is_rejected_after_normalization() -> None:
    service = NovelService(RecordingNovelRepository())  # type: ignore[arg-type]
    with pytest.raises(ApiError, match="名称不能为空") as caught:
        await service.create_novel(
            "user-1",
            CreateNovelRequest(name="   ", storyLengthProfile="short_medium"),
        )
    assert caught.value.status_code == 422


class TransactionSession:
    def __init__(self, *, fail_on_flush: int | None = None) -> None:
        self.added: list[object] = []
        self.flushes = 0
        self.committed = False
        self.rolled_back = False
        self.fail_on_flush = fail_on_flush

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback

    @asynccontextmanager
    async def begin(self):
        try:
            yield
        except Exception:
            self.rolled_back = True
            raise
        else:
            self.committed = True

    def add(self, value: object) -> None:
        self.added.append(value)

    def add_all(self, values: list[object]) -> None:
        self.added.extend(values)

    async def flush(self) -> None:
        self.flushes += 1
        if self.fail_on_flush == self.flushes:
            raise RuntimeError("模拟事务失败")
        for value in self.added:
            typed_value = cast(Any, value)
            if typed_value.id is None:
                typed_value.id = f"id-{type(value).__name__}"


def complete_creation() -> ServiceNovelCreation:
    return ServiceNovelCreation(
        user_id="user-1",
        name="作品",
        summary=None,
        story_progress=None,
        story_length_profile="short_medium",
        target_total_word_count=80_000,
        genre=None,
        core_selling_point=None,
        reader_promise=None,
        notes=None,
        first_chapter_title="第一章",
        first_chapter_order=1,
        outline_content="",
        current_stage="开篇",
        current_goal=None,
    )


@pytest.mark.asyncio
async def test_repository_creates_five_initial_records_in_one_transaction() -> None:
    from inkforge_core.novels.repository import NovelRepository

    session = TransactionSession()
    repository = NovelRepository(lambda: session)  # type: ignore[arg-type]
    result = await repository.create_novel(complete_creation())

    assert session.committed is True
    assert session.rolled_back is False
    assert [type(value).__name__ for value in session.added] == [
        "Novel",
        "Chapter",
        "Outline",
        "PlotProgress",
        "WritingBible",
    ]
    chapter = cast(Any, session.added[1])
    assert chapter.title == "第一章"
    assert chapter.order == 1
    novel = cast(Any, session.added[0])
    assert result == {
        "novelId": novel.id,
        "chapterId": chapter.id,
    }
    assert str(result["novelId"]).startswith("c")
    assert str(result["chapterId"]).startswith("c")


@pytest.mark.asyncio
async def test_repository_rolls_back_all_initial_records_on_failure() -> None:
    from inkforge_core.novels.repository import NovelRepository

    session = TransactionSession(fail_on_flush=2)
    repository = NovelRepository(lambda: session)  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="模拟事务失败"):
        await repository.create_novel(complete_creation())

    assert session.committed is False
    assert session.rolled_back is True


class ScalarRows:
    def __init__(self, values: list[object]) -> None:
        self._values = values

    def all(self) -> list[object]:
        return self._values


class WorkspaceSession:
    def __init__(
        self,
        chapters: list[object],
        reference_rows: list[tuple[object, object | None]] | None = None,
    ) -> None:
        self.chapters = chapters
        self.reference_rows = reference_rows or []
        self.query_count = 0

    async def scalars(self, statement):
        from inkforge_core.db.models import Chapter

        self.query_count += 1
        entity = statement.column_descriptions[0].get("entity")
        return ScalarRows(self.chapters if entity is Chapter else [])

    async def execute(self, statement):
        del statement
        self.query_count += 1
        return ScalarRows(self.reference_rows)

    async def scalar(self, statement):
        del statement
        self.query_count += 1
        return None

    async def get(self, model, identity):
        del model, identity
        self.query_count += 1
        return None


def workspace_novel():
    from datetime import UTC, datetime

    from inkforge_core.db.models import Novel

    now = datetime(2026, 7, 11, tzinfo=UTC)
    return Novel(
        id="novel-1",
        userId="user-1",
        name="作品",
        summary=None,
        storyProgress=None,
        appliedStyleId=None,
        createdAt=now,
        updatedAt=now,
    )


def workspace_chapters(count: int, content: str = "正文") -> list[object]:
    from datetime import UTC, datetime

    from inkforge_core.db.models import Chapter

    now = datetime(2026, 7, 11, tzinfo=UTC)
    return [
        Chapter(
            id=f"chapter-{index}",
            novelId="novel-1",
            title=f"第 {index} 章",
            content=content,
            order=index,
            status="drafting",
            completedAt=None,
            createdAt=now,
            updatedAt=now,
        )
        for index in range(1, count + 1)
    ]


@pytest.mark.asyncio
async def test_workspace_query_count_does_not_grow_with_chapter_count() -> None:
    from inkforge_core.novels.repository import NovelRepository

    repository = NovelRepository(lambda: None)  # type: ignore[arg-type]
    small = WorkspaceSession(workspace_chapters(1))
    large = WorkspaceSession(workspace_chapters(100))
    await repository._load_workspace(small, workspace_novel(), None)
    await repository._load_workspace(large, workspace_novel(), None)
    assert small.query_count == large.query_count


@pytest.mark.asyncio
async def test_workspace_preserves_long_chapter_content_and_all_chapters() -> None:
    from inkforge_core.novels.repository import NovelRepository

    long_content = "首行\n  中间\n末行" * 50_000
    repository = NovelRepository(lambda: None)  # type: ignore[arg-type]
    session = WorkspaceSession(workspace_chapters(25, long_content))
    workspace = await repository._load_workspace(session, workspace_novel(), "chapter-7")
    assert len(workspace["chapters"]) == 25
    assert workspace["chapters"][7 - 1]["content"] == long_content
    assert workspace["currentChapterId"] == "chapter-7"


@pytest.mark.asyncio
async def test_workspace_current_chapter_fallback_is_last_drafting_then_last() -> None:
    from inkforge_core.novels.repository import NovelRepository

    repository = NovelRepository(lambda: None)  # type: ignore[arg-type]
    chapters = workspace_chapters(3)
    chapters[2].status = "review"  # type: ignore[attr-defined]
    workspace = await repository._load_workspace(
        WorkspaceSession(chapters), workspace_novel(), "missing"
    )
    assert workspace["currentChapterId"] == "chapter-2"

    for chapter in chapters:
        chapter.status = "completed"  # type: ignore[attr-defined]
    workspace = await repository._load_workspace(
        WorkspaceSession(chapters), workspace_novel(), None
    )
    assert workspace["currentChapterId"] == "chapter-3"


def test_workspace_openapi_lists_complete_top_level_fields_without_user_id() -> None:
    schema = create_app(testing=True).openapi()
    components = schema["components"]["schemas"]
    properties = components["WorkspaceResponse"]["properties"]
    assert set(properties) == {
        "novel",
        "chapters",
        "currentChapterId",
        "characters",
        "items",
        "locations",
        "factions",
        "glossaries",
        "storyBackground",
        "worldSetting",
        "writingBible",
        "outline",
        "outlineNodes",
        "plotProgress",
        "references",
        "styles",
    }
    assert "userId" not in str(components["WorkspaceResponse"])
    assert "userId" not in str(components["WorkspaceNovel"])


def test_openapi_publishes_exact_style_and_reference_types() -> None:
    schemas = create_app(testing=True).openapi()["components"]["schemas"]
    style_ref = schemas["StyleSummary"]["properties"]["sourceType"]["$ref"]
    reference_ref = schemas["ReferenceDto"]["properties"]["type"]["$ref"]
    assert schemas[style_ref.rsplit("/", 1)[-1]]["enum"] == ["manual", "agent"]
    assert schemas[reference_ref.rsplit("/", 1)[-1]]["enum"] == [
        "note",
        "web",
        "book",
        "image",
        "custom",
    ]


@pytest.mark.parametrize(
    ("model_name", "body"),
    [
        (
            "StyleSummary",
            {"id": "style-1", "name": "文风", "portraitMarkdown": None, "sourceType": "upload"},
        ),
        (
            "ReferenceDto",
            {
                "id": "reference-1",
                "title": "资料",
                "type": "pdf",
                "content": "内容",
                "sourceUrl": None,
                "createdAt": "2026-07-11T00:00:00Z",
                "updatedAt": "2026-07-11T00:00:00Z",
            },
        ),
    ],
)
def test_style_and_reference_models_reject_unknown_enum_values(
    model_name: str, body: dict[str, object]
) -> None:
    from datetime import UTC, datetime

    from inkforge_core.novels import schemas

    if model_name == "ReferenceDto":
        body["createdAt"] = datetime(2026, 7, 11, tzinfo=UTC)
        body["updatedAt"] = datetime(2026, 7, 11, tzinfo=UTC)
    model = getattr(schemas, model_name)
    with pytest.raises(ValidationError):
        model.model_validate(body)


def test_public_datetime_serializes_as_utc_z() -> None:
    from datetime import UTC, datetime

    from inkforge_core.novels.schemas import NovelResponse

    response = NovelResponse(
        id="novel-1",
        name="作品",
        summary=None,
        storyProgress=None,
        appliedStyleId=None,
        createdAt=datetime(2026, 7, 11, tzinfo=UTC),
        updatedAt=datetime(2026, 7, 11, tzinfo=UTC),
    )
    assert '"createdAt":"2026-07-11T00:00:00Z"' in response.model_dump_json()


def test_task7_source_contains_no_database_definition_or_migration_call() -> None:
    from pathlib import Path

    root = Path(__file__).parents[2] / "src" / "inkforge_core"
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for domain in ("novels", "chapters", "quality")
        for path in (root / domain).glob("*.py")
    ).lower()
    for forbidden in ("create_all(", "drop_all(", "alembic", "create table", "alter table"):
        assert forbidden not in source


@pytest.mark.asyncio
async def test_dashboard_uses_stable_order_and_ordered_chapter_projection() -> None:
    from datetime import UTC, datetime

    from inkforge_core.db.models import Chapter, Novel, WritingStyle
    from inkforge_core.novels.repository import NovelRepository

    now = datetime(2026, 7, 11, tzinfo=UTC)
    novel = Novel(
        id="novel-1",
        userId="user-1",
        name="作品",
        summary=None,
        updatedAt=now,
        createdAt=now,
    )
    chapters = workspace_chapters(3)

    class Session:
        def __init__(self) -> None:
            self.statements: list[str] = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback) -> None:
            del exc_type, exc, traceback

        async def scalars(self, statement):
            self.statements.append(str(statement))
            entity = statement.column_descriptions[0].get("entity")
            values = [novel] if entity is Novel else chapters if entity is Chapter else []
            assert entity in {Novel, Chapter, WritingStyle}
            return ScalarRows(values)

    session = Session()
    response = await NovelRepository(lambda: session).list_dashboard("user-1")  # type: ignore[arg-type]
    assert [chapter.id for chapter in response.novels[0].chapters] == [
        "chapter-1",
        "chapter-2",
        "chapter-3",
    ]
    assert '"Novel"."updatedAt" DESC' in session.statements[0]
    assert '"Novel".id ASC' in session.statements[0]
    assert '"Chapter"."order" ASC' in session.statements[1]
    assert '"Chapter".id ASC' in session.statements[1]


@pytest.mark.asyncio
async def test_workspace_sets_read_only_repeatable_read_before_authorization_query() -> None:
    from inkforge_core.db.models import Novel
    from inkforge_core.novels.repository import NovelRepository

    novel = workspace_novel()

    class Dialect:
        name = "postgresql"

    class Bind:
        dialect = Dialect()

    class Session:
        def __init__(self) -> None:
            self.operations: list[str] = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback) -> None:
            del exc_type, exc, traceback

        @asynccontextmanager
        async def begin(self):
            yield

        def get_bind(self):
            return Bind()

        async def execute(self, statement):
            self.operations.append(str(statement))
            return ScalarRows([])

        async def scalar(self, statement):
            self.operations.append(f"查询:{statement}")
            entity = statement.column_descriptions[0].get("entity")
            return novel if entity is Novel else None

        async def scalars(self, statement):
            self.operations.append(f"查询:{statement}")
            return ScalarRows([])

        async def get(self, model, identity):
            del model, identity
            self.operations.append("查询:get")
            return None

    session = Session()
    response = await NovelRepository(lambda: session).get_workspace(  # type: ignore[arg-type]
        "novel-1", "user-1", None
    )
    assert response.novel.id == "novel-1"
    assert session.operations[0] == ("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
    assert session.operations[1].startswith("查询:")


@pytest.mark.asyncio
async def test_workspace_returns_rag_status_with_single_reference_join() -> None:
    from inkforge_core.db.models import RagDocument, ReferenceMaterial
    from inkforge_core.novels.repository import NovelRepository

    reference = ReferenceMaterial(
        id="reference-1",
        novelId="novel-1",
        title="资料",
        type="note",
        content="正文",
        sourceUrl=None,
    )
    document = RagDocument(
        id="document-1",
        novelId="novel-1",
        sourceType="reference_material",
        sourceId="reference-1",
        title="资料",
        contentHash="a" * 64,
        status="failed",
        errorMessage="索引失败",
    )
    session = WorkspaceSession([], [(reference, document)])
    workspace = await NovelRepository(lambda: None)._load_workspace(  # type: ignore[arg-type]
        session, workspace_novel(), None
    )
    item = workspace["references"][0]
    assert item["id"] == "reference-1"
    assert item["ragStatus"] == "failed"
    assert item["contentHash"] == "a" * 64
    assert item["errorMessage"] == "索引生成失败"
