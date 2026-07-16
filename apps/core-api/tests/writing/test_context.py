import json
from typing import Any, cast

import pytest
from inkforge_core.db.models import Foreshadowing, ReviewArtifact, WritingRunCommand, WritingTask
from inkforge_core.errors import ApiError
from inkforge_core.writing.context import (
    ChapterGroupSnapshot,
    WritingContextRepository,
    WritingContextService,
    _split_current_user_message,
    select_unique_chapter_group,
)
from sqlalchemy.ext.asyncio import AsyncSession


def test_chapter_group_allows_missing_but_rejects_ambiguous_mapping() -> None:
    matching = ChapterGroupSnapshot("group-1", "第一组", 1, 5, "完整章节组内容")
    assert select_unique_chapter_group(3, [matching]) == matching
    assert select_unique_chapter_group(3, []) is None
    with pytest.raises(ApiError, match="没有唯一对应的章节组"):
        select_unique_chapter_group(
            3,
            [matching, ChapterGroupSnapshot("group-2", "重叠组", 3, 6, "冲突")],
        )


def test_split_current_user_preserves_older_identical_message() -> None:
    history, current = _split_current_user_message(
        [
            {"role": "user", "content": "再写一次"},
            {"role": "agent", "content": "上次回复"},
            {"role": "user", "content": "再写一次"},
        ]
    )

    assert current == "再写一次"
    assert history == [
        {"role": "user", "content": "再写一次"},
        {"role": "agent", "content": "上次回复"},
    ]


def test_split_current_user_ignores_non_string_user_records() -> None:
    history, current = _split_current_user_message(
        [
            {"role": "user", "content": "合法请求"},
            {"role": "user", "content": None},
        ]
    )

    assert current == "合法请求"
    assert history == [{"role": "user", "content": None}]


class FakePlanningRepository:
    async def get_planning_context(self, user_id: str, task_id: str):
        assert (user_id, task_id) == ("user-1", "task-1")
        return {
            "taskId": task_id,
            "novelId": "novel-1",
            "chapterId": "chapter-1",
            "chapterOrder": 3,
            "chapterGoal": {"narrativeGoal": "推进冲突"},
            "approvedBeatPlan": {"chapterGoal": "按计划推进", "sceneBeats": []},
            "chapterGroup": {"id": "group-1", "content": "完整章节组内容"},
            "outlinePath": [{"kind": "stage", "title": "第一卷"}],
            "foreshadowingSummaries": [
                {
                    "id": "foreshadowing-1",
                    "name": "断裂墨印",
                    "status": "active",
                    "plantedAt": "第一章",
                    "expectedPayoff": "第五章",
                    "payoffAt": None,
                }
            ],
            "activeArtifact": None,
        }


class FakeWorkspaceRepository:
    async def get_workspace(self, novel_id: str, user_id: str, chapter_id: str | None = None):
        assert (novel_id, user_id) == ("novel-1", "user-1")
        assert chapter_id == "chapter-1"
        return {"novel": {"id": novel_id, "name": "作品"}, "characters": []}


@pytest.mark.asyncio
async def test_context_combines_complete_workspace_and_current_planning_scope() -> None:
    context = await WritingContextService(
        FakePlanningRepository(), FakeWorkspaceRepository()
    ).build("user-1", "task-1")

    assert context["workspace"]["novel"]["name"] == "作品"
    assert context["planning"]["approvedBeatPlan"]["chapterGoal"] == "按计划推进"
    assert context["planning"]["chapterGroup"]["content"] == "完整章节组内容"
    assert context["planning"]["foreshadowingSummaries"][0]["name"] == "断裂墨印"


class FakeScalarSession:
    def __init__(self, responses: list[object | None]) -> None:
        self._responses = iter(responses)

    async def scalar(self, statement: object) -> object | None:
        del statement
        return next(self._responses)


class FakeScalarsResult:
    def __init__(self, values: list[object]) -> None:
        self._values = values

    def all(self) -> list[object]:
        return self._values


class FakeScalarsSession:
    def __init__(self, values: list[object]) -> None:
        self.values = values
        self.statement: object | None = None

    async def scalars(self, statement: object) -> FakeScalarsResult:
        self.statement = statement
        return FakeScalarsResult(self.values)


@pytest.mark.asyncio
async def test_foreshadowing_summaries_use_stable_order_and_exclude_detail() -> None:
    repository = WritingContextRepository(cast(Any, None))
    session = FakeScalarsSession(
        [
            Foreshadowing(
                id="foreshadowing-1",
                novelId="novel-1",
                name="断裂墨印",
                status="active",
                plantedAt="第一章",
                expectedPayoff="第五章",
                payoffAt=None,
                plantedContent="种下伏笔的完整正文",
            )
        ]
    )

    result = await repository._foreshadowing_summaries(
        cast(AsyncSession, session), "novel-1"
    )

    assert result == [
        {
            "id": "foreshadowing-1",
            "name": "断裂墨印",
            "status": "active",
            "plantedAt": "第一章",
            "expectedPayoff": "第五章",
            "payoffAt": None,
        }
    ]
    statement = str(session.statement)
    assert 'ORDER BY public."Foreshadowing"."createdAt" ASC' in statement
    assert 'public."Foreshadowing".id ASC' in statement


def _task_with_active_artifact(artifact_id: str = "artifact-1") -> WritingTask:
    return WritingTask(
        id="task-1",
        novelId="novel-1",
        chapterId="chapter-1",
        graphStateJson=json.dumps(
            {
                "taskId": "task-1",
                "userId": "user-1",
                "novelId": "novel-1",
                "chapterId": "chapter-1",
                "targetWordCount": 3000,
                "conversationHistory": [],
                "activeArtifactId": artifact_id,
            }
        ),
    )


def _active_decision_command() -> WritingRunCommand:
    return WritingRunCommand(
        id="command-1",
        taskId="task-1",
        artifactId="artifact-1",
        kind="artifact_decision",
        status="submitted",
        idempotencyKey="user-1:request-1",
        payloadJson="{}",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "artifact",
    [
        ReviewArtifact(
            id="artifact-1",
            taskId="task-1",
            novelId="novel-1",
            status="applied",
        ),
        None,
    ],
)
async def test_context_allows_resolved_artifact_during_active_decision_command(
    artifact: ReviewArtifact | None,
) -> None:
    repository = WritingContextRepository(cast(Any, None))
    session = cast(
        AsyncSession,
        FakeScalarSession([artifact, _active_decision_command()]),
    )

    active_artifact = await repository._active_artifact(
        session,
        _task_with_active_artifact(),
    )

    assert active_artifact is None


@pytest.mark.asyncio
async def test_context_rejects_resolved_artifact_without_active_decision_command() -> None:
    repository = WritingContextRepository(cast(Any, None))
    artifact = ReviewArtifact(
        id="artifact-1",
        taskId="task-1",
        novelId="novel-1",
        status="applied",
    )
    session = cast(AsyncSession, FakeScalarSession([artifact, None]))

    with pytest.raises(ApiError, match="待审核草案与任务不匹配"):
        await repository._active_artifact(session, _task_with_active_artifact())
