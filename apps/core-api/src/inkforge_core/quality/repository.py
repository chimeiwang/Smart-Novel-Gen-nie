from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..db.models import Chapter, ChapterQualityCheck, Novel, WritingTask
from ..errors import ApiError
from ..novels.repository import quality_check_dict
from ..novels.schemas import QualityCheckDto
from .service import QualityRecordPort


@dataclass(frozen=True, slots=True)
class QualityRecord:
    id: str
    chapter_id: str
    novel_id: str
    type: str
    status: str


class QualityRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def require_check(self, check_id: str, user_id: str) -> QualityRecordPort:
        async with self._session_factory() as session:
            check, novel_id = await self._require_check(session, check_id, user_id)
        return self._record(check, novel_id)

    async def get_check(self, check_id: str, user_id: str) -> QualityCheckDto:
        async with self._session_factory() as session:
            check, _ = await self._require_check(session, check_id, user_id)
        return QualityCheckDto.model_validate(quality_check_dict(check))

    async def update_public_status(
        self, check_id: str, user_id: str, status: str, reset_result: bool
    ) -> QualityCheckDto:
        async with self._session_factory() as session:
            async with session.begin():
                await self._lock_chapter_owner_for_check(session, check_id, user_id)
                check = await self._lock_check(session, check_id)
                if check is None:
                    raise ApiError(
                        status_code=404, code="QUALITY_CHECK_NOT_FOUND", message="检查项不存在"
                    )
                check.status = status
                if reset_result:
                    check.result = None
                    check.scoreHook = None
                    check.scoreTension = None
                    check.scorePayoff = None
                    check.scorePacing = None
                    check.scoreEndingHook = None
                    check.scoreReaderPromise = None
                    check.scoreOverall = None
                    check.qualityGate = None
                    check.rewriteBrief = None
                await session.flush()
                result = QualityCheckDto.model_validate(quality_check_dict(check))
        return result

    async def authorize_run(
        self, check_id: str, user_id: str, task_id: str | None
    ) -> QualityRecordPort:
        async with self._session_factory() as session:
            check, novel_id = await self._require_check(session, check_id, user_id)
            record = self._record(check, novel_id)
            if task_id is None:
                return record
            row = (
                await session.execute(
                    select(WritingTask, Novel.userId)
                    .join(Novel, Novel.id == WritingTask.novelId)
                    .where(WritingTask.id == task_id)
                )
            ).one_or_none()
            if row is None:
                raise self._task_mismatch()
            task, owner_id = row
            if (
                owner_id is None
                or owner_id != user_id
                or task.novelId != record.novel_id
                or task.chapterId != record.chapter_id
            ):
                raise self._task_mismatch()
        return record

    async def _lock_chapter_owner_for_check(
        self, session: AsyncSession, check_id: str, user_id: str
    ) -> Chapter:
        row = (
            await session.execute(
                select(Chapter, Novel.userId)
                .join(ChapterQualityCheck, ChapterQualityCheck.chapterId == Chapter.id)
                .join(Novel, Novel.id == Chapter.novelId)
                .where(ChapterQualityCheck.id == check_id)
                .with_for_update(of=Chapter)
            )
        ).one_or_none()
        if row is None:
            raise ApiError(
                status_code=404,
                code="QUALITY_CHECK_NOT_FOUND",
                message="检查项不存在",
            )
        chapter = cast(Chapter, row[0])
        owner_id = cast(str | None, row[1])
        if owner_id is None or owner_id != user_id:
            raise ApiError(
                status_code=403,
                code="QUALITY_CHECK_FORBIDDEN",
                message="无权访问该检查项",
            )
        return chapter

    async def _lock_check(self, session: AsyncSession, check_id: str) -> ChapterQualityCheck | None:
        return cast(
            ChapterQualityCheck | None,
            await session.scalar(
                select(ChapterQualityCheck)
                .where(ChapterQualityCheck.id == check_id)
                .with_for_update()
            ),
        )

    async def _require_check(
        self, session: AsyncSession, check_id: str, user_id: str
    ) -> tuple[ChapterQualityCheck, str]:
        row = (
            await session.execute(
                select(ChapterQualityCheck, Novel.userId, Chapter.novelId)
                .join(Chapter, Chapter.id == ChapterQualityCheck.chapterId)
                .join(Novel, Novel.id == Chapter.novelId)
                .where(ChapterQualityCheck.id == check_id)
            )
        ).one_or_none()
        if row is None:
            raise ApiError(status_code=404, code="QUALITY_CHECK_NOT_FOUND", message="检查项不存在")
        check = cast(ChapterQualityCheck, row[0])
        owner_id = cast(str | None, row[1])
        novel_id = cast(str, row[2])
        if owner_id is None or owner_id != user_id:
            raise ApiError(
                status_code=403, code="QUALITY_CHECK_FORBIDDEN", message="无权访问该检查项"
            )
        return check, novel_id

    @staticmethod
    def _record(check: ChapterQualityCheck, novel_id: str) -> QualityRecord:
        return QualityRecord(
            id=check.id,
            chapter_id=check.chapterId,
            novel_id=novel_id,
            type=check.type,
            status=check.status,
        )

    @staticmethod
    def _task_mismatch() -> ApiError:
        return ApiError(
            status_code=403,
            code="QUALITY_TASK_MISMATCH",
            message="任务与检查项不匹配",
        )
