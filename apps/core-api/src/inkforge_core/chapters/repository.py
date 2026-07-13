from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..db.base import utc_now
from ..db.models import (
    Chapter,
    ChapterBeatPlan,
    ChapterProgress,
    ChapterQualityCheck,
    Novel,
    SceneBeat,
)
from ..errors import ApiError
from ..novels.repository import chapter_dict, utc_datetime
from ..novels.schemas import ChapterStatus, WorkspaceChapter
from .service import ChapterRecordPort

DEFAULT_QUALITY_TYPE = "consistency"
DEFAULT_QUALITY_TITLE = "一致性终检"
DEFAULT_QUALITY_SUMMARY = "最终检查正文与设定的一致性、角色 OOC、伏笔回收、逻辑矛盾"


@dataclass(frozen=True, slots=True)
class ChapterRecord:
    id: str
    novel_id: str
    status: ChapterStatus
    completed_at: datetime | None


class ChapterRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def require_chapter(
        self, chapter_id: str, user_id: str, *, lock: bool = False
    ) -> ChapterRecordPort:
        async with self._session_factory() as session:
            return await self._require_chapter(session, chapter_id, user_id, lock=lock)

    async def create_chapter(self, novel_id: str, user_id: str) -> WorkspaceChapter:
        async with self._session_factory() as session:
            async with session.begin():
                statement = select(Novel).where(Novel.id == novel_id).with_for_update()
                novel = await session.scalar(statement)
                if novel is None:
                    raise ApiError(status_code=404, code="NOVEL_NOT_FOUND", message="小说不存在")
                if novel.userId is None or novel.userId != user_id:
                    raise ApiError(
                        status_code=403, code="NOVEL_FORBIDDEN", message="无权访问该小说"
                    )
                current_order = await session.scalar(
                    select(func.max(Chapter.order)).where(Chapter.novelId == novel_id)
                )
                next_order = (current_order or 0) + 1
                chapter = Chapter(
                    novelId=novel_id,
                    title=f"第 {next_order} 章",
                    order=next_order,
                    content="",
                    status="drafting",
                )
                session.add(chapter)
                await session.flush()
                result = self._empty_chapter(chapter)
        return WorkspaceChapter.model_validate(result)

    async def list_chapters(self, novel_id: str, user_id: str) -> list[WorkspaceChapter]:
        async with self._session_factory() as session:
            await self._require_novel(session, novel_id, user_id)
            chapters = list(
                (
                    await session.scalars(
                        select(Chapter)
                        .where(Chapter.novelId == novel_id)
                        .order_by(Chapter.order.asc(), Chapter.id.asc())
                    )
                ).all()
            )
            return await self._load_chapters(session, chapters)

    async def get_chapter(self, chapter_id: str, user_id: str) -> WorkspaceChapter:
        async with self._session_factory() as session:
            await self._require_chapter(session, chapter_id, user_id)
            chapter = await session.get(Chapter, chapter_id)
            if chapter is None:
                raise ApiError(status_code=404, code="CHAPTER_NOT_FOUND", message="章节不存在")
            values = await self._load_chapters(session, [chapter])
        return values[0]

    async def update_draft(
        self, chapter_id: str, user_id: str, title: str, content: str
    ) -> datetime:
        async with self._session_factory() as session:
            async with session.begin():
                await self._require_chapter(session, chapter_id, user_id, lock=True)
                chapter = await session.get(Chapter, chapter_id, with_for_update=True)
                if chapter is None:
                    raise ApiError(status_code=404, code="CHAPTER_NOT_FOUND", message="章节不存在")
                chapter.title = title
                chapter.content = content
                await session.flush()
                updated_at = utc_datetime(chapter.updatedAt)
        if updated_at is None:
            raise RuntimeError("章节更新时间缺失")
        return updated_at

    async def upsert_progress(self, chapter_id: str, user_id: str, content: str) -> datetime:
        async with self._session_factory() as session:
            async with session.begin():
                await self._require_chapter(session, chapter_id, user_id, lock=True)
                progress = await session.scalar(
                    select(ChapterProgress)
                    .where(ChapterProgress.chapterId == chapter_id)
                    .with_for_update()
                )
                if progress is None:
                    progress = ChapterProgress(chapterId=chapter_id, content=content)
                    session.add(progress)
                else:
                    progress.content = content
                await session.flush()
                updated_at = utc_datetime(progress.updatedAt)
        if updated_at is None:
            raise RuntimeError("章节进展更新时间缺失")
        return updated_at

    async def transition_status(
        self, chapter_id: str, user_id: str, status: ChapterStatus
    ) -> ChapterRecordPort:
        async with self._session_factory() as session:
            async with session.begin():
                chapter = await self._lock_chapter_owner(session, chapter_id, user_id)
                allowed = {
                    "drafting": {"drafting", "review"},
                    "review": {"drafting", "review", "completed"},
                    "completed": {"drafting", "review", "completed"},
                }
                if status not in allowed.get(chapter.status, set()):
                    raise ApiError(
                        status_code=409,
                        code="INVALID_CHAPTER_STATUS_TRANSITION",
                        message="章节状态不能这样切换",
                    )
                check = await self._lock_consistency_check(session, chapter_id)
                if status == "completed" and (
                    check is None or check.status not in {"completed", "skipped"}
                ):
                    raise ApiError(
                        status_code=409,
                        code="QUALITY_CHECK_REQUIRED",
                        message="一致性终检完成或跳过后，才能标记章节完成",
                    )
                if status == "review":
                    if check is None:
                        check = ChapterQualityCheck(
                            chapterId=chapter_id,
                            type=DEFAULT_QUALITY_TYPE,
                            title=DEFAULT_QUALITY_TITLE,
                            summary=DEFAULT_QUALITY_SUMMARY,
                            status="pending",
                        )
                        session.add(check)
                    else:
                        check.title = DEFAULT_QUALITY_TITLE
                        check.summary = DEFAULT_QUALITY_SUMMARY
                chapter.status = status
                chapter.completedAt = (
                    chapter.completedAt or utc_now() if status == "completed" else None
                )
                await session.flush()
                result = self._record(chapter)
        return result

    async def _lock_consistency_check(
        self, session: AsyncSession, chapter_id: str
    ) -> ChapterQualityCheck | None:
        return cast(
            ChapterQualityCheck | None,
            await session.scalar(
                select(ChapterQualityCheck)
                .where(
                    ChapterQualityCheck.chapterId == chapter_id,
                    ChapterQualityCheck.type == DEFAULT_QUALITY_TYPE,
                )
                .with_for_update()
            ),
        )

    async def _lock_chapter_owner(
        self, session: AsyncSession, chapter_id: str, user_id: str
    ) -> Chapter:
        row = (
            await session.execute(
                select(Chapter, Novel.userId)
                .join(Novel, Novel.id == Chapter.novelId)
                .where(Chapter.id == chapter_id)
                .with_for_update(of=Chapter)
            )
        ).one_or_none()
        if row is None:
            raise ApiError(status_code=404, code="CHAPTER_NOT_FOUND", message="章节不存在")
        chapter = cast(Chapter, row[0])
        owner_id = cast(str | None, row[1])
        if owner_id is None or owner_id != user_id:
            raise ApiError(status_code=403, code="CHAPTER_FORBIDDEN", message="无权访问该章节")
        return chapter

    async def _load_chapters(
        self, session: AsyncSession, chapters: list[Chapter]
    ) -> list[WorkspaceChapter]:
        ids = [chapter.id for chapter in chapters]
        if not ids:
            return []
        progresses = list(
            (
                await session.scalars(
                    select(ChapterProgress).where(ChapterProgress.chapterId.in_(ids))
                )
            ).all()
        )
        checks = list(
            (
                await session.scalars(
                    select(ChapterQualityCheck)
                    .where(ChapterQualityCheck.chapterId.in_(ids))
                    .order_by(ChapterQualityCheck.createdAt.asc(), ChapterQualityCheck.id.asc())
                )
            ).all()
        )
        plans = list(
            (
                await session.scalars(
                    select(ChapterBeatPlan)
                    .where(ChapterBeatPlan.chapterId.in_(ids), ChapterBeatPlan.status == "approved")
                    .order_by(ChapterBeatPlan.updatedAt.desc(), ChapterBeatPlan.id.asc())
                )
            ).all()
        )
        latest: dict[str, ChapterBeatPlan] = {}
        for plan in plans:
            latest.setdefault(plan.chapterId, plan)
        plan_ids = [plan.id for plan in latest.values()]
        beats = (
            list(
                (
                    await session.scalars(
                        select(SceneBeat)
                        .where(SceneBeat.beatPlanId.in_(plan_ids))
                        .order_by(SceneBeat.order.asc(), SceneBeat.id.asc())
                    )
                ).all()
            )
            if plan_ids
            else []
        )
        progress_by_chapter = {item.chapterId: item for item in progresses}
        checks_by_chapter: dict[str, list[ChapterQualityCheck]] = defaultdict(list)
        beats_by_plan: dict[str, list[SceneBeat]] = defaultdict(list)
        for check in checks:
            checks_by_chapter[check.chapterId].append(check)
        for beat in beats:
            beats_by_plan[beat.beatPlanId].append(beat)
        return [
            WorkspaceChapter.model_validate(
                chapter_dict(
                    chapter,
                    progress_by_chapter.get(chapter.id),
                    checks_by_chapter[chapter.id],
                    latest.get(chapter.id),
                    beats_by_plan[latest[chapter.id].id] if chapter.id in latest else [],
                )
            )
            for chapter in chapters
        ]

    async def _require_novel(self, session: AsyncSession, novel_id: str, user_id: str) -> Novel:
        novel = await session.get(Novel, novel_id)
        if novel is None:
            raise ApiError(status_code=404, code="NOVEL_NOT_FOUND", message="小说不存在")
        if novel.userId is None or novel.userId != user_id:
            raise ApiError(status_code=403, code="NOVEL_FORBIDDEN", message="无权访问该小说")
        return novel

    async def _require_chapter(
        self, session: AsyncSession, chapter_id: str, user_id: str, *, lock: bool = False
    ) -> ChapterRecord:
        statement = (
            select(Chapter, Novel.userId)
            .join(Novel, Novel.id == Chapter.novelId)
            .where(Chapter.id == chapter_id)
        )
        if lock:
            statement = statement.with_for_update(of=Chapter)
        row = (await session.execute(statement)).one_or_none()
        if row is None:
            raise ApiError(status_code=404, code="CHAPTER_NOT_FOUND", message="章节不存在")
        chapter, owner_id = row
        if owner_id is None or owner_id != user_id:
            raise ApiError(status_code=403, code="CHAPTER_FORBIDDEN", message="无权访问该章节")
        return self._record(chapter)

    @staticmethod
    def _record(chapter: Chapter) -> ChapterRecord:
        return ChapterRecord(
            id=chapter.id,
            novel_id=chapter.novelId,
            status=cast(ChapterStatus, chapter.status),
            completed_at=utc_datetime(chapter.completedAt),
        )

    @staticmethod
    def _empty_chapter(chapter: Chapter) -> dict[str, object]:
        return chapter_dict(chapter, None, [], None, [])
