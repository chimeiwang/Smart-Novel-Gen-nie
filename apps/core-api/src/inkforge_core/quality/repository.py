from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from inkforge_contracts import ConsistencyQualityReport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..chapters.content_state import (
    QUALITY_SOURCE_CHANGED,
    content_sha256,
    reset_quality_check,
)
from ..db.models import Chapter, ChapterQualityCheck, Novel, WorkflowRun, WritingTask
from ..errors import ApiError
from ..novels.repository import quality_check_dict, utc_datetime
from ..novels.schemas import QualityCheckDto
from .dispatcher import QualityDispatchRecord
from .service import QualityRecordPort


@dataclass(frozen=True, slots=True)
class QualityRecord:
    id: str
    chapter_id: str
    novel_id: str
    type: str
    status: str


@dataclass(frozen=True, slots=True)
class QualityRunInput:
    check_id: str
    source_task_id: str | None
    message: str | None
    chapter_content: str
    chapter_content_sha256: str
    source_updated_at: str


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
                chapter = await self._lock_chapter_owner_for_check(session, check_id, user_id)
                check = await self._lock_check(session, check_id)
                if check is None:
                    raise ApiError(
                        status_code=404, code="QUALITY_CHECK_NOT_FOUND", message="检查项不存在"
                    )
                if chapter.status == "completed":
                    raise ApiError(
                        status_code=409,
                        code="QUALITY_CHECK_CHAPTER_COMPLETED",
                        message="已完成章节不能重置或跳过一致性终检",
                    )
                if await self._find_active_quality_run(session, check_id) is not None:
                    raise ApiError(
                        status_code=409,
                        code="QUALITY_RUN_ACTIVE",
                        message="质量检查运行期间不能修改检查状态",
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
            await self._validate_task_binding(session, record, user_id, task_id)
        return record

    async def create_run(
        self,
        check_id: str,
        user_id: str,
        task_id: str | None,
        message: str | None,
    ) -> QualityDispatchRecord:
        async with self._session_factory() as session:
            async with session.begin():
                chapter = await self._lock_chapter_owner_for_check(
                    session, check_id, user_id
                )
                check = await self._lock_check(session, check_id)
                if check is None:
                    raise ApiError(
                        status_code=404,
                        code="QUALITY_CHECK_NOT_FOUND",
                        message="检查项不存在",
                    )
                if chapter.status != "review":
                    raise ApiError(
                        status_code=409,
                        code="QUALITY_CHECK_CHAPTER_NOT_IN_REVIEW",
                        message="只有待审章节可以运行一致性终检",
                    )
                record = self._record(check, chapter.novelId)
                await self._validate_task_binding(session, record, user_id, task_id)
                active_run = await self._find_active_quality_run(session, check_id)
                if active_run is not None:
                    raise ApiError(
                        status_code=409,
                        code="QUALITY_RUN_ACTIVE",
                        message="质量检查已有运行中的任务",
                    )
                check.status = "running"
                run = WorkflowRun(
                    chapterId=record.chapter_id,
                    novelId=record.novel_id,
                    userId=user_id,
                    kind="quality_check",
                    status="pending",
                    sourceType="quality_check",
                    sourceId=check_id,
                    input=json.dumps(
                        {
                            "checkId": check_id,
                            "sourceTaskId": task_id,
                            "message": message,
                            "chapterContent": chapter.content,
                            "chapterContentSha256": content_sha256(chapter.content),
                            "sourceUpdatedAt": _source_updated_at(chapter.updatedAt),
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                )
                session.add(run)
                await session.flush()
                result = self._dispatch_record(run)
        return result

    async def list_dispatchable_quality_runs(
        self,
        limit: int,
    ) -> list[QualityDispatchRecord]:
        async with self._session_factory() as session:
            async with session.begin():
                runs = list(
                    (
                        await session.scalars(
                            select(WorkflowRun)
                            .where(
                                WorkflowRun.kind == "quality_check",
                                WorkflowRun.status.in_(("pending", "running")),
                            )
                            .order_by(WorkflowRun.updatedAt.asc(), WorkflowRun.id.asc())
                            .limit(limit)
                            .with_for_update(skip_locked=True)
                        )
                    ).all()
                )
                records: list[QualityDispatchRecord] = []
                for run in runs:
                    try:
                        records.append(self._dispatch_record(run))
                    except ValueError:
                        run.status = "failed"
                        run.errorMessage = "QUALITY_RUN_INPUT_INVALID"
        return records

    async def mark_quality_run_running(self, run_id: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                run = await self._lock_quality_run(session, run_id)
                if run.status in {"pending", "running"}:
                    run.status = "running"
                    run.errorMessage = None

    async def record_quality_dispatch_failure(
        self,
        run_id: str,
        error_code: str,
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                run = await self._lock_quality_run(session, run_id)
                if run.status in {"pending", "running"}:
                    run.errorMessage = error_code

    async def get_run_context(
        self,
        check_id: str,
        user_id: str,
        task_id: str | None,
        message: str | None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        if run_id is not None:
            async with self._session_factory() as session:
                async with session.begin():
                    chapter = await self._lock_chapter_owner_for_check(
                        session, check_id, user_id
                    )
                    run = await self._require_bound_quality_run(
                        session,
                        run_id,
                        check_id,
                        user_id,
                        expected_novel_id=None,
                    )
                    durable = self._dispatch_record(run)
                    run_input = self._run_input(run)
                    if (
                        durable.source_task_id != task_id
                        or durable.message != message
                    ):
                        raise ApiError(
                            status_code=409,
                            code="QUALITY_RUN_INPUT_MISMATCH",
                            message="质量检查运行输入与持久记录不匹配",
                        )
                    check = await self._lock_check(session, check_id)
                    if check is None:
                        raise ApiError(
                            status_code=404,
                            code="QUALITY_CHECK_NOT_FOUND",
                            message="检查项不存在",
                        )
                    if run.status not in {"pending", "running"} or not (
                        await self._is_latest_quality_run(session, run)
                    ):
                        raise ApiError(
                            status_code=409,
                            code="QUALITY_RUN_NOT_ACTIVE",
                            message="质量检查运行已不是当前活动任务",
                        )
                    record = self._record(check, chapter.novelId)
                    await self._validate_task_binding(
                        session,
                        record,
                        user_id,
                        durable.source_task_id,
                    )
                    check.status = "running"
                    content = run_input.chapter_content
            return {
                "checkId": check_id,
                "novelId": record.novel_id,
                "chapterId": record.chapter_id,
                "chapterContent": content,
                "message": durable.message or "检查本章一致性",
            }
        authorized_record = await self.authorize_run(check_id, user_id, task_id)
        async with self._session_factory() as session:
            async with session.begin():
                chapter = await self._lock_chapter_owner_for_check(
                    session, check_id, user_id
                )
                check = await self._lock_check(session, check_id)
                if check is None:
                    raise ApiError(
                        status_code=404,
                        code="QUALITY_CHECK_NOT_FOUND",
                        message="检查项不存在",
                    )
                check.status = "running"
                content = chapter.content
        return {
            "checkId": check_id,
            "novelId": authorized_record.novel_id,
            "chapterId": authorized_record.chapter_id,
            "chapterContent": content,
            "message": message or "检查本章一致性",
        }

    async def complete_run(
        self,
        check_id: str,
        user_id: str,
        result: dict[str, Any],
        *,
        run_id: str | None = None,
        novel_id: str | None = None,
    ) -> None:
        report = ConsistencyQualityReport.model_validate(result)
        report_payload = report.model_dump()
        async with self._session_factory() as session:
            async with session.begin():
                chapter = await self._lock_chapter_owner_for_check(session, check_id, user_id)
                workflow_run = (
                    await self._require_bound_quality_run(
                        session,
                        run_id,
                        check_id,
                        user_id,
                        expected_novel_id=novel_id,
                    )
                    if run_id is not None
                    else None
                )
                check = await self._lock_check(session, check_id)
                if check is None:
                    raise ApiError(
                        status_code=404,
                        code="QUALITY_CHECK_NOT_FOUND",
                        message="检查项不存在",
                    )
                if workflow_run is not None and workflow_run.status in {
                    "completed",
                    "failed",
                    "cancelled",
                }:
                    return
                run_input = self._run_input(workflow_run) if workflow_run is not None else None
                is_latest = workflow_run is None or await self._is_latest_quality_run(
                    session, workflow_run
                )
                if workflow_run is not None:
                    if (
                        run_input is not None
                        and content_sha256(chapter.content)
                        != run_input.chapter_content_sha256
                    ):
                        workflow_run.status = "cancelled"
                        workflow_run.output = json.dumps(
                            report_payload,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                        workflow_run.errorMessage = QUALITY_SOURCE_CHANGED
                        if is_latest:
                            reset_quality_check(check)
                        return
                    workflow_run.status = "completed"
                    workflow_run.output = json.dumps(
                        report_payload,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    workflow_run.errorMessage = None
                if not is_latest:
                    return
                check.status = "completed"
                check.result = report.report
                check.scoreHook = None
                check.scoreTension = None
                check.scorePayoff = None
                check.scorePacing = None
                check.scoreEndingHook = None
                check.scoreReaderPromise = None
                scores = report.scores
                check.scoreOverall = _score(
                    (
                        scores.characterConsistency
                        + scores.worldRuleConsistency
                        + scores.timelineConsistency
                        + scores.causalityConsistency
                        + scores.foreshadowingConsistency
                    )
                    / 5
                )
                check.qualityGate = report.qualityGate
                check.rewriteBrief = report.rewriteBrief

    async def fail_run(
        self,
        check_id: str,
        user_id: str,
        *,
        run_id: str | None = None,
        novel_id: str | None = None,
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                chapter = await self._lock_chapter_owner_for_check(session, check_id, user_id)
                workflow_run = (
                    await self._require_bound_quality_run(
                        session,
                        run_id,
                        check_id,
                        user_id,
                        expected_novel_id=novel_id,
                    )
                    if run_id is not None
                    else None
                )
                check = await self._lock_check(session, check_id)
                if check is None:
                    raise ApiError(
                        status_code=404,
                        code="QUALITY_CHECK_NOT_FOUND",
                        message="检查项不存在",
                    )
                if workflow_run is not None and workflow_run.status in {
                    "completed",
                    "failed",
                    "cancelled",
                }:
                    return
                run_input = self._run_input(workflow_run) if workflow_run is not None else None
                is_latest = workflow_run is None or await self._is_latest_quality_run(
                    session, workflow_run
                )
                if workflow_run is not None:
                    if (
                        run_input is not None
                        and content_sha256(chapter.content)
                        != run_input.chapter_content_sha256
                    ):
                        workflow_run.status = "cancelled"
                        workflow_run.errorMessage = QUALITY_SOURCE_CHANGED
                        if is_latest:
                            reset_quality_check(check)
                        return
                    workflow_run.status = "failed"
                    workflow_run.errorMessage = "QUALITY_RUN_FAILED"
                if is_latest:
                    check.status = "failed"

    async def _validate_task_binding(
        self,
        session: AsyncSession,
        record: QualityRecord,
        user_id: str,
        task_id: str | None,
    ) -> None:
        if task_id is None:
            return
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

    async def _lock_quality_run(
        self,
        session: AsyncSession,
        run_id: str,
    ) -> WorkflowRun:
        run = cast(
            WorkflowRun | None,
            await session.scalar(
                select(WorkflowRun)
                .where(
                    WorkflowRun.id == run_id,
                    WorkflowRun.kind == "quality_check",
                )
                .with_for_update()
            ),
        )
        if run is None:
            raise ApiError(
                status_code=404,
                code="QUALITY_RUN_NOT_FOUND",
                message="质量检查运行不存在",
            )
        return run

    async def _find_active_quality_run(
        self,
        session: AsyncSession,
        check_id: str,
    ) -> WorkflowRun | None:
        return cast(
            WorkflowRun | None,
            await session.scalar(
                select(WorkflowRun)
                .where(
                    WorkflowRun.kind == "quality_check",
                    WorkflowRun.sourceId == check_id,
                    WorkflowRun.status.in_(("pending", "running")),
                )
                .order_by(WorkflowRun.createdAt.asc(), WorkflowRun.id.asc())
                .limit(1)
            ),
        )

    async def _is_latest_quality_run(
        self,
        session: AsyncSession,
        run: WorkflowRun,
    ) -> bool:
        latest_run_id = await session.scalar(
            select(WorkflowRun.id)
            .where(
                WorkflowRun.kind == "quality_check",
                WorkflowRun.sourceId == run.sourceId,
            )
            .order_by(WorkflowRun.createdAt.desc(), WorkflowRun.id.desc())
            .limit(1)
        )
        return latest_run_id == run.id

    async def _require_bound_quality_run(
        self,
        session: AsyncSession,
        run_id: str,
        check_id: str,
        user_id: str,
        *,
        expected_novel_id: str | None,
    ) -> WorkflowRun:
        run = await self._lock_quality_run(session, run_id)
        if (
            run.userId != user_id
            or run.sourceId != check_id
            or (expected_novel_id is not None and run.novelId != expected_novel_id)
        ):
            raise ApiError(
                status_code=403,
                code="QUALITY_RUN_MISMATCH",
                message="质量检查运行资源绑定不匹配",
            )
        self._dispatch_record(run)
        return run

    @staticmethod
    def _dispatch_record(run: WorkflowRun) -> QualityDispatchRecord:
        payload = QualityRepository._run_input(run)
        if run.userId is None or run.sourceId is None:
            raise ValueError("质量检查运行归属无效")
        return QualityDispatchRecord(
            run_id=run.id,
            check_id=run.sourceId,
            user_id=run.userId,
            novel_id=run.novelId,
            chapter_id=run.chapterId,
            source_task_id=payload.source_task_id,
            message=payload.message,
        )

    @staticmethod
    def _run_input(run: WorkflowRun) -> QualityRunInput:
        try:
            payload = json.loads(run.input or "")
        except json.JSONDecodeError as exc:
            raise ValueError("质量检查运行输入无效") from exc
        if (
            run.sourceId is None
            or not isinstance(payload, dict)
            or payload.get("checkId") != run.sourceId
        ):
            raise ValueError("质量检查运行输入无效")
        source_task_id = payload.get("sourceTaskId")
        message = payload.get("message")
        chapter_content = payload.get("chapterContent")
        chapter_content_hash = payload.get("chapterContentSha256")
        source_updated_at = payload.get("sourceUpdatedAt")
        if source_task_id is not None and not isinstance(source_task_id, str):
            raise ValueError("质量检查源任务无效")
        if message is not None and not isinstance(message, str):
            raise ValueError("质量检查消息无效")
        if not isinstance(chapter_content, str):
            raise ValueError("质量检查正文快照无效")
        if (
            not isinstance(chapter_content_hash, str)
            or chapter_content_hash != content_sha256(chapter_content)
        ):
            raise ValueError("质量检查正文哈希无效")
        if not isinstance(source_updated_at, str) or not source_updated_at:
            raise ValueError("质量检查正文版本无效")
        return QualityRunInput(
            check_id=run.sourceId,
            source_task_id=source_task_id,
            message=message,
            chapter_content=chapter_content,
            chapter_content_sha256=chapter_content_hash,
            source_updated_at=source_updated_at,
        )

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


def _score(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return round(float(value))


def _source_updated_at(value: object) -> str:
    if not isinstance(value, datetime):
        raise RuntimeError("章节更新时间缺失")
    normalized = utc_datetime(value)
    if normalized is None:
        raise RuntimeError("章节更新时间缺失")
    return normalized.isoformat()
