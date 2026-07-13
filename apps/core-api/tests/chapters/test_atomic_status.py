from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from inkforge_core.chapters.repository import ChapterRepository
from inkforge_core.db.models import Chapter, ChapterQualityCheck
from inkforge_core.quality.repository import QualityRepository


def chapter(status: str = "review") -> Chapter:
    now = datetime(2026, 7, 11, tzinfo=UTC)
    return Chapter(
        id="chapter-1",
        novelId="novel-1",
        title="第一章",
        order=1,
        content="正文",
        status=status,
        completedAt=None,
        createdAt=now,
        updatedAt=now,
    )


def quality_check(status: str = "pending") -> ChapterQualityCheck:
    now = datetime(2026, 7, 11, tzinfo=UTC)
    return ChapterQualityCheck(
        id="check-1",
        chapterId="chapter-1",
        type="consistency",
        status=status,
        title="一致性终检",
        summary=None,
        result=None,
        createdAt=now,
        updatedAt=now,
    )


class RecordingSession:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.added: list[object] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback

    @asynccontextmanager
    async def begin(self):
        self.events.append("事务开始")
        try:
            yield
        finally:
            self.events.append("事务结束")

    def add(self, value: object) -> None:
        self.added.append(value)
        self.events.append("新增默认检查")

    async def flush(self) -> None:
        self.events.append("写入")


class RecordingChapterRepository(ChapterRepository):
    def __init__(
        self,
        session: RecordingSession,
        chapter_value: Chapter,
        check_value: ChapterQualityCheck | None,
    ) -> None:
        super().__init__(lambda: session)  # type: ignore[arg-type]
        self._chapter_value = chapter_value
        self._check_value = check_value

    async def _lock_chapter_owner(self, session, chapter_id: str, user_id: str):
        del chapter_id, user_id
        session.events.append("锁章节和所有者")
        return self._chapter_value

    async def _lock_consistency_check(self, session, chapter_id: str):
        del chapter_id
        session.events.append("锁质量检查")
        return self._check_value


@pytest.mark.asyncio
async def test_status_transition_uses_one_transaction_and_fixed_lock_order() -> None:
    events: list[str] = []
    session = RecordingSession(events)
    repository = RecordingChapterRepository(session, chapter("completed"), None)
    result = await repository.transition_status("chapter-1", "user-1", "review")
    assert result.status == "review"
    assert events == [
        "事务开始",
        "锁章节和所有者",
        "锁质量检查",
        "新增默认检查",
        "写入",
        "事务结束",
    ]


class RecordingQualityRepository(QualityRepository):
    def __init__(
        self,
        session: RecordingSession,
        chapter_value: Chapter,
        check_value: ChapterQualityCheck,
    ) -> None:
        super().__init__(lambda: session)  # type: ignore[arg-type]
        self._chapter_value = chapter_value
        self._check_value = check_value

    async def _lock_chapter_owner_for_check(self, session, check_id: str, user_id: str):
        del check_id, user_id
        session.events.append("锁章节和所有者")
        return self._chapter_value

    async def _lock_check(self, session, check_id: str):
        del check_id
        session.events.append("锁质量检查")
        return self._check_value


@pytest.mark.asyncio
async def test_quality_patch_uses_same_transaction_and_lock_order() -> None:
    events: list[str] = []
    session = RecordingSession(events)
    check = quality_check("pending")
    repository = RecordingQualityRepository(session, chapter(), check)
    result = await repository.update_public_status("check-1", "user-1", "skipped", False)
    assert result.status == "skipped"
    assert events == [
        "事务开始",
        "锁章节和所有者",
        "锁质量检查",
        "写入",
        "事务结束",
    ]


class SharedLockState:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.chapter = chapter("review")
        self.check = quality_check("pending")
        self.quality_has_chapter_lock = asyncio.Event()
        self.allow_quality_to_continue = asyncio.Event()


class LockSession:
    def __init__(self, shared: SharedLockState) -> None:
        self.shared = shared
        self.holds_chapter_lock = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback

    @asynccontextmanager
    async def begin(self):
        try:
            yield
        finally:
            if self.holds_chapter_lock:
                self.shared.lock.release()
                self.holds_chapter_lock = False

    async def flush(self) -> None:
        return None


