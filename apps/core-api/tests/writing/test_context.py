from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from inkforge_contracts.jobs import WritingJobPayload
from inkforge_core.db.models import (
    Chapter,
    Foreshadowing,
    Novel,
    ReviewArtifact,
    ReviewArtifactEvaluation,
    ReviewArtifactRevision,
    StoryBackground,
    WorldSetting,
    WritingBible,
    WritingRunCommand,
    WritingStyle,
    WritingTask,
)
from inkforge_core.errors import ApiError
from inkforge_core.writing.context import (
    ChapterGroupSnapshot,
    WritingContextRepository,
    WritingContextService,
    _build_short_story_context,
    _command_revision_request,
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


def test_short_story_context_keeps_authority_priority_and_only_six_recent_messages() -> None:
    outline = {
        "kind": "outline_draft",
        "storyLengthProfile": "short_medium",
        "anchors": {"mustKeep": ["结局"], "confirmed": [], "avoid": []},
        "content": "完整大纲",
    }
    recent = [
        {"role": "user", "content": f"历史-{index}"}
        for index in range(10)
    ]

    result = _build_short_story_context(
        direct_edit={"sections": [{"id": "section-2", "events": "直接编辑"}]},
        revision_request="只修改第二节，不要改结局",
        outline=outline,
        inspiration="原始灵感",
        recent_conversation=recent,
    )

    assert list(result) == [
        "revisionRequest",
        "referencedVersions",
        "directEdit",
        "anchors",
        "currentOutline",
        "originalInspiration",
        "recentConversation",
    ]
    assert result["anchors"] == outline["anchors"]
    assert result["currentOutline"] is outline
    assert [item["content"] for item in result["recentConversation"]] == [
        "历史-4",
        "历史-5",
        "历史-6",
        "历史-7",
        "历史-8",
        "历史-9",
    ]


def test_initial_short_outline_start_does_not_turn_start_message_into_revision_request() -> None:
    payload = WritingJobPayload.model_validate(
        {
            "version": 1,
            "resume": False,
            "chapterId": "chapter-1",
            "writingSessionId": None,
            "resumeInput": None,
            "workflowKind": "short_medium",
            "operation": "develop_short_outline",
            "targetTotalWordCount": 6000,
            "source": {
                "kind": "short_outline_inspiration",
                "originalInspiration": "原始灵感",
            },
            "startRequest": {"userMessage": "创建并生成大纲"},
        }
    )

    assert _command_revision_request(payload) is None


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
    def __init__(
        self,
        responses: list[object | None],
        *,
        scalar_lists: list[list[object]] | None = None,
        execute_rows: list[tuple[object, ...] | None] | None = None,
    ) -> None:
        self._responses = iter(responses)
        self._scalar_lists = iter(scalar_lists or [])
        self._execute_rows = iter(execute_rows or [])

    async def scalar(self, statement: object) -> object | None:
        del statement
        return next(self._responses)

    async def scalars(self, statement: object) -> FakeScalarsResult:
        del statement
        return FakeScalarsResult(next(self._scalar_lists))

    async def execute(self, statement: object):
        del statement
        row = next(self._execute_rows)

        class Result:
            def one_or_none(self) -> tuple[object, ...] | None:
                return row

        return Result()


class PlanningRowResult:
    def __init__(self, row: tuple[object, ...]) -> None:
        self.row = row

    def one_or_none(self) -> tuple[object, ...]:
        return self.row


class ShortPlanningSession:
    def __init__(
        self,
        row: tuple[object, ...],
        scalar_responses: list[object | None],
        scalar_list_responses: list[object],
    ) -> None:
        self.row = row
        self._scalar_responses = iter(scalar_responses)
        self._scalar_list_responses = scalar_list_responses
        self.execute_count = 0

    async def __aenter__(self) -> ShortPlanningSession:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback

    async def execute(self, statement: object) -> PlanningRowResult:
        del statement
        self.execute_count += 1
        if self.execute_count > 1:
            raise AssertionError("中短篇上下文不应执行长篇章节组或 Beat Plan 查询")
        return PlanningRowResult(self.row)

    async def scalar(self, statement: object) -> object | None:
        del statement
        return next(self._scalar_responses)

    async def scalars(self, statement: object) -> FakeScalarsResult:
        del statement
        return FakeScalarsResult(self._scalar_list_responses)


class ShortPlanningFactory:
    def __init__(self, session: ShortPlanningSession) -> None:
        self.session = session

    def __call__(self) -> ShortPlanningSession:
        return self.session


@pytest.mark.asyncio
async def test_short_context_bypasses_long_planning_and_prioritizes_direct_edit() -> None:
    task = WritingTask(
        id="task-1",
        novelId="novel-1",
        chapterId="chapter-1",
        writingSessionId=None,
        phase="active",
        targetWordCount=80000,
        selectedAgents="剧情",
        conversationHistory="[]",
    )
    chapter = Chapter(
        id="chapter-1", novelId="novel-1", title="旧项目正文名", order=1
    )
    novel = Novel(id="novel-1", userId="user-1", name="测试", summary="原始灵感")
    bible = WritingBible(
        id="bible-1",
        novelId="novel-1",
        storyLengthProfile="short_medium",
        targetTotalWordCount=None,
    )
    command = WritingRunCommand(
        id="command-1",
        taskId="task-1",
        kind="resume",
        status="submitted",
        idempotencyKey="user-1:request-1",
        payloadJson=json.dumps(
            {
                "version": 1,
                "resume": True,
                "chapterId": "chapter-1",
                "writingSessionId": None,
                "resumeInput": {"userMessage": "只修改第二节"},
                "workflowKind": "short_medium",
                "operation": "develop_short_outline",
                "targetTotalWordCount": None,
                "source": {
                    "kind": "short_outline_inspiration",
                    "originalInspiration": "原始灵感",
                },
            },
            ensure_ascii=False,
        ),
    )
    outline = ReviewArtifact(
        id="artifact-1",
        novelId="novel-1",
        chapterId="chapter-1",
        kind="outline_draft",
        status="awaiting_user",
        revision=2,
        payloadJson=json.dumps(
            {
                "kind": "outline_draft",
                "storyLengthProfile": "short_medium",
                "originalInspiration": "原始灵感",
                "corePremise": "核心前提",
                "anchors": {"mustKeep": ["结局"], "confirmed": [], "avoid": []},
                "sections": [
                    {"id": "section-1", "title": "第一节", "events": "事件"}
                ],
                "content": "由契约重建",
                "changeSummary": "直接编辑",
                "anchorChanges": [],
            },
            ensure_ascii=False,
        ),
        diffJson=json.dumps({"type": "user_edit", "changed": ["section-1"]}),
    )
    session = ShortPlanningSession(
        (task, chapter, novel, bible),
        [command, 1],
        [outline],
    )

    result = await WritingContextRepository(ShortPlanningFactory(session)).get_planning_context(  # type: ignore[arg-type]
        "user-1", "task-1"
    )

    short = result["shortStoryContext"]
    assert short["directEdit"]["revision"] == 2
    assert short["directEdit"]["diff"]["type"] == "user_edit"
    assert short["revisionRequest"] == "只修改第二节"
    assert short["originalInspiration"] == "原始灵感"
    assert result["chapterGroup"] is None
    assert result["approvedBeatPlan"] is None
    assert result["outlinePath"] == []
    assert result["targetWordCount"] is None
    assert result["targetTotalWordCount"] is None
    assert result["versionReferences"] == []


@pytest.mark.asyncio
async def test_short_outline_context_ignores_legacy_untyped_artifact() -> None:
    legacy = ReviewArtifact(
        id="legacy-outline",
        novelId="novel-1",
        chapterId="chapter-1",
        kind="outline_draft",
        status="awaiting_user",
        revision=1,
        payloadJson=json.dumps(
            {"kind": "outline_draft", "content": "旧流程自由文本大纲"},
            ensure_ascii=False,
        ),
    )

    outline, direct_edit = await WritingContextRepository(
        cast(Any, None)
    )._current_short_outline(
        cast(AsyncSession, FakeScalarsSession([legacy])),
        "novel-1",
    )

    assert outline is None
    assert direct_edit is None


@pytest.mark.asyncio
async def test_short_outline_context_skips_newer_legacy_artifact() -> None:
    legacy = ReviewArtifact(
        id="legacy-outline",
        novelId="novel-1",
        chapterId="chapter-1",
        kind="outline_draft",
        status="awaiting_user",
        revision=1,
        payloadJson=json.dumps(
            {"kind": "outline_draft", "content": "迟到的旧流程大纲"},
            ensure_ascii=False,
        ),
    )
    typed = ReviewArtifact(
        id="typed-outline",
        novelId="novel-1",
        chapterId="chapter-1",
        kind="outline_draft",
        status="awaiting_user",
        revision=3,
        payloadJson=json.dumps(
            {
                "kind": "outline_draft",
                "storyLengthProfile": "short_medium",
                "originalInspiration": "原始灵感",
                "corePremise": "核心前提",
                "anchors": {"mustKeep": [], "confirmed": [], "avoid": []},
                "sections": [
                    {"id": "section-1", "title": "第一节", "events": "事件"}
                ],
                "content": "权威完整大纲",
                "changeSummary": "修改摘要",
                "anchorChanges": [],
            },
            ensure_ascii=False,
        ),
    )

    outline, direct_edit = await WritingContextRepository(
        cast(Any, None)
    )._current_short_outline(
        cast(AsyncSession, FakeScalarsSession([legacy, typed])),
        "novel-1",
    )

    assert outline is not None
    assert outline["corePremise"] == "核心前提"
    assert outline["sections"][0]["id"] == "section-1"
    assert direct_edit is None


@pytest.mark.asyncio
async def test_long_context_identity_does_not_compare_chapter_and_total_word_targets() -> None:
    repository = WritingContextRepository(cast(Any, None))
    task = WritingTask(
        id="task-1",
        novelId="novel-1",
        chapterId="chapter-1",
        phase="active",
        targetWordCount=4000,
        selectedAgents="剧情",
        conversationHistory="[]",
    )
    chapter = Chapter(id="chapter-1", novelId="novel-1", title="第一章", order=1)
    novel = Novel(id="novel-1", userId="user-1", name="长篇", summary="")
    bible = WritingBible(
        id="bible-1",
        novelId="novel-1",
        storyLengthProfile="long_serial",
        targetTotalWordCount=1_000_000,
    )
    payload = WritingJobPayload.model_validate(
        {
            "version": 1,
            "resume": False,
            "chapterId": "chapter-1",
            "writingSessionId": None,
            "resumeInput": None,
            "workflowKind": "long_serial",
            "operation": None,
            "targetTotalWordCount": 1_000_000,
            "source": None,
        }
    )

    await repository._validate_command_identity(
        cast(AsyncSession, FakeScalarSession([])),
        task=task,
        chapter=chapter,
        novel=novel,
        bible=bible,
        payload=payload,
    )


@pytest.mark.asyncio
async def test_short_story_source_must_still_reference_an_existing_exact_outline() -> None:
    repository = WritingContextRepository(cast(Any, None))
    task = WritingTask(
        id="task-1",
        novelId="novel-1",
        chapterId="chapter-1",
        phase="active",
        targetWordCount=6000,
        selectedAgents="剧情",
        conversationHistory="[]",
    )
    chapter = Chapter(id="chapter-1", novelId="novel-1", title="正文", order=1)
    novel = Novel(id="novel-1", userId="user-1", name="中短篇", summary="灵感")
    bible = WritingBible(
        id="bible-1",
        novelId="novel-1",
        storyLengthProfile="short_medium",
        targetTotalWordCount=6000,
    )
    payload = WritingJobPayload.model_validate(
        {
            "version": 1,
            "resume": False,
            "chapterId": "chapter-1",
            "writingSessionId": None,
            "resumeInput": None,
            "workflowKind": "short_medium",
            "operation": "write_short_story",
            "targetTotalWordCount": 6000,
            "source": {
                "kind": "approved_short_outline",
                "outlineArtifactId": "outline-old",
                "outlineRevision": 1,
                "outlineHash": "0" * 64,
            },
        }
    )
    with pytest.raises(ApiError) as exc_info:
        await repository._validate_command_identity(
            cast(
                AsyncSession,
                FakeScalarSession([1, None], execute_rows=[None]),
            ),
            task=task,
            chapter=chapter,
            novel=novel,
            bible=bible,
            payload=payload,
        )

    assert exc_info.value.code == "WRITING_CONTEXT_IDENTITY_MISMATCH"


@pytest.mark.asyncio
async def test_short_story_manuscript_context_contains_only_authoritative_inputs() -> None:
    repository = WritingContextRepository(cast(Any, None))
    task = WritingTask(
        id="task-1",
        novelId="novel-1",
        chapterId="chapter-1",
        targetWordCount=6000,
        selectedAgents="写作,编辑,校验",
    )
    chapter = Chapter(
        id="chapter-1", novelId="novel-1", title="正文", order=1, content="旧正文"
    )
    novel = Novel(
        id="novel-1",
        userId="user-1",
        name="中短篇",
        summary="原始灵感",
        appliedStyleId="style-1",
    )
    bible = WritingBible(
        id="bible-1",
        novelId="novel-1",
        storyLengthProfile="short_medium",
        targetTotalWordCount=6000,
        genre="悬疑",
        taboo="不要梦境解释",
    )
    outline_payload = {
        "kind": "outline_draft",
        "storyLengthProfile": "short_medium",
        "originalInspiration": "原始灵感",
        "corePremise": "主人公必须查清讣告来源。",
        "anchors": {"mustKeep": ["未来讣告"], "confirmed": [], "avoid": []},
        "sections": [{"id": "section-1", "title": "来信", "events": "收到讣告。"}],
        "content": "由契约重建",
        "changeSummary": "已批准",
        "anchorChanges": [],
    }
    from inkforge_contracts import ShortStoryOutlineDraft, canonical_short_outline_hash

    outline = ShortStoryOutlineDraft.model_validate(outline_payload)
    artifact = ReviewArtifact(
        id="outline-1",
        novelId="novel-1",
        chapterId="chapter-1",
        kind="outline_draft",
        status="applied",
        revision=2,
        payloadJson=outline.model_dump_json(),
    )
    outline_revision = ReviewArtifactRevision(
        artifactId="outline-1",
        revision=2,
        payloadJson=outline.model_dump_json(),
    )
    background = StoryBackground(novelId="novel-1", content="故事背景")
    world = WorldSetting(novelId="novel-1", content="世界规则")
    style = WritingStyle(
        id="style-1",
        userId="user-1",
        name="冷峻",
        portraitMarkdown="文风画像",
        sourceType="manual",
    )
    payload = WritingJobPayload.model_validate(
        {
            "version": 1,
            "resume": False,
            "chapterId": "chapter-1",
            "writingSessionId": None,
            "resumeInput": None,
            "workflowKind": "short_medium",
            "operation": "write_short_story",
            "targetTotalWordCount": 6000,
            "source": {
                "kind": "approved_short_outline",
                "outlineArtifactId": "outline-1",
                "outlineRevision": 2,
                "outlineHash": canonical_short_outline_hash(outline),
            },
        }
    )

    result = await repository._short_story_manuscript_context(
        cast(
            AsyncSession,
            FakeScalarSession(
                [background, world, style],
                execute_rows=[(outline_revision, artifact)],
            ),
        ),
        task=task,
        chapter=chapter,
        novel=novel,
        bible=bible,
        payload=payload,
        referenced_versions=[],
    )

    assert list(result) == [
        "referencedVersions",
        "approvedOutline",
        "anchors",
        "originalInspiration",
        "targetTotalWordCount",
        "targetChapter",
        "writingBible",
        "storyBackground",
        "worldSetting",
        "appliedStyle",
    ]
    assert result["approvedOutline"]["artifactId"] == "outline-1"
    assert result["targetChapter"]["baseContentHash"]
    assert result["storyBackground"] == "故事背景"
    assert result["appliedStyle"]["portraitMarkdown"] == "文风画像"


class ShortRunArtifactSession:
    def __init__(
        self,
        artifact: ReviewArtifact,
        evaluations: list[ReviewArtifactEvaluation],
    ) -> None:
        self.artifact = artifact
        self.evaluations = evaluations

    async def scalar(self, statement: object) -> object:
        del statement
        return self.artifact

    async def scalars(self, statement: object):
        del statement

        class Result:
            def __init__(self, values: list[ReviewArtifactEvaluation]) -> None:
                self.values = values

            def all(self) -> list[ReviewArtifactEvaluation]:
                return self.values

        return Result(self.evaluations)


@pytest.mark.asyncio
async def test_short_story_run_artifact_recovers_without_snapshot_active_id() -> None:
    repository = WritingContextRepository(cast(Any, None))
    content = "甲" * 6000
    artifact = ReviewArtifact(
        id="draft-1",
        taskId="task-1",
        novelId="novel-1",
        chapterId="chapter-1",
        artifactKey="short-story-draft",
        kind="chapter_draft",
        status="under_review",
        revision=1,
        payloadJson=json.dumps(
            {
                "kind": "chapter_draft",
                "storyLengthProfile": "short_medium",
                "content": content,
                "metadata": {
                    "sourceOutlineArtifactId": "outline-1",
                    "sourceOutlineRevision": 1,
                    "sourceOutlineHash": "a" * 64,
                    "targetWordCount": 6000,
                    "actualWordCount": 6000,
                    "targetChapterId": "chapter-1",
                    "baseChapterHash": "b" * 64,
                    "generationCommandId": "command-1",
                    "automaticRewriteCount": 0,
                    "generationReason": "user_request",
                },
            },
            ensure_ascii=False,
        ),
    )
    evaluation = ReviewArtifactEvaluation(
        id="evaluation-1",
        artifactId="draft-1",
        revision=1,
        evaluatorAgent="编辑",
        verdict="pass",
        summary="编辑通过",
        createdAt=datetime.now(UTC),
    )
    task = WritingTask(
        id="task-1",
        novelId="novel-1",
        chapterId="chapter-1",
        graphStateJson=None,
    )

    result = await repository._short_story_run_artifact(
        cast(AsyncSession, ShortRunArtifactSession(artifact, [evaluation])), task
    )

    assert result is not None
    assert result["id"] == "draft-1"
    assert result["payload"]["content"] == content
    assert result["evaluations"][0]["evaluatorAgent"] == "编辑"


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


def _hydration_artifact(**overrides: Any) -> ReviewArtifact:
    values: dict[str, Any] = {
        "id": "artifact-1",
        "taskId": "task-1",
        "novelId": "novel-1",
        "chapterId": "chapter-1",
        "workflowRunId": "workflow-1",
        "artifactKey": "authority-key",
        "kind": "chapter_draft",
        "status": "under_review",
        "title": "正文草案",
        "summary": "首版",
        "payloadJson": json.dumps({"kind": "chapter_draft", "content": "完整正文"}),
        "diffJson": json.dumps({"changed": True}),
        "createdByAgent": "写作",
        "reviewerAgent": "校验",
        "revision": 2,
    }
    values.update(overrides)
    return ReviewArtifact(**values)


@pytest.mark.asyncio
async def test_context_returns_complete_hydratable_active_artifact() -> None:
    repository = WritingContextRepository(cast(Any, None))
    artifact = _hydration_artifact()
    session = cast(AsyncSession, FakeScalarSession([artifact]))

    active = await repository._active_artifact(session, _task_with_active_artifact())

    assert active is not None
    assert set(active) == {
        "id",
        "taskId",
        "novelId",
        "chapterId",
        "workflowRunId",
        "artifactKey",
        "kind",
        "status",
        "title",
        "summary",
        "payload",
        "diff",
        "createdByAgent",
        "reviewerAgent",
        "revision",
    }
    assert active["payload"] == {"kind": "chapter_draft", "content": "完整正文"}
    assert active["diff"] == {"changed": True}
    assert "runId" not in active
    assert "jobId" not in active


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "artifact",
    [
        _hydration_artifact(payloadJson="{"),
        _hydration_artifact(payloadJson=json.dumps(["不是对象"])),
        _hydration_artifact(payloadJson=json.dumps({"kind": "outline_draft"})),
        _hydration_artifact(diffJson="{"),
    ],
)
async def test_context_rejects_invalid_active_artifact_json(
    artifact: ReviewArtifact,
) -> None:
    repository = WritingContextRepository(cast(Any, None))
    session = cast(AsyncSession, FakeScalarSession([artifact]))

    with pytest.raises(ApiError) as caught:
        await repository._active_artifact(session, _task_with_active_artifact())

    assert caught.value.code == "ARTIFACT_PAYLOAD_INVALID"


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
