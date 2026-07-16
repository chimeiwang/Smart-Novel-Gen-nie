from __future__ import annotations

import hashlib
import math
from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.base import utc_now
from ..db.models import Chapter, ChapterQualityCheck, WorkflowRun

CONSISTENCY_CHECK_TYPE = "consistency"
QUALITY_SOURCE_CHANGED = "QUALITY_SOURCE_CHANGED"


def is_valid_completed_quality_check(check: ChapterQualityCheck) -> bool:
    score_overall = check.scoreOverall
    return (
        check.status == "completed"
        and isinstance(check.result, str)
        and bool(check.result.strip())
        and isinstance(score_overall, (int, float))
        and not isinstance(score_overall, bool)
        and math.isfinite(score_overall)
        and check.qualityGate in {"pass", "revise"}
    )


def is_handled_quality_check(check: ChapterQualityCheck) -> bool:
    return check.status == "skipped" or is_valid_completed_quality_check(check)


def content_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def next_chapter_updated_at(current: datetime) -> datetime:
    current_naive = (
        current.astimezone(UTC).replace(tzinfo=None)
        if current.tzinfo is not None
        else current
    )
    return max(utc_now(), current_naive + timedelta(milliseconds=1))


async def lock_consistency_check(
    session: AsyncSession,
    chapter_id: str,
) -> ChapterQualityCheck | None:
    return cast(
        ChapterQualityCheck | None,
        await session.scalar(
            select(ChapterQualityCheck)
            .where(
                ChapterQualityCheck.chapterId == chapter_id,
                ChapterQualityCheck.type == CONSISTENCY_CHECK_TYPE,
            )
            .with_for_update()
        ),
    )


async def invalidate_quality_state(
    session: AsyncSession,
    check: ChapterQualityCheck,
) -> None:
    reset_quality_check(check)
    await session.execute(
        update(WorkflowRun)
        .where(
            WorkflowRun.kind == "quality_check",
            WorkflowRun.sourceId == check.id,
            WorkflowRun.status.in_(("pending", "running")),
        )
        .values(
            status="cancelled",
            errorMessage=QUALITY_SOURCE_CHANGED,
            updatedAt=utc_now(),
        )
    )


def reset_quality_check(check: ChapterQualityCheck) -> None:
    check.status = "pending"
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


async def replace_chapter_content(
    session: AsyncSession,
    chapter: Chapter,
    check: ChapterQualityCheck | None,
    content: str,
    *,
    reopen: bool,
) -> bool:
    content_changed = chapter.content != content
    reopen_changed = reopen and (
        chapter.status != "drafting" or chapter.completedAt is not None
    )
    if not content_changed and not reopen_changed:
        return False
    if content_changed:
        chapter.content = content
    if reopen:
        chapter.status = "drafting"
        chapter.completedAt = None
    chapter.updatedAt = next_chapter_updated_at(chapter.updatedAt)
    if content_changed and check is not None:
        await invalidate_quality_state(session, check)
    return content_changed