class InterleavingChapterRepository(ChapterRepository):
    def __init__(self, shared: SharedLockState) -> None:
        self.shared = shared
        super().__init__(lambda: LockSession(shared))  # type: ignore[arg-type]

    async def _lock_chapter_owner(self, session: LockSession, chapter_id: str, user_id: str):
        del chapter_id, user_id
        await self.shared.lock.acquire()
        session.holds_chapter_lock = True
        return self.shared.chapter

    async def _lock_consistency_check(self, session, chapter_id: str):
        del session, chapter_id
        return self.shared.check


class InterleavingQualityRepository(QualityRepository):
    def __init__(self, shared: SharedLockState) -> None:
        self.shared = shared
        super().__init__(lambda: LockSession(shared))  # type: ignore[arg-type]

    async def _lock_chapter_owner_for_check(
        self, session: LockSession, check_id: str, user_id: str
    ):
        del check_id, user_id
        await self.shared.lock.acquire()
        session.holds_chapter_lock = True
        self.shared.quality_has_chapter_lock.set()
        return self.shared.chapter

    async def _lock_check(self, session, check_id: str):
        del session, check_id
        await self.shared.allow_quality_to_continue.wait()
        return self.shared.check


@pytest.mark.asyncio
async def test_quality_patch_and_completion_cannot_interleave_between_locks() -> None:
    shared = SharedLockState()
    quality_repository = InterleavingQualityRepository(shared)
    chapter_repository = InterleavingChapterRepository(shared)

    quality_task = asyncio.create_task(
        quality_repository.update_public_status("check-1", "user-1", "skipped", False)
    )
    await shared.quality_has_chapter_lock.wait()
    completion_task = asyncio.create_task(
        chapter_repository.transition_status("chapter-1", "user-1", "completed")
    )
    await asyncio.sleep(0)
    assert completion_task.done() is False

    shared.allow_quality_to_continue.set()
    await quality_task
    completed = await completion_task
    assert shared.check.status == "skipped"
    assert completed.status == "completed"
    assert completed.completed_at is not None
    assert shared.chapter.completedAt is not None
    assert shared.chapter.completedAt.tzinfo is None


class ScalarRows:
    def __init__(self, values: list[object]) -> None:
        self._values = values

    def all(self) -> list[object]:
        return self._values


class CountingCheck:
    chapter_id_reads = 0

    def __init__(self, index: int) -> None:
        now = datetime(2026, 7, 11, tzinfo=UTC)
        self.id = f"check-{index}"
        self._chapter_id = f"chapter-{index}"
        self.type = "consistency"
        self.status = "pending"
        self.title = "一致性终检"
        self.summary = None
        self.result = None
        self.scoreHook = None
        self.scoreTension = None
        self.scorePayoff = None
        self.scorePacing = None
        self.scoreEndingHook = None
        self.scoreReaderPromise = None
        self.scoreOverall = None
        self.qualityGate = None
        self.rewriteBrief = None
        self.createdAt = now
        self.updatedAt = now

    @property
    def chapterId(self) -> str:
        type(self).chapter_id_reads += 1
        return self._chapter_id


class AggregateSession:
    def __init__(self, checks: list[CountingCheck]) -> None:
        self.checks = checks

    async def scalars(self, statement):
        entity = statement.column_descriptions[0].get("entity")
        return ScalarRows(self.checks if entity is ChapterQualityCheck else [])


def many_chapters(count: int) -> list[Chapter]:
    now = datetime(2026, 7, 11, tzinfo=UTC)
    return [
        Chapter(
            id=f"chapter-{index}",
            novelId="novel-1",
            title=f"第 {index} 章",
            order=index,
            content="正文",
            status="drafting",
            completedAt=None,
            createdAt=now,
            updatedAt=now,
        )
        for index in range(count)
    ]


@pytest.mark.asyncio
async def test_chapter_aggregation_scales_linearly_with_related_rows() -> None:
    repository = ChapterRepository(lambda: None)  # type: ignore[arg-type]

    async def reads_for(size: int) -> int:
        CountingCheck.chapter_id_reads = 0
        checks = [CountingCheck(index) for index in range(size)]
        result = await repository._load_chapters(  # type: ignore[arg-type]
            AggregateSession(checks), many_chapters(size)
        )
        assert len(result) == size
        return CountingCheck.chapter_id_reads

    small_reads = await reads_for(10)
    large_reads = await reads_for(1_000)
    assert large_reads <= small_reads * 110
