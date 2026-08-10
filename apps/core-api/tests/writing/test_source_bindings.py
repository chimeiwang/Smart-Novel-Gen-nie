from __future__ import annotations

import hashlib
import inspect
from collections.abc import Sequence
from datetime import UTC, datetime

import pytest
from inkforge_contracts.long_serial import AbsenceSentinel, SourceBinding
from inkforge_core.db.models import Chapter, ChapterBeatPlan, Outline, OutlineNode, SceneBeat
from inkforge_core.errors import ApiError
from inkforge_core.outlines.repository import OutlineRepository
from inkforge_core.reviews.formal_writes import FormalWriteRepository
from inkforge_core.writing.idempotency import canonical_json_bytes
from inkforge_core.writing.source_bindings import (
    capture_chapter_source_bindings,
    verify_source_bindings,
)

NOW = datetime(2026, 8, 5, 10, 0, tzinfo=UTC)


class ScalarCollection:
    def __init__(self, values: Sequence[object]) -> None:
        self._values = list(values)

    def all(self) -> list[object]:
        return self._values


class SourceSession:
    def __init__(
        self,
        *,
        scalar_values: Sequence[object | None],
        scalars_values: Sequence[Sequence[object]] = (),
    ) -> None:
        self.scalar_values = list(scalar_values)
        self.scalars_values = [list(values) for values in scalars_values]
        self.statements: list[object] = []

    async def scalar(self, statement: object) -> object | None:
        self.statements.append(statement)
        return self.scalar_values.pop(0)

    async def scalars(self, statement: object) -> ScalarCollection:
        self.statements.append(statement)
        return ScalarCollection(self.scalars_values.pop(0))


def chapter(*, content: str = "第一行\r\n第二行🙂") -> Chapter:
    return Chapter(
        id="chapter-1",
        novelId="novel-1",
        title="雨夜",
        content=content,
        order=1,
        status="drafting",
        updatedAt=NOW.replace(tzinfo=None),
    )


def outline(*, content: str = "总纲：风暴不会被规范化。") -> Outline:
    return Outline(
        id="outline-1",
        novelId="novel-1",
        content=content,
        createdAt=NOW.replace(tzinfo=None),
        updatedAt=NOW.replace(tzinfo=None),
    )


def beat_plan(*, plan_id: str = "plan-1") -> ChapterBeatPlan:
    return ChapterBeatPlan(
        id=plan_id,
        chapterId="chapter-1",
        goalId=None,
        status="approved",
        chapterGoal="主角在雨夜作出选择",
        mainPlotConnection="推进主线",
        chapterAcceptanceCriteria="选择不可撤销",
        totalEstimatedWords=4_000,
        generatedBy="剧情",
        createdAt=NOW.replace(tzinfo=None),
        updatedAt=NOW.replace(tzinfo=None),
    )


def scene(
    beat_id: str,
    order: int,
    *,
    goal: str,
) -> SceneBeat:
    return SceneBeat(
        id=beat_id,
        beatPlanId="plan-1",
        order=order,
        goal=goal,
        conflict="风雨阻拦",
        characters='["主角"]',
        foreshadowingRefs='["雨伞"]',
        estimatedWords=1_000,
        acceptanceCriteria="完成场景选择",
    )


