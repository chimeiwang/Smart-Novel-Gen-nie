from __future__ import annotations

import hashlib
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from inkforge_core.db.models import Chapter, ChapterQualityCheck, Novel
from inkforge_core.errors import ApiError
from inkforge_core.reviews.apply import FormalArtifactApplier, resolve_apply_target
from inkforge_core.reviews.formal_writes import FormalWriteRepository
from inkforge_core.reviews.repository import _materialize_selection_payload, _selection_diff
from inkforge_core.reviews.service import ReviewService


@dataclass
class Artifact:
    id: str = "artifact-1"
    status: str = "awaiting_user"
    kind: str = "chapter_draft"
    artifact_key: str | None = None
    payload: dict[str, object] | None = None

    def __post_init__(self) -> None:
        if self.payload is None:
            self.payload = {"kind": self.kind, "content": "完整正文"}


class FakeReviewRepository:
    def __init__(self, artifact: Artifact | None = None) -> None:
        self.artifact = artifact or Artifact()
        self.transitions: list[tuple[str, str]] = []
        self.deleted = False

    async def require_artifact(self, user_id: str, artifact_id: str) -> Artifact:
        assert user_id == "user-1"
        assert artifact_id == "artifact-1"
        return self.artifact

    async def prepare_decision(
        self, user_id: str, artifact_id: str, *, expected_revision: int, decision: str
    ) -> Artifact:
        del expected_revision, decision
        return await self.require_artifact(user_id, artifact_id)

    async def transition(self, artifact_id: str, current: str, target: str) -> None:
        assert self.artifact.status == current
        self.transitions.append((current, target))
        self.artifact.status = target

    async def discard(self, user_id: str, artifact_id: str) -> None:
        await self.require_artifact(user_id, artifact_id)
        self.deleted = True


class FakeApplier:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.payload: dict[str, object] | None = None

    async def apply(
        self,
        artifact: Artifact,
        *,
        user_id: str,
        edited_content: str | None,
        selected_update_refs: list[dict[str, object]] | None,
    ) -> int:
        del user_id, edited_content, selected_update_refs
        self.payload = artifact.payload
        if self.fail:
            raise ValueError("正式写入失败")
        return 1


@pytest.mark.asyncio
async def test_approve_transitions_through_applying_to_applied() -> None:
    repository = FakeReviewRepository()
    applier = FakeApplier()
    service = ReviewService(repository, applier)

    result = await service.decide("user-1", "artifact-1", "approve", expected_revision=1)

    assert repository.transitions == [
        ("awaiting_user", "applying"),
        ("applying", "applied"),
    ]
    assert result.savedCount == 1


@pytest.mark.asyncio
async def test_apply_failure_returns_artifact_to_awaiting_user() -> None:
    repository = FakeReviewRepository()
    service = ReviewService(repository, FakeApplier(fail=True))

    with pytest.raises(ApiError) as error:
        await service.decide("user-1", "artifact-1", "approve", expected_revision=1)

    assert error.value.status_code == 409
    assert error.value.code == "ARTIFACT_APPLY_FAILED"
    assert repository.transitions[-1] == ("applying", "awaiting_user")


@pytest.mark.asyncio
async def test_discard_hard_deletes_artifact() -> None:
    repository = FakeReviewRepository()
    result = await ReviewService(repository, FakeApplier()).decide(
        "user-1", "artifact-1", "discard", expected_revision=1
    )

    assert repository.deleted is True
    assert result.deleted is True


@pytest.mark.asyncio
async def test_revision_brief_cannot_be_approved() -> None:
    repository = FakeReviewRepository(Artifact(kind="revision_brief"))

    with pytest.raises(ApiError) as error:
        await ReviewService(repository, FakeApplier()).decide(
            "user-1", "artifact-1", "approve", expected_revision=1
        )

    assert error.value.status_code == 400
    assert repository.transitions == []


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["approve", "revise", "discard"])
async def test_generic_decision_rejects_short_medium_versions(decision: str) -> None:
    repository = FakeReviewRepository(
        Artifact(artifact_key="short-medium:manuscript:chapter-1")
    )

    with pytest.raises(ApiError) as error:
        await ReviewService(repository, FakeApplier()).decide(
            "user-1", "artifact-1", decision, expected_revision=1  # type: ignore[arg-type]
        )

    assert error.value.code == "SHORT_MEDIUM_VERSION_ROUTE_REQUIRED"
    assert repository.transitions == []
    assert repository.deleted is False


