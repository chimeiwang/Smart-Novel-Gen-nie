from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from inkforge_contracts.long_serial import AbsenceSentinel, SourceBinding
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Chapter, ChapterBeatPlan, Novel, Outline, SceneBeat
from ..errors import ApiError
from .idempotency import canonical_json_bytes


async def capture_chapter_source_bindings(
    session: AsyncSession,
    *,
    novel_id: str,
    chapter_id: str,
) -> tuple[SourceBinding, ...]:
    locked_novel_id = await session.scalar(
        select(Novel.id).where(Novel.id == novel_id).with_for_update()
    )
    if locked_novel_id != novel_id:
        raise ApiError(status_code=404, code="NOVEL_NOT_FOUND", message="小说不存在")

    chapter = await session.scalar(
        select(Chapter)
        .where(Chapter.id == chapter_id, Chapter.novelId == novel_id)
        .with_for_update()
    )
    if chapter is None:
        raise ApiError(
            status_code=404,
            code="CHAPTER_NOT_FOUND",
            message="章节不存在或不属于该小说",
        )

    outline = await session.scalar(
        select(Outline)
        .where(Outline.novelId == novel_id)
        .with_for_update()
    )
    approved_plans = list(
        (
            await session.scalars(
                select(ChapterBeatPlan)
                .where(
                    ChapterBeatPlan.chapterId == chapter_id,
                    ChapterBeatPlan.status == "approved",
                )
                .order_by(ChapterBeatPlan.id.asc())
                .with_for_update()
            )
        ).all()
    )
    if len(approved_plans) > 1:
        raise _ambiguous_beat_plan(chapter_id)

    bindings = [
        _existing_text_binding(
            resource_type="chapter",
            resource_id=chapter.id,
            updated_at=chapter.updatedAt,
            content=chapter.content,
        ),
        (
            _existing_text_binding(
                resource_type="outline",
                resource_id=outline.id,
                updated_at=outline.updatedAt,
                content=outline.content,
            )
            if outline is not None
            else _absent_binding(
                resource_type="outline",
                resource_id=f"novel:{novel_id}:outline",
                sentinel_type="novel",
                sentinel_id=novel_id,
            )
        ),
    ]

    if approved_plans:
        plan = approved_plans[0]
        beats = list(
            (
                await session.scalars(
                    select(SceneBeat)
                    .where(SceneBeat.beatPlanId == plan.id)
                    .order_by(SceneBeat.order.asc(), SceneBeat.id.asc())
                    .with_for_update()
                )
            ).all()
        )
        bindings.append(_approved_beat_plan_binding(plan, beats))
    else:
        bindings.append(
            _absent_binding(
                resource_type="approved_beat_plan",
                resource_id=f"chapter:{chapter_id}:approved_beat_plan",
                sentinel_type="chapter",
                sentinel_id=chapter_id,
            )
        )
    return tuple(bindings)


async def verify_source_bindings(
    session: AsyncSession,
    bindings: tuple[SourceBinding, ...],
) -> None:
    for binding in sorted(
        bindings, key=lambda item: (item.resourceType, item.resourceId)
    ):
        if binding.resourceType == "chapter":
            await _verify_chapter(session, binding)
        elif binding.resourceType == "outline":
            await _verify_outline(session, binding)
        elif binding.resourceType == "approved_beat_plan":
            await _verify_approved_beat_plan(session, binding)
        else:
            raise ApiError(
                status_code=409,
                code="ARTIFACT_SOURCE_BINDING_INVALID",
                message="审核产物包含不受支持的来源绑定",
                details={
                    "resourceType": binding.resourceType,
                    "resourceId": binding.resourceId,
                },
            )


async def _verify_chapter(session: AsyncSession, binding: SourceBinding) -> None:
    if not binding.exists or binding.absenceSentinel is not None:
        raise _source_conflict(binding)
    chapter = await session.scalar(
        select(Chapter)
        .where(Chapter.id == binding.resourceId)
        .with_for_update()
    )
    if chapter is None or not _matches_text_binding(
        binding,
        updated_at=chapter.updatedAt,
        content=chapter.content,
    ):
        raise _source_conflict(binding)


async def _verify_outline(session: AsyncSession, binding: SourceBinding) -> None:
    if binding.exists:
        outline = await session.scalar(
            select(Outline)
            .where(Outline.id == binding.resourceId)
            .with_for_update()
        )
        if outline is None or not _matches_text_binding(
            binding,
            updated_at=outline.updatedAt,
            content=outline.content,
        ):
            raise _source_conflict(binding)
        return

    sentinel = binding.absenceSentinel
    if (
        sentinel is None
        or sentinel.resourceType != "novel"
        or binding.resourceId != f"novel:{sentinel.resourceId}:outline"
    ):
        raise _source_conflict(binding)
    current = await session.scalar(
        select(Outline)
        .where(Outline.novelId == sentinel.resourceId)
        .with_for_update()
    )
    if current is not None:
        raise _source_conflict(binding)


