from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..db.models import Chapter, ChapterQualityCheck, Novel
from ..errors import ApiError
from ..novels.repository import quality_check_dict
from ..novels.schemas import QualityCheckDto
from .service import QualityRecordPort


@dataclass(frozen=True, slots=True)
class QualityRecord:
    id: str
    chapter_id: str
    type: str
    status: str


class QualityRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def require_check(self, check_id: str, user_id: str) -> QualityRecordPort:
        async with self._session_factory() as session:
            check = await self._require_check(session, check_id, user_id)
        return self._record(check)

    async def get_check(self, check_id: str, user_id: str) -> QualityCheckDto:
        async with self._session_factory() as session:
            check = await self._require_check(session, check_id, user_id)
        return QualityCheckDto.model_validate(quality_check_dict(check))

    async def update_public_status(
        self, check_id: str, user_id: str, status: str, reset_result: bool
    ) -> QualityRecordPort:
        async with self._session_factory() as session:
            async with session.begin():
                await self._require_check(session, check_id, user_id)
                check = await session.get(ChapterQualityCheck, check_id, with_for_update=True)
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
                result = self._record(check)
        return result

    async def _require_check(
        self, session: AsyncSession, check_id: str, user_id: str
    ) -> ChapterQualityCheck:
        row = (
            await session.execute(
                select(ChapterQualityCheck, Novel.userId)
                .join(Chapter, Chapter.id == ChapterQualityCheck.chapterId)
                .join(Novel, Novel.id == Chapter.novelId)
                .where(ChapterQualityCheck.id == check_id)
            )
        ).one_or_none()
        if row is None:
            raise ApiError(status_code=404, code="QUALITY_CHECK_NOT_FOUND", message="检查项不存在")
        check = cast(ChapterQualityCheck, row[0])
        owner_id = cast(str | None, row[1])
        if owner_id is None or owner_id != user_id:
            raise ApiError(
                status_code=403, code="QUALITY_CHECK_FORBIDDEN", message="无权访问该检查项"
            )
        return check

    @staticmethod
    def _record(check: ChapterQualityCheck) -> QualityRecord:
        return QualityRecord(
            id=check.id,
            chapter_id=check.chapterId,
            type=check.type,
            status=check.status,
        )