class FakeFormalWrites:
    def __init__(self) -> None:
        self.calls = 0
        self.content: str | None = None
        self.beat_plan: dict[str, object] | None = None

    async def apply_outline(self, artifact: object, user_id: str, content: str) -> int:
        del artifact, user_id
        self.calls += 1
        self.content = content
        return 1

    async def apply_chapter(self, artifact: object, user_id: str, content: str) -> int:
        del artifact, user_id
        self.calls += 1
        self.content = content
        return 1

    async def apply_beat_plan(
        self, artifact: object, user_id: str, beat_plan: dict[str, object]
    ) -> int:
        del artifact, user_id
        self.calls += 1
        self.beat_plan = beat_plan
        self.content = str(beat_plan["chapterGoal"])
        return 1

    async def apply_selection(
        self, artifact: object, user_id: str, replacement: str
    ) -> int:
        del artifact, user_id
        self.content = replacement
        return 1


class FakeUpdatesExecutor:
    def __init__(self) -> None:
        self.updates: dict[str, object] | None = None

    async def apply(
        self,
        novel_id: str,
        user_id: str,
        updates: dict[str, object],
        *,
        expected_outline_updated_at: datetime | None = None,
        expected_lore_updated_at: dict[str, datetime | None] | None = None,
    ) -> int:
        del novel_id, user_id
        self.updates = updates
        self.expected_outline_updated_at = expected_outline_updated_at
        self.expected_lore_updated_at = expected_lore_updated_at
        return 1


def _beat_plan_artifact(beat_plan: dict[str, object]) -> Artifact:
    artifact = Artifact(kind="beat_plan", payload={"kind": "beat_plan", "beatPlan": beat_plan})
    artifact.novel_id = "novel-1"
    artifact.chapter_id = "chapter-1"
    return artifact


@pytest.mark.asyncio
async def test_formal_applier_normalizes_production_legacy_scene_fields() -> None:
    beat_plan: dict[str, object] = {
        "title": "第一章计划",
        "chapterGoal": "纪寻潜入栾城。",
        "totalEstimatedWords": 2300,
        "sceneBeats": [
            {
                "order": 7,
                "sceneName": "  城门试探  ",
                "sceneGoal": "  混入入城队伍  ",
                "conflict": "守卫临时加验路引。",
                "characters": "纪寻、栾城守卫，商队领队",
                "foreshadowingReferences": "破损路引上的旧印与第三章失窃案呼应。",
                "estimatedWords": 1000,
                "acceptanceCriteria": "纪寻成功入城但留下疑点。",
            },
            {
                "sceneName": "暗巷接头",
                "sceneGoal": "取得内城地图",
                "conflict": "接头人被跟踪。",
                "characters": "纪寻, 线人",
                "foreshadowingReferences": "无",
                "estimatedWords": 1300,
                "acceptanceCriteria": "地图到手并暴露新的追兵。",
            },
            {
                "sceneName": "城内落脚",
                "sceneGoal": "避开搜查",
                "conflict": "客栈掌柜盘问来历。",
                "foreshadowingReferences": "",
                "estimatedWords": 500,
                "acceptanceCriteria": "纪寻取得临时藏身处。",
            },
        ],
    }
    original = deepcopy(beat_plan)
    writes = FakeFormalWrites()

    await FormalArtifactApplier(writes, FakeUpdatesExecutor()).apply(
        _beat_plan_artifact(beat_plan),
        user_id="user-1",
        edited_content=None,
        selected_update_refs=None,
    )

    assert writes.beat_plan == {
        "title": "第一章计划",
        "chapterGoal": "纪寻潜入栾城。",
        "totalEstimatedWords": 2300,
        "sceneBeats": [
            {
                "order": 7,
                "goal": "城门试探：混入入城队伍",
                "conflict": "守卫临时加验路引。",
                "characters": ["纪寻", "栾城守卫", "商队领队"],
                "foreshadowingRefs": ["破损路引上的旧印与第三章失窃案呼应。"],
                "estimatedWords": 1000,
                "acceptanceCriteria": "纪寻成功入城但留下疑点。",
            },
            {
                "order": 2,
                "goal": "暗巷接头：取得内城地图",
                "conflict": "接头人被跟踪。",
                "characters": ["纪寻", "线人"],
                "foreshadowingRefs": ["无"],
                "estimatedWords": 1300,
                "acceptanceCriteria": "地图到手并暴露新的追兵。",
            },
            {
                "order": 3,
                "goal": "城内落脚：避开搜查",
                "conflict": "客栈掌柜盘问来历。",
                "characters": [],
                "foreshadowingRefs": [],
                "estimatedWords": 500,
                "acceptanceCriteria": "纪寻取得临时藏身处。",
            },
        ],
    }
    assert beat_plan == original


