from __future__ import annotations

import json

from inkforge_contracts import (
    ShortStoryChapterDraft,
    ShortStoryOutlineDraft,
    canonical_short_outline_hash,
    count_short_story_text_length,
)
from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..chapters.content_state import (
    content_sha256,
    lock_consistency_check,
    replace_chapter_content,
)
from ..db.models import (
    Chapter,
    ChapterBeatPlan,
    ChapterQualityCheck,
    Novel,
    Outline,
    ReviewArtifact,
    ReviewArtifactEvaluation,
    SceneBeat,
    WritingBible,
)
from ..errors import ApiError
from .apply import ApplicableArtifactPort


class FormalWriteRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def apply_outline(
        self, artifact: ApplicableArtifactPort, user_id: str, content: str
    ) -> int:
        async with self._session_factory() as session:
            async with session.begin():
                await _require_owner(session, artifact.novel_id, user_id)
                await session.execute(
                    pg_insert(Outline)
                    .values(novelId=artifact.novel_id, content=content)
                    .on_conflict_do_update(
                        index_elements=[Outline.novelId], set_={"content": content}
                    )
                )
        return 1

    async def apply_chapter(
        self, artifact: ApplicableArtifactPort, user_id: str, content: str
    ) -> int:
        payload = artifact.payload
        if (
            payload.get("kind") == "chapter_draft"
            and payload.get("storyLengthProfile") == "short_medium"
        ):
            return await self._apply_short_story_chapter(artifact, user_id, content)
        target = payload.get("target") if payload.get("kind") == "chapter_draft" else None
        async with self._session_factory() as session:
            async with session.begin():
                await _require_owner(session, artifact.novel_id, user_id)
                if isinstance(target, dict) and target.get("mode") == "new_next_chapter":
                    maximum = await session.scalar(
                        select(func.max(Chapter.order)).where(Chapter.novelId == artifact.novel_id)
                    )
                    order = (maximum or 0) + 1
                    title = target.get("title")
                    chapter = Chapter(
                        novelId=artifact.novel_id,
                        order=order,
                        title=(title if isinstance(title, str) and title else f"第 {order} 章"),
                        content=content,
                        status="drafting",
                    )
                    session.add(chapter)
                    await session.flush()
                    chapter_id = chapter.id
                else:
                    requested_id = (
                        target.get("chapterId")
                        if isinstance(target, dict) and target.get("mode") == "existing_chapter"
                        else artifact.chapter_id
                    )
                    if not isinstance(requested_id, str) or not requested_id:
                        raise ValueError("正文草案缺少目标章节")
                    existing_chapter = await session.scalar(
                        select(Chapter).where(
                            Chapter.id == requested_id,
                            Chapter.novelId == artifact.novel_id,
                        ).with_for_update()
                    )
                    if existing_chapter is None:
                        raise ApiError(
                            status_code=404,
                            code="CHAPTER_NOT_FOUND",
                            message="正文草案目标章节不存在",
                        )
                    check = await lock_consistency_check(session, existing_chapter.id)
                    if check is None:
                        check = ChapterQualityCheck(
                            chapterId=existing_chapter.id,
                            type="consistency",
                            title="一致性终检",
                            status="pending",
                        )
                        session.add(check)
                    await replace_chapter_content(
                        session,
                        existing_chapter,
                        check,
                        content,
                        reopen=True,
                    )
                    chapter_id = existing_chapter.id
                if not (
                    isinstance(target, dict)
                    and target.get("mode") == "existing_chapter"
                ):
                    await _ensure_consistency_check(session, chapter_id)
        return 1

    async def _apply_short_story_chapter(
        self,
        artifact: ApplicableArtifactPort,
        user_id: str,
        content: str,
    ) -> int:
        try:
            draft = ShortStoryChapterDraft.model_validate(artifact.payload)
        except ValidationError as exc:
            raise ApiError(
                status_code=409,
                code="SHORT_STORY_DRAFT_PAYLOAD_INVALID",
                message="中短篇完整正文载荷无效",
            ) from exc
        if content != draft.content:
            raise ApiError(
                status_code=409,
                code="SHORT_STORY_DRAFT_DIRECT_EDIT_FORBIDDEN",
                message="中短篇完整正文只能按当前精确版本应用",
            )
        async with self._session_factory() as session:
            async with session.begin():
                await _require_owner(session, artifact.novel_id, user_id)
                bible = await session.scalar(
                    select(WritingBible)
                    .where(WritingBible.novelId == artifact.novel_id)
                    .with_for_update()
                )
                if (
                    bible is None
                    or bible.storyLengthProfile != "short_medium"
                    or bible.targetTotalWordCount != draft.metadata.targetWordCount
                    or bible.targetTotalWordCount is None
                    or not 6_000 <= bible.targetTotalWordCount <= 80_000
                ):
                    raise ApiError(
                        status_code=409,
                        code="SHORT_STORY_TARGET_MISMATCH",
                        message="中短篇正文目标字数与作品圣经不一致",
                    )
                latest_outline = await session.scalar(
                    select(ReviewArtifact)
                    .where(
                        ReviewArtifact.novelId == artifact.novel_id,
                        ReviewArtifact.kind == "outline_draft",
                    )
                    .order_by(ReviewArtifact.updatedAt.desc(), ReviewArtifact.id.desc())
                    .limit(1)
                    .with_for_update()
                )
                if (
                    latest_outline is None
                    or latest_outline.status != "applied"
                    or latest_outline.id != draft.metadata.sourceOutlineArtifactId
                    or latest_outline.revision != draft.metadata.sourceOutlineRevision
                ):
                    raise ApiError(
                        status_code=409,
                        code="SHORT_STORY_OUTLINE_SOURCE_CHANGED",
                        message="中短篇正文来源大纲已经变化，不能应用旧草案",
                    )
                try:
                    outline = ShortStoryOutlineDraft.model_validate_json(
                        latest_outline.payloadJson
                    )
                except (ValidationError, ValueError):
                    raise ApiError(
                        status_code=409,
                        code="SHORT_STORY_OUTLINE_SOURCE_CHANGED",
                        message="中短篇正文来源大纲载荷无效",
                    ) from None
                if (
                    canonical_short_outline_hash(outline)
                    != draft.metadata.sourceOutlineHash
                ):
                    raise ApiError(
                        status_code=409,
                        code="SHORT_STORY_OUTLINE_SOURCE_CHANGED",
                        message="中短篇正文来源大纲哈希已经变化，不能应用旧草案",
                    )
                chapters = list(
                    (
                        await session.scalars(
                            select(Chapter)
                            .where(Chapter.novelId == artifact.novel_id)
                            .order_by(Chapter.order, Chapter.id)
                            .with_for_update()
                        )
                    ).all()
                )
                if len(chapters) != 1:
                    raise ApiError(
                        status_code=409,
                        code="SHORT_STORY_CHAPTER_INVALID",
                        message="中短篇必须使用唯一正文承载章节",
                    )
                chapter = chapters[0]
                if (
                    chapter.id != artifact.chapter_id
                    or chapter.id != draft.metadata.targetChapterId
                ):
                    raise ApiError(
                        status_code=409,
                        code="SHORT_STORY_TARGET_CHAPTER_MISMATCH",
                        message="中短篇正文目标章节已经变化",
                    )
                if content_sha256(chapter.content) != draft.metadata.baseChapterHash:
                    raise ApiError(
                        status_code=409,
                        code="SHORT_STORY_CHAPTER_BASE_CHANGED",
                        message="中短篇正式正文基线已经变化，不能应用旧草案",
                    )
                actual_count = count_short_story_text_length(draft.content)
                if (
                    actual_count != draft.metadata.actualWordCount
                    or not 6_000 <= actual_count <= 80_000
                ):
                    raise ApiError(
                        status_code=409,
                        code="SHORT_STORY_ACTUAL_WORD_COUNT_INVALID",
                        message="中短篇正文实际字数无效",
                    )
                current_artifact = await session.scalar(
                    select(ReviewArtifact)
                    .where(ReviewArtifact.id == artifact.id)
                    .with_for_update()
                )
                if (
                    current_artifact is None
                    or current_artifact.novelId != artifact.novel_id
                    or current_artifact.chapterId != chapter.id
                    or current_artifact.taskId != artifact.task_id
                    or current_artifact.kind != "chapter_draft"
                    or current_artifact.status != "applying"
                    or current_artifact.revision != artifact.revision
                ):
                    raise ApiError(
                        status_code=409,
                        code="SHORT_STORY_DRAFT_CHANGED",
                        message="中短篇正文草案版本或状态已经变化",
                    )
                try:
                    current_payload = ShortStoryChapterDraft.model_validate_json(
                        current_artifact.payloadJson
                    )
                except (ValidationError, ValueError):
                    raise ApiError(
                        status_code=409,
                        code="SHORT_STORY_DRAFT_CHANGED",
                        message="中短篇正文当前草案载荷无效",
                    ) from None
                if current_payload != draft:
                    raise ApiError(
                        status_code=409,
                        code="SHORT_STORY_DRAFT_CHANGED",
                        message="中短篇正文草案已经变化",
                    )
                evaluations = list(
                    (
                        await session.scalars(
                            select(ReviewArtifactEvaluation).where(
                                ReviewArtifactEvaluation.artifactId == artifact.id,
                                ReviewArtifactEvaluation.revision == artifact.revision,
                                ReviewArtifactEvaluation.evaluatorAgent.in_(("编辑", "校验")),
                            )
                        )
                    ).all()
                )
                by_agent = {item.evaluatorAgent: item for item in evaluations}
                if set(by_agent) != {"编辑", "校验"}:
                    raise ApiError(
                        status_code=409,
                        code="SHORT_STORY_REVIEWS_INCOMPLETE",
                        message="中短篇正文尚未完成编辑和校验两份审核",
                    )
                check = await lock_consistency_check(session, chapter.id)
                if check is None:
                    check = ChapterQualityCheck(
                        chapterId=chapter.id,
                        type="consistency",
                        title="一致性终检",
                        status="pending",
                    )
                    session.add(check)
                await replace_chapter_content(
                    session,
                    chapter,
                    check,
                    draft.content,
                    reopen=True,
                )
                validator = by_agent["校验"]
                if validator.verdict == "pass":
                    check.status = "skipped"
                    check.summary = "已由中短篇全稿审核覆盖"
                    check.result = json.dumps(
                        {
                            "coverage": "short_story_full_review",
                            "artifactId": artifact.id,
                            "artifactRevision": artifact.revision,
                            "validatorEvaluationId": validator.id,
                            "validatorVerdict": validator.verdict,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                else:
                    check.status = "pending"
                    check.summary = None
        return 1

    async def apply_beat_plan(
        self,
        artifact: ApplicableArtifactPort,
        user_id: str,
        beat_plan: dict[str, object],
    ) -> int:
        if artifact.chapter_id is None:
            raise ValueError("章节计划草案缺少目标章节")
        scenes = beat_plan.get("sceneBeats")
        chapter_goal = beat_plan.get("chapterGoal")
        if not isinstance(chapter_goal, str) or not chapter_goal or not isinstance(scenes, list):
            raise ValueError("章节计划草案结构无效")
        async with self._session_factory() as session:
            async with session.begin():
                await _require_owner(session, artifact.novel_id, user_id)
                chapter = await session.scalar(
                    select(Chapter.id).where(
                        Chapter.id == artifact.chapter_id,
                        Chapter.novelId == artifact.novel_id,
                    )
                )
                if chapter is None:
                    raise ApiError(
                        status_code=404,
                        code="CHAPTER_NOT_FOUND",
                        message="章节计划目标章节不存在",
                    )
                await session.execute(
                    update(ChapterBeatPlan)
                    .where(
                        ChapterBeatPlan.chapterId == artifact.chapter_id,
                        ChapterBeatPlan.status == "approved",
                    )
                    .values(status="superseded")
                )
                total = beat_plan.get("totalEstimatedWords")
                plan = ChapterBeatPlan(
                    chapterId=artifact.chapter_id,
                    status="approved",
                    chapterGoal=chapter_goal,
                    mainPlotConnection=_optional_text(beat_plan.get("mainPlotConnection")),
                    chapterAcceptanceCriteria=_optional_text(
                        beat_plan.get("chapterAcceptanceCriteria")
                    ),
                    totalEstimatedWords=(total if isinstance(total, int) else 0),
                )
                session.add(plan)
                await session.flush()
                for index, scene in enumerate(scenes):
                    if not isinstance(scene, dict) or not isinstance(scene.get("goal"), str):
                        raise ValueError("章节计划场景结构无效")
                    characters = scene.get("characters")
                    refs = scene.get("foreshadowingRefs")
                    session.add(
                        SceneBeat(
                            beatPlanId=plan.id,
                            order=(
                                scene["order"] if isinstance(scene.get("order"), int) else index + 1
                            ),
                            goal=scene["goal"],
                            conflict=_optional_text(scene.get("conflict")),
                            characters=json.dumps(
                                characters if isinstance(characters, list) else [],
                                ensure_ascii=False,
                            ),
                            foreshadowingRefs=(
                                json.dumps(refs, ensure_ascii=False)
                                if isinstance(refs, list)
                                else None
                            ),
                            estimatedWords=(
                                scene["estimatedWords"]
                                if isinstance(scene.get("estimatedWords"), int)
                                else 0
                            ),
                            acceptanceCriteria=(
                                scene["acceptanceCriteria"]
                                if isinstance(scene.get("acceptanceCriteria"), str)
                                else scene["goal"]
                            ),
                        )
                    )
        return 1


async def _require_owner(session: AsyncSession, novel_id: str, user_id: str) -> None:
    owner = await session.scalar(select(Novel.userId).where(Novel.id == novel_id).with_for_update())
    if owner != user_id:
        raise ApiError(status_code=403, code="NOVEL_FORBIDDEN", message="无权访问该小说")


async def _ensure_consistency_check(session: AsyncSession, chapter_id: str) -> None:
    existing = await session.scalar(
        select(ChapterQualityCheck.id).where(
            ChapterQualityCheck.chapterId == chapter_id,
            ChapterQualityCheck.type == "consistency",
        )
    )
    if existing is None:
        session.add(
            ChapterQualityCheck(
                chapterId=chapter_id,
                type="consistency",
                title="一致性终检",
                status="pending",
            )
        )


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) else None