@pytest.mark.asyncio
async def test_capture_binds_complete_utf8_sources_and_sorted_scene_beats() -> None:
    current_chapter = chapter()
    current_outline = outline()
    current_plan = beat_plan()
    second = scene("beat-2", 2, goal="承担后果")
    first = scene("beat-1", 1, goal="进入雨幕")
    session = SourceSession(
        scalar_values=["novel-1", current_chapter, current_outline],
        scalars_values=[[current_plan], [second, first]],
    )

    bindings = await capture_chapter_source_bindings(  # type: ignore[arg-type]
        session,
        novel_id="novel-1",
        chapter_id="chapter-1",
    )

    by_type = {binding.resourceType: binding for binding in bindings}
    assert tuple(by_type) == ("chapter", "outline", "approved_beat_plan")
    assert by_type["chapter"].contentSha256 == hashlib.sha256(
        "第一行\r\n第二行🙂".encode()
    ).hexdigest()
    assert by_type["outline"].contentSha256 == hashlib.sha256(
        "总纲：风暴不会被规范化。".encode()
    ).hexdigest()
    expected_plan = {
        "id": "plan-1",
        "chapterId": "chapter-1",
        "goalId": None,
        "status": "approved",
        "chapterGoal": "主角在雨夜作出选择",
        "mainPlotConnection": "推进主线",
        "chapterAcceptanceCriteria": "选择不可撤销",
        "totalEstimatedWords": 4_000,
        "generatedBy": "剧情",
        "createdAt": NOW,
        "updatedAt": NOW,
        "sceneBeats": [
            {
                "id": "beat-1",
                "order": 1,
                "goal": "进入雨幕",
                "conflict": "风雨阻拦",
                "characters": '["主角"]',
                "foreshadowingRefs": '["雨伞"]',
                "estimatedWords": 1_000,
                "acceptanceCriteria": "完成场景选择",
            },
            {
                "id": "beat-2",
                "order": 2,
                "goal": "承担后果",
                "conflict": "风雨阻拦",
                "characters": '["主角"]',
                "foreshadowingRefs": '["雨伞"]',
                "estimatedWords": 1_000,
                "acceptanceCriteria": "完成场景选择",
            },
        ],
    }
    assert by_type["approved_beat_plan"].contentSha256 == hashlib.sha256(
        canonical_json_bytes(expected_plan)
    ).hexdigest()
    assert all("FOR UPDATE" in str(statement) for statement in session.statements)


@pytest.mark.asyncio
async def test_capture_uses_stable_absence_sentinels() -> None:
    session = SourceSession(
        scalar_values=["novel-1", chapter(), None],
        scalars_values=[[]],
    )

    bindings = await capture_chapter_source_bindings(  # type: ignore[arg-type]
        session,
        novel_id="novel-1",
        chapter_id="chapter-1",
    )

    by_type = {binding.resourceType: binding for binding in bindings}
    assert by_type["outline"].model_dump(mode="json") == {
        "resourceType": "outline",
        "resourceId": "novel:novel-1:outline",
        "exists": False,
        "updatedAt": None,
        "contentSha256": None,
        "revision": None,
        "absenceSentinel": {
            "resourceType": "novel",
            "resourceId": "novel-1",
        },
    }
    assert by_type["approved_beat_plan"].model_dump(mode="json") == {
        "resourceType": "approved_beat_plan",
        "resourceId": "chapter:chapter-1:approved_beat_plan",
        "exists": False,
        "updatedAt": None,
        "contentSha256": None,
        "revision": None,
        "absenceSentinel": {
            "resourceType": "chapter",
            "resourceId": "chapter-1",
        },
    }


@pytest.mark.asyncio
async def test_capture_rejects_multiple_approved_beat_plans() -> None:
    session = SourceSession(
        scalar_values=["novel-1", chapter(), outline()],
        scalars_values=[[beat_plan(plan_id="plan-1"), beat_plan(plan_id="plan-2")]],
    )

    with pytest.raises(ApiError) as error:
        await capture_chapter_source_bindings(  # type: ignore[arg-type]
            session,
            novel_id="novel-1",
            chapter_id="chapter-1",
        )

    assert error.value.status_code == 409
    assert error.value.code == "BEAT_PLAN_SOURCE_AMBIGUOUS"


@pytest.mark.asyncio
async def test_verify_rejects_changed_chapter_bytes() -> None:
    binding = SourceBinding(
        resourceType="chapter",
        resourceId="chapter-1",
        exists=True,
        updatedAt=NOW,
        contentSha256=hashlib.sha256("原文".encode()).hexdigest(),
        revision=None,
        absenceSentinel=None,
    )
    changed = chapter(content="新文")
    session = SourceSession(scalar_values=[changed])

    with pytest.raises(ApiError) as error:
        await verify_source_bindings(  # type: ignore[arg-type]
            session, (binding,)
        )

    assert error.value.code == "ARTIFACT_SOURCE_VERSION_CONFLICT"