@pytest.mark.asyncio
async def test_formal_applier_preserves_canonical_beat_plan_values() -> None:
    beat_plan: dict[str, object] = {
        "title": "规范计划",
        "chapterGoal": "推进主线。",
        "sceneBeats": [
            {
                "order": 3,
                "goal": "  保留目标两侧空格  ",
                "conflict": "  保留冲突两侧空格  ",
                "characters": ["  纪寻  "],
                "foreshadowingRefs": ["  原始伏笔引用  "],
                "estimatedWords": 0,
                "acceptanceCriteria": "  保留验收标准两侧空格  ",
            }
        ],
    }
    original = deepcopy(beat_plan)
    writes = FakeFormalWrites()

    await FormalArtifactApplier(writes, FakeUpdatesExecutor()).apply(
        _beat_plan_artifact(beat_plan),
        user_id="user-1",
        edited_content=None,
        selected_update_refs=None,
    )

    assert beat_plan == original
    assert writes.beat_plan == original
    assert writes.beat_plan is not beat_plan
    assert writes.beat_plan is not None
    written_scenes = writes.beat_plan["sceneBeats"]
    input_scenes = beat_plan["sceneBeats"]
    assert isinstance(written_scenes, list)
    assert isinstance(input_scenes, list)
    assert written_scenes is not input_scenes
    assert written_scenes[0] is not input_scenes[0]
    written_scene = written_scenes[0]
    input_scene = input_scenes[0]
    assert isinstance(written_scene, dict)
    assert isinstance(input_scene, dict)
    assert written_scene["characters"] is not input_scene["characters"]
    assert written_scene["foreshadowingRefs"] is not input_scene["foreshadowingRefs"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("invalid_fields", "message"),
    [
        pytest.param(
            {},
            "章节计划 chapterGoal 必须是非空字符串",
            id="missing-chapter-goal",
        ),
        pytest.param(
            {"chapterGoal": ""},
            "章节计划 chapterGoal 必须是非空字符串",
            id="empty-chapter-goal",
        ),
        pytest.param(
            {"chapterGoal": 1},
            "章节计划 chapterGoal 必须是非空字符串",
            id="non-string-chapter-goal",
        ),
        pytest.param(
            {"chapterGoal": "推进主线。", "mainPlotConnection": []},
            "章节计划 mainPlotConnection 必须是字符串",
            id="non-string-main-plot-connection",
        ),
        pytest.param(
            {"chapterGoal": "推进主线。", "chapterAcceptanceCriteria": []},
            "章节计划 chapterAcceptanceCriteria 必须是字符串",
            id="non-string-chapter-acceptance-criteria",
        ),
        pytest.param(
            {"chapterGoal": "推进主线。", "totalEstimatedWords": True},
            "章节计划 totalEstimatedWords 必须是非负整数",
            id="bool-total-estimated-words",
        ),
        pytest.param(
            {"chapterGoal": "推进主线。", "totalEstimatedWords": -1},
            "章节计划 totalEstimatedWords 必须是非负整数",
            id="negative-total-estimated-words",
        ),
        pytest.param(
            {"chapterGoal": "推进主线。", "totalEstimatedWords": "1000"},
            "章节计划 totalEstimatedWords 必须是非负整数",
            id="string-total-estimated-words",
        ),
    ],
)
async def test_formal_applier_rejects_invalid_canonical_beat_plan_fields(
    invalid_fields: dict[str, object],
    message: str,
) -> None:
    beat_plan: dict[str, object] = {
        "sceneBeats": [{"goal": "目标"}],
        **invalid_fields,
    }

    with pytest.raises(ValueError, match=f"^{message}$"):
        await FormalArtifactApplier(FakeFormalWrites(), FakeUpdatesExecutor()).apply(
            _beat_plan_artifact(beat_plan),
            user_id="user-1",
            edited_content=None,
            selected_update_refs=None,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scene_beats",
    [
        pytest.param([], id="empty-scenes"),
        pytest.param("not-a-list", id="scenes-not-list"),
        pytest.param(["not-a-scene"], id="scene-not-object"),
        pytest.param([{"sceneName": "只有名称"}], id="missing-goal"),
        pytest.param([{"goal": "目标", "characters": ["纪寻", 1]}], id="bad-character"),
        pytest.param([{"goal": "目标", "characters": [""]}], id="empty-character"),
        pytest.param([{"goal": "目标", "foreshadowingRefs": [1]}], id="bad-ref"),
        pytest.param([{"goal": "目标", "foreshadowingRefs": [""]}], id="empty-ref"),
        pytest.param([{"goal": "目标", "order": True}], id="bool-order"),
        pytest.param([{"goal": "目标", "order": -1}], id="negative-order"),
        pytest.param([{"goal": "目标", "estimatedWords": False}], id="bool-words"),
        pytest.param([{"goal": "目标", "estimatedWords": -1}], id="negative-words"),
        pytest.param([{"goal": "目标", "conflict": []}], id="bad-conflict"),
        pytest.param(
            [{"goal": "目标", "acceptanceCriteria": []}],
            id="bad-acceptance-criteria",
        ),
        pytest.param(
            [
                {
                    "sceneName": "场景",
                    "sceneGoal": "目标",
                    "foreshadowingReferences": [],
                }
            ],
            id="bad-legacy-ref",
        ),
    ],
)
async def test_formal_applier_rejects_malformed_scene_beats(scene_beats: object) -> None:
    beat_plan: dict[str, object] = {
        "chapterGoal": "推进主线。",
        "sceneBeats": scene_beats,
    }

    with pytest.raises(ValueError):
        await FormalArtifactApplier(FakeFormalWrites(), FakeUpdatesExecutor()).apply(
            _beat_plan_artifact(beat_plan),
            user_id="user-1",
            edited_content=None,
            selected_update_refs=None,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scene_beats", "message"),
    [
        pytest.param(
            [{"goal": "目标", "unexpectedField": "意外值"}],
            "章节计划场景包含未知字段：unexpectedField",
            id="unknown-field",
        ),
        pytest.param(
            [{"goal": "规范目标", "sceneName": "旧名称", "sceneGoal": "旧目标"}],
            "章节计划场景不能同时包含 goal 与 sceneName/sceneGoal",
            id="canonical-and-legacy-goal",
        ),
        pytest.param(
            [
                {
                    "goal": "目标",
                    "foreshadowingRefs": ["规范伏笔"],
                    "foreshadowingReferences": "旧伏笔",
                }
            ],
            (
                "章节计划场景不能同时包含 foreshadowingRefs "
                "与 foreshadowingReferences"
            ),
            id="canonical-and-legacy-foreshadowing",
        ),
    ],
)
async def test_formal_applier_rejects_malformed_scene_beats_with_clear_message(
    scene_beats: object,
    message: str,
) -> None:
    beat_plan: dict[str, object] = {
        "chapterGoal": "推进主线。",
        "sceneBeats": scene_beats,
    }

    with pytest.raises(ValueError, match=f"^{message}$"):
        await FormalArtifactApplier(FakeFormalWrites(), FakeUpdatesExecutor()).apply(
            _beat_plan_artifact(beat_plan),
            user_id="user-1",
            edited_content=None,
            selected_update_refs=None,
        )