async def _verify_approved_beat_plan(
    session: AsyncSession,
    binding: SourceBinding,
) -> None:
    if not binding.exists:
        sentinel = binding.absenceSentinel
        if (
            sentinel is None
            or sentinel.resourceType != "chapter"
            or binding.resourceId
            != f"chapter:{sentinel.resourceId}:approved_beat_plan"
        ):
            raise _source_conflict(binding)
        approved = list(
            (
                await session.scalars(
                    select(ChapterBeatPlan)
                    .where(
                        ChapterBeatPlan.chapterId == sentinel.resourceId,
                        ChapterBeatPlan.status == "approved",
                    )
                    .order_by(ChapterBeatPlan.id.asc())
                    .with_for_update()
                )
            ).all()
        )
        if len(approved) > 1:
            raise _ambiguous_beat_plan(sentinel.resourceId)
        if approved:
            raise _source_conflict(binding)
        return

    plan = await session.scalar(
        select(ChapterBeatPlan)
        .where(
            ChapterBeatPlan.id == binding.resourceId,
            ChapterBeatPlan.status == "approved",
        )
        .with_for_update()
    )
    if plan is None:
        raise _source_conflict(binding)
    approved = list(
        (
            await session.scalars(
                select(ChapterBeatPlan)
                .where(
                    ChapterBeatPlan.chapterId == plan.chapterId,
                    ChapterBeatPlan.status == "approved",
                )
                .order_by(ChapterBeatPlan.id.asc())
                .with_for_update()
            )
        ).all()
    )
    if len(approved) > 1:
        raise _ambiguous_beat_plan(plan.chapterId)
    if len(approved) != 1 or approved[0].id != binding.resourceId:
        raise _source_conflict(binding)
    beats = list(
        (
            await session.scalars(
                select(SceneBeat)
                .where(SceneBeat.beatPlanId == plan.id)
                .order_by(SceneBeat.order.asc(), SceneBeat.id.asc())
                .with_for_update()
            )
        ).all()
    )
    current = _approved_beat_plan_binding(plan, beats)
    if current.model_dump(mode="json") != binding.model_dump(mode="json"):
        raise _source_conflict(binding)


def _existing_text_binding(
    *,
    resource_type: str,
    resource_id: str,
    updated_at: datetime,
    content: str,
) -> SourceBinding:
    return SourceBinding(
        resourceType=resource_type,
        resourceId=resource_id,
        exists=True,
        updatedAt=_aware_datetime(updated_at),
        contentSha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        revision=None,
        absenceSentinel=None,
    )


def _absent_binding(
    *,
    resource_type: str,
    resource_id: str,
    sentinel_type: str,
    sentinel_id: str,
) -> SourceBinding:
    return SourceBinding(
        resourceType=resource_type,
        resourceId=resource_id,
        exists=False,
        updatedAt=None,
        contentSha256=None,
        revision=None,
        absenceSentinel=AbsenceSentinel(
            resourceType=sentinel_type,
            resourceId=sentinel_id,
        ),
    )


def _approved_beat_plan_binding(
    plan: ChapterBeatPlan,
    beats: list[SceneBeat],
) -> SourceBinding:
    payload = _approved_beat_plan_payload(plan, beats)
    return SourceBinding(
        resourceType="approved_beat_plan",
        resourceId=plan.id,
        exists=True,
        updatedAt=_aware_datetime(plan.updatedAt),
        contentSha256=hashlib.sha256(canonical_json_bytes(payload)).hexdigest(),
        revision=None,
        absenceSentinel=None,
    )


def _approved_beat_plan_payload(
    plan: ChapterBeatPlan,
    beats: list[SceneBeat],
) -> dict[str, object]:
    ordered_beats = sorted(beats, key=lambda beat: (beat.order, beat.id))
    return {
        "id": plan.id,
        "chapterId": plan.chapterId,
        "goalId": plan.goalId,
        "status": plan.status,
        "chapterGoal": plan.chapterGoal,
        "mainPlotConnection": plan.mainPlotConnection,
        "chapterAcceptanceCriteria": plan.chapterAcceptanceCriteria,
        "totalEstimatedWords": plan.totalEstimatedWords,
        "generatedBy": plan.generatedBy,
        "createdAt": _aware_datetime(plan.createdAt),
        "updatedAt": _aware_datetime(plan.updatedAt),
        "sceneBeats": [
            {
                "id": beat.id,
                "order": beat.order,
                "goal": beat.goal,
                "conflict": beat.conflict,
                "characters": beat.characters,
                "foreshadowingRefs": beat.foreshadowingRefs,
                "estimatedWords": beat.estimatedWords,
                "acceptanceCriteria": beat.acceptanceCriteria,
            }
            for beat in ordered_beats
        ],
    }


def _matches_text_binding(
    binding: SourceBinding,
    *,
    updated_at: datetime,
    content: str,
) -> bool:
    return (
        binding.revision is None
        and binding.updatedAt == _aware_datetime(updated_at)
        and binding.contentSha256
        == hashlib.sha256(content.encode("utf-8")).hexdigest()
    )


def _aware_datetime(value: datetime | None) -> datetime:
    if value is None:
        raise RuntimeError("来源更新时间缺失")
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _source_conflict(binding: SourceBinding) -> ApiError:
    return ApiError(
        status_code=409,
        code="ARTIFACT_SOURCE_VERSION_CONFLICT",
        message="审核产物的来源版本已变化",
        details={
            "resourceType": binding.resourceType,
            "resourceId": binding.resourceId,
        },
    )


def _ambiguous_beat_plan(chapter_id: str) -> ApiError:
    return ApiError(
        status_code=409,
        code="BEAT_PLAN_SOURCE_AMBIGUOUS",
        message="章节存在多个已批准计划，无法确定权威来源",
        details={"chapterId": chapter_id},
    )