@pytest.mark.asyncio
async def test_verify_rejects_changed_outline_node_content() -> None:
    node = OutlineNode(
        id="node-1",
        novelId="novel-1",
        title="节点",
        kind="stage",
        order=1,
        content="原节点内容",
        updatedAt=NOW.replace(tzinfo=None),
    )
    binding = SourceBinding(
        resourceType="outline_node_content",
        resourceId="node-1",
        exists=True,
        updatedAt=NOW,
        contentSha256=hashlib.sha256("原节点内容".encode()).hexdigest(),
        revision=None,
        absenceSentinel=None,
    )
    await verify_source_bindings(  # type: ignore[arg-type]
        SourceSession(scalar_values=[node]), (binding,)
    )
    node.content = "节点已变化"
    with pytest.raises(ApiError) as error:
        await verify_source_bindings(  # type: ignore[arg-type]
            SourceSession(scalar_values=[node]), (binding,)
        )
    assert error.value.code == "ARTIFACT_SOURCE_VERSION_CONFLICT"


@pytest.mark.asyncio
async def test_verify_absent_outline_detects_later_creation() -> None:
    binding = SourceBinding(
        resourceType="outline",
        resourceId="novel:novel-1:outline",
        exists=False,
        updatedAt=None,
        contentSha256=None,
        revision=None,
        absenceSentinel=AbsenceSentinel(
            resourceType="novel", resourceId="novel-1"
        ),
    )

    await verify_source_bindings(  # type: ignore[arg-type]
        SourceSession(scalar_values=[None]), (binding,)
    )

    with pytest.raises(ApiError) as error:
        await verify_source_bindings(  # type: ignore[arg-type]
            SourceSession(scalar_values=[outline()]), (binding,)
        )
    assert error.value.code == "ARTIFACT_SOURCE_VERSION_CONFLICT"


@pytest.mark.asyncio
async def test_verify_approved_beat_plan_detects_scene_change() -> None:
    current_plan = beat_plan()
    current_scene = scene("beat-1", 1, goal="进入雨幕")
    captured = await capture_chapter_source_bindings(  # type: ignore[arg-type]
        SourceSession(
            scalar_values=["novel-1", chapter(), outline()],
            scalars_values=[[current_plan], [current_scene]],
        ),
        novel_id="novel-1",
        chapter_id="chapter-1",
    )
    binding = next(
        item for item in captured if item.resourceType == "approved_beat_plan"
    )

    await verify_source_bindings(  # type: ignore[arg-type]
        SourceSession(
            scalar_values=[current_plan],
            scalars_values=[[current_plan], [current_scene]],
        ),
        (binding,),
    )

    changed_scene = scene("beat-1", 1, goal="绕开雨幕")
    with pytest.raises(ApiError) as error:
        await verify_source_bindings(  # type: ignore[arg-type]
            SourceSession(
                scalar_values=[current_plan],
                scalars_values=[[current_plan], [changed_scene]],
            ),
            (binding,),
        )
    assert error.value.code == "ARTIFACT_SOURCE_VERSION_CONFLICT"


def test_real_outline_and_beat_plan_writes_take_the_same_parent_row_locks() -> None:
    outline_source = inspect.getsource(OutlineRepository.upsert_outline)
    novel_lock_source = inspect.getsource(OutlineRepository._lock_novel)
    beat_plan_source = inspect.getsource(FormalWriteRepository.apply_beat_plan)

    assert "_lock_novel" in outline_source
    assert "select(Novel)" in novel_lock_source
    assert ".with_for_update()" in novel_lock_source
    assert "select(Chapter)" in beat_plan_source
    assert ".with_for_update()" in beat_plan_source