@pytest.mark.asyncio
async def test_invalid_beat_plan_rolls_back_without_calling_formal_writes() -> None:
    writes = FakeFormalWrites()
    repository = FakeReviewRepository(
        _beat_plan_artifact(
            {
                "chapterGoal": "推进主线。",
                "sceneBeats": [],
            }
        )
    )
    service = ReviewService(
        repository,
        FormalArtifactApplier(writes, FakeUpdatesExecutor()),
    )

    with pytest.raises(ApiError) as error:
        await service.decide("user-1", "artifact-1", "approve", expected_revision=1)

    assert error.value.code == "ARTIFACT_APPLY_FAILED"
    assert repository.transitions == [
        ("awaiting_user", "applying"),
        ("applying", "awaiting_user"),
    ]
    assert repository.artifact.status == "awaiting_user"
    assert writes.calls == 0


@pytest.mark.asyncio
async def test_formal_applier_preserves_complete_edited_chapter_content() -> None:
    writes = FakeFormalWrites()
    applier = FormalArtifactApplier(writes, FakeUpdatesExecutor())
    artifact = Artifact()
    artifact.novel_id = "novel-1"
    artifact.chapter_id = "chapter-1"
    complete_content = "正文" * 20_000

    await applier.apply(
        artifact,
        user_id="user-1",
        edited_content=complete_content,
        selected_update_refs=None,
    )

    assert writes.content == complete_content


@pytest.mark.asyncio
async def test_formal_applier_filters_selected_agent_updates() -> None:
    executor = FakeUpdatesExecutor()
    applier = FormalArtifactApplier(FakeFormalWrites(), executor)
    artifact = Artifact(
        kind="agent_updates",
        payload={
            "kind": "agent_updates",
            "updates": {
                "characters": [
                    {"action": "update", "name": "甲"},
                    {"action": "update", "name": "乙"},
                ]
            },
        },
    )
    artifact.novel_id = "novel-1"
    artifact.chapter_id = None

    await applier.apply(
        artifact,
        user_id="user-1",
        edited_content=None,
        selected_update_refs=[{"section": "characters", "index": 1}],
    )

    assert executor.updates == {"characters": [{"action": "update", "name": "乙"}]}


@pytest.mark.asyncio
async def test_formal_applier_forwards_outline_cas_from_artifact() -> None:
    executor = FakeUpdatesExecutor()
    applier = FormalArtifactApplier(FakeFormalWrites(), executor)
    artifact = Artifact(
        kind="agent_updates",
        payload={
            "kind": "agent_updates",
            "baseOutlineUpdatedAt": "2026-07-30T00:00:00Z",
            "updates": {"outlineContent": "候选大纲"},
        },
    )
    artifact.novel_id = "novel-1"
    artifact.chapter_id = None

    await applier.apply(
        artifact,
        user_id="user-1",
        edited_content=None,
        selected_update_refs=None,
    )

    assert executor.expected_outline_updated_at == datetime(
        2026, 7, 30, tzinfo=UTC
    )


@pytest.mark.asyncio
async def test_formal_applier_forwards_lore_text_cas_from_artifact() -> None:
    executor = FakeUpdatesExecutor()
    applier = FormalArtifactApplier(FakeFormalWrites(), executor)
    artifact = Artifact(
        kind="agent_updates",
        payload={
            "kind": "agent_updates",
            "baseLoreUpdatedAt": {
                "worldSetting": "2026-07-30T00:00:00Z",
                "storyBackground": None,
            },
            "updates": {
                "worldSetting": "候选世界设定",
                "storyBackground": "候选故事背景",
            },
        },
    )
    artifact.novel_id = "novel-1"
    artifact.chapter_id = None

    await applier.apply(
        artifact,
        user_id="user-1",
        edited_content=None,
        selected_update_refs=None,
    )

    assert executor.expected_lore_updated_at == {
        "worldSetting": datetime(2026, 7, 30, tzinfo=UTC),
        "storyBackground": None,
    }


@pytest.mark.asyncio
async def test_selection_applier_uses_replacement_and_rejects_full_content() -> None:
    writes = FakeFormalWrites()
    applier = FormalArtifactApplier(writes, FakeUpdatesExecutor())
    artifact = Artifact(
        kind="chapter_draft",
        payload={
            "kind": "chapter_draft",
            "operation": "rewrite_chapter_selection",
            "target": {"mode": "replace_selection"},
            "resourceType": "chapter_content",
            "resourceId": "chapter-1",
            "baseUpdatedAt": "2026-07-30T00:00:00Z",
            "baseContentHash": "a" * 64,
            "selectionStart": 1,
            "selectionEnd": 2,
            "selectedTextHash": "b" * 64,
            "selectedText": "x",
            "replacement": "y",
        },
    )
    artifact.novel_id = "novel-1"
    artifact.chapter_id = "chapter-1"

    await applier.apply(
        artifact,
        user_id="user-1",
        edited_content=None,
        edited_replacement="z",
        selected_update_refs=None,
    )
    assert writes.content == "z"

    with pytest.raises(ValueError, match="editedContent"):
        await applier.apply(
            artifact,
            user_id="user-1",
            edited_content="full document",
            edited_replacement=None,
            selected_update_refs=None,
        )


class FormalWriteSession:
    def __init__(self, chapter: Chapter, check: ChapterQualityCheck) -> None:
        self.chapter = chapter
        self.check = check
        self.executed: list[object] = []
        self.added: list[object] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback

    @asynccontextmanager
    async def begin(self):
        yield

    async def scalar(self, statement):
        entity = statement.column_descriptions[0].get("entity")
        if entity is Novel:
            return "user-1"
        if entity is Chapter:
            return self.chapter
        if entity is ChapterQualityCheck:
            return self.check
        raise AssertionError(f"未处理的查询实体：{entity}")

    async def execute(self, statement):
        self.executed.append(statement)
        return None

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        return None


@pytest.mark.asyncio
async def test_formal_chapter_write_reopens_chapter_and_invalidates_old_check() -> None:
    now = datetime(2026, 7, 11, tzinfo=UTC)
    chapter = Chapter(
        id="chapter-1",
        novelId="novel-1",
        order=1,
        status="completed",
        title="第一章",
        content="旧正文",
        completedAt=now,
        createdAt=now,
        updatedAt=now,
    )
    check = ChapterQualityCheck(
        id="check-1",
        chapterId=chapter.id,
        type="consistency",
        status="completed",
        title="一致性终检",
        result="旧报告",
        scoreOverall=9,
        qualityGate="pass",
        createdAt=now,
        updatedAt=now,
    )
    session = FormalWriteSession(chapter, check)
    repository = FormalWriteRepository(lambda: session)  # type: ignore[arg-type]
    artifact = Artifact(
        payload={
            "kind": "chapter_draft",
            "content": "新正文",
            "target": {"mode": "existing_chapter", "chapterId": chapter.id},
        }
    )
    artifact.novel_id = "novel-1"
    artifact.chapter_id = chapter.id

    await repository.apply_chapter(artifact, "user-1", "新正文")  # type: ignore[arg-type]

    assert chapter.content == "新正文"
    assert chapter.status == "drafting"
    assert chapter.completedAt is None
    assert check.status == "pending"
    assert check.result is None
    assert check.scoreOverall is None
    assert check.qualityGate is None
    assert len(session.executed) == 1


@pytest.mark.asyncio
async def test_formal_same_content_still_reopens_without_invalidating_check() -> None:
    now = datetime(2026, 7, 11, tzinfo=UTC)
    chapter = Chapter(
        id="chapter-1",
        novelId="novel-1",
        order=1,
        status="completed",
        title="第一章",
        content="相同正文",
        completedAt=now,
        createdAt=now,
        updatedAt=now,
    )
    check = ChapterQualityCheck(
        id="check-1",
        chapterId=chapter.id,
        type="consistency",
        status="completed",
        title="一致性终检",
        result="当前正文报告",
        scoreOverall=9,
        qualityGate="pass",
        createdAt=now,
        updatedAt=now,
    )
    session = FormalWriteSession(chapter, check)
    repository = FormalWriteRepository(lambda: session)  # type: ignore[arg-type]
    artifact = Artifact(
        payload={
            "kind": "chapter_draft",
            "content": "相同正文",
            "target": {"mode": "existing_chapter", "chapterId": chapter.id},
        }
    )
    artifact.novel_id = "novel-1"
    artifact.chapter_id = chapter.id

    await repository.apply_chapter(artifact, "user-1", "相同正文")  # type: ignore[arg-type]

    assert chapter.status == "drafting"
    assert chapter.completedAt is None
    assert chapter.updatedAt.replace(tzinfo=UTC) > now
    assert check.status == "completed"
    assert check.result == "当前正文报告"
    assert session.executed == []


@pytest.mark.asyncio
async def test_formal_selection_write_splices_authoritative_chapter_only() -> None:
    now = datetime(2026, 7, 11, tzinfo=UTC)
    source = "前缀😀选区后缀"
    selected = "选区"
    chapter = Chapter(
        id="chapter-1",
        novelId="novel-1",
        order=1,
        status="completed",
        title="第一章",
        content=source,
        completedAt=now,
        createdAt=now,
        updatedAt=now,
    )
    check = ChapterQualityCheck(
        id="check-1",
        chapterId=chapter.id,
        type="consistency",
        status="completed",
        title="一致性终检",
        result="旧报告",
        createdAt=now,
        updatedAt=now,
    )
    session = FormalWriteSession(chapter, check)
    repository = FormalWriteRepository(lambda: session)  # type: ignore[arg-type]
    artifact = Artifact(
        kind="chapter_draft",
        payload={
            "kind": "chapter_draft",
            "target": {"mode": "replace_selection"},
            "resourceType": "chapter_content",
            "resourceId": chapter.id,
            "baseUpdatedAt": now.isoformat(),
            "baseContentHash": hashlib.sha256(source.encode()).hexdigest(),
            "selectionStart": 3,
            "selectionEnd": 5,
            "selectedTextHash": hashlib.sha256(selected.encode()).hexdigest(),
            "replacement": "替换",
        },
    )
    artifact.novel_id = "novel-1"
    artifact.chapter_id = chapter.id

    await repository.apply_selection(artifact, "user-1", "替换")  # type: ignore[arg-type]

    assert chapter.content == "前缀😀替换后缀"


def test_selection_diff_contains_complete_before_after_and_replacement() -> None:
    diff = _selection_diff(
        {
            "target": {"mode": "replace_selection"},
            "resourceType": "chapter_content",
            "resourceId": "chapter-1",
            "selectionStart": 2,
            "selectionEnd": 4,
            "selectedText": "旧文",
            "replacement": "新文",
            "candidate": "前缀新文后缀",
            "candidatePrefix": "前缀",
            "candidateSuffix": "后缀",
        }
    )

    assert diff is not None
    assert diff["before"] == "前缀旧文后缀"
    assert diff["after"] == "前缀新文后缀"
    assert diff["replacement"] == "新文"


@pytest.mark.parametrize(
    ("kind", "mode", "expected"),
    [
        ("chapter_draft", None, "chapter_content"),
        ("chapter_draft", "existing_chapter", "chapter_content"),
        ("chapter_draft", "new_next_chapter", "chapter_content"),
        ("outline_draft", "normal_outline", "outline_content"),
        ("chapter_draft", "future_mode", None),
        ("outline_draft", "future_mode", None),
    ],
)
def test_resolve_apply_target_rejects_unknown_modes(
    kind: str, mode: str | None, expected: str | None
) -> None:
    payload: dict[str, object] = {"kind": kind}
    if mode is not None:
        payload["target"] = {"mode": mode}

    assert resolve_apply_target(payload) == expected


@pytest.mark.asyncio
async def test_formal_applier_rejects_unknown_target_mode_before_full_write() -> None:
    writes = FakeFormalWrites()
    applier = FormalArtifactApplier(writes, FakeUpdatesExecutor())
    artifact = Artifact(
        kind="chapter_draft",
        payload={
            "kind": "chapter_draft",
            "target": {"mode": "future_mode"},
            "content": "不应写入",
        },
    )
    artifact.novel_id = "novel-1"
    artifact.chapter_id = "chapter-1"

    with pytest.raises(ValueError):
        await applier.apply(
            artifact,
            user_id="user-1",
            edited_content=None,
            selected_update_refs=None,
        )
    assert writes.content is None


@pytest.mark.asyncio
async def test_selection_materializer_rejects_nested_top_level_identity_mismatch() -> None:
    payload = {
        "kind": "chapter_draft",
        "target": {
            "mode": "replace_selection",
            "resourceType": "chapter_content",
            "resourceId": "chapter-1",
        },
        "resourceType": "chapter_content",
        "resourceId": "chapter-2",
    }

    with pytest.raises(ApiError) as error:
        await _materialize_selection_payload(  # type: ignore[arg-type]
            object(), payload, kind="chapter_draft", novel_id="novel-1"
        )

    assert error.value.code == "ARTIFACT_SOURCE_VERSION_CONFLICT"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "mode"),
    [
        ("chapter_draft", "existing_chapter"),
        ("chapter_draft", "new_next_chapter"),
        ("outline_draft", "normal_outline"),
    ],
)
async def test_materializer_preserves_normal_draft_target_modes(
    kind: str, mode: str
) -> None:
    payload = {"kind": kind, "target": {"mode": mode}}

    await _materialize_selection_payload(  # type: ignore[arg-type]
        object(), payload, kind=kind, novel_id="novel-1"
    )

    assert payload["target"] == {"mode": mode}


@pytest.mark.asyncio
async def test_materializer_rejects_unknown_target_mode() -> None:
    with pytest.raises(ApiError) as error:
        await _materialize_selection_payload(  # type: ignore[arg-type]
            object(),
            {"kind": "chapter_draft", "target": {"mode": "future_mode"}},
            kind="chapter_draft",
            novel_id="novel-1",
        )

    assert error.value.code == "ARTIFACT_SELECTION_TARGET_INVALID"
