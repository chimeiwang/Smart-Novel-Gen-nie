from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
import pytest
from inkforge_contracts import ConsistencyQualityReport
from inkforge_core.app import create_app
from inkforge_core.auth.dependencies import get_current_user
from inkforge_core.auth.repository import AuthUser
from inkforge_core.errors import ApiError
from inkforge_core.novels.schemas import QualityCheckDto
from inkforge_core.quality.dispatcher import QualityDispatchRecord
from inkforge_core.quality.schemas import (
    QualityRunSuccessRequest,
    RunQualityCheckRequest,
    UpdateQualityCheckRequest,
)
from inkforge_core.quality.service import QualityService
from pydantic import ValidationError


def valid_quality_report(**overrides: object) -> dict[str, object]:
    report: dict[str, object] = {
        "scores": {
            "characterConsistency": 81.0,
            "worldRuleConsistency": 82.0,
            "timelineConsistency": 83.0,
            "causalityConsistency": 84.0,
            "foreshadowingConsistency": 88.0,
        },
        "qualityGate": "revise",
        "issues": [
            {
                "dimension": "timeline",
                "severity": "warning",
                "message": "时间顺序需要核对",
                "evidence": "第二幕早于第一幕结尾",
                "location": "第二幕开头",
                "suggestion": "统一日期",
            }
        ],
        "report": "完整一致性报告",
        "rewriteBrief": "修正时间线",
    }
    report.update(overrides)
    return report


@dataclass
class QualityRecord:
    id: str = "check-1"
    chapter_id: str = "chapter-1"
    novel_id: str = "novel-1"
    type: str = "consistency"
    status: str = "pending"


class RecordingQualityRepository:
    def __init__(self) -> None:
        self.record = QualityRecord()
        self.updated = False
        self.authorized_task_ids: list[str | None] = []
        self.created_runs: list[QualityDispatchRecord] = []
        self.active_run_id: str | None = None

    async def require_check(self, check_id: str, user_id: str):
        del check_id, user_id
        return self.record

    async def update_public_status(
        self, check_id: str, user_id: str, status: str, reset_result: bool
    ):
        del check_id, user_id, reset_result
        self.updated = True
        self.record.status = status
        return self.record

    async def get_check(self, check_id: str, user_id: str) -> QualityCheckDto:
        del check_id, user_id
        now = datetime(2026, 7, 11, tzinfo=UTC)
        return QualityCheckDto(
            id=self.record.id,
            chapterId=self.record.chapter_id,
            type=self.record.type,
            status=self.record.status,
            title="一致性终检",
            summary=None,
            result=None,
            scoreHook=None,
            scoreTension=None,
            scorePayoff=None,
            scorePacing=None,
            scoreEndingHook=None,
            scoreReaderPromise=None,
            scoreOverall=None,
            qualityGate=None,
            rewriteBrief=None,
            createdAt=now,
            updatedAt=now,
        )

    async def authorize_run(
        self, check_id: str, user_id: str, task_id: str | None
    ) -> QualityRecord:
        del check_id, user_id
        self.authorized_task_ids.append(task_id)
        if task_id == "mismatch":
            raise ApiError(
                status_code=403,
                code="QUALITY_TASK_MISMATCH",
                message="任务与检查项不匹配",
            )
        return self.record

    async def create_run(
        self,
        check_id: str,
        user_id: str,
        task_id: str | None,
        message: str | None,
    ) -> QualityDispatchRecord:
        await self.authorize_run(check_id, user_id, task_id)
        if self.active_run_id is not None:
            raise ApiError(
                status_code=409,
                code="QUALITY_RUN_ACTIVE",
                message="质量检查已有运行中的任务",
            )
        import json

        run = QualityDispatchRecord(
            run_id=f"quality-run-{len(self.created_runs) + 1}",
            check_id=check_id,
            user_id=user_id,
            novel_id=self.record.novel_id,
            chapter_id=self.record.chapter_id,
            source_task_id=task_id,
            message=message,
        )
        self.created_runs.append(run)
        self.active_run_id = run.run_id
        self.last_input_json = json.dumps(
            {
                "checkId": check_id,
                "sourceTaskId": task_id,
                "message": message,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return run

    async def get_run_context(self, check_id, user_id, task_id, message):
        self.authorized_task_ids.append(task_id)
        return {
            "checkId": check_id,
            "novelId": self.record.novel_id,
            "chapterId": self.record.chapter_id,
            "chapterContent": "完整章节",
            "message": message,
        }

    async def complete_run(self, check_id, user_id, result):
        self.completed = (check_id, user_id, result)

    async def fail_run(self, check_id, user_id):
        self.failed = (check_id, user_id)


def test_public_quality_status_only_accepts_pending_or_skipped() -> None:
    for status in ("running", "completed", "failed"):
        with pytest.raises(ValidationError):
            UpdateQualityCheckRequest.model_validate({"status": status})


@pytest.mark.asyncio
async def test_run_without_submitter_returns_503_without_changing_status() -> None:
    repository = RecordingQualityRepository()
    service = QualityService(repository, submitter=None)  # type: ignore[arg-type]

    with pytest.raises(ApiError, match="暂时不可用") as caught:
        await service.run("user-1", "check-1", RunQualityCheckRequest(message="完整检查"))

    assert caught.value.status_code == 503
    assert repository.updated is False
    assert repository.record.status == "pending"


@pytest.mark.asyncio
async def test_run_rejects_non_consistency_check() -> None:
    repository = RecordingQualityRepository()
    repository.record.type = "editorial"
    service = QualityService(repository, submitter=None)  # type: ignore[arg-type]

    with pytest.raises(ApiError, match="只支持一致性终检") as caught:
        await service.run("user-1", "check-1", RunQualityCheckRequest())

    assert caught.value.status_code == 400


@pytest.mark.parametrize("status", ["pending", "skipped"])
def test_public_quality_status_accepts_only_public_values(status: str) -> None:
    value = UpdateQualityCheckRequest.model_validate({"status": status})
    assert value.status == status


def test_quality_requests_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        RunQualityCheckRequest.model_validate({"userId": "越权"})
    with pytest.raises(ValidationError, match="extra_forbidden"):
        UpdateQualityCheckRequest.model_validate({"status": "pending", "scoreOverall": 10})


def test_quality_success_request_reuses_shared_report_contract() -> None:
    assert issubclass(QualityRunSuccessRequest, ConsistencyQualityReport)
    with pytest.raises(ValidationError):
        QualityRunSuccessRequest.model_validate(
            {
                "userId": "user-1",
                "novelId": "novel-1",
                "taskId": "task-1",
                "runId": "run-1",
                **valid_quality_report(report="   "),
            }
        )


@pytest.mark.parametrize(
    ("request_type", "body"),
    [
        (UpdateQualityCheckRequest, {"status": "pending", "resetResult": "true"}),
        (RunQualityCheckRequest, {"taskId": 123}),
    ],
)
def test_quality_requests_reject_coerced_values(request_type, body) -> None:
    with pytest.raises(ValidationError):
        request_type.model_validate(body)


@pytest.mark.asyncio
async def test_public_status_update_forwards_reset_and_returns_fresh_check() -> None:
    repository = RecordingQualityRepository()
    service = QualityService(repository, submitter=None)  # type: ignore[arg-type]
    response = await service.update_status(
        "user-1",
        "check-1",
        UpdateQualityCheckRequest(status="skipped", resetResult=True),
    )
    assert repository.updated is True
    assert response.status == "skipped"


class RecordingDispatcher:
    def __init__(self) -> None:
        self.records: list[QualityDispatchRecord] = []

    async def dispatch(self, record: QualityDispatchRecord) -> bool:
        self.records.append(record)
        return True


@pytest.mark.asyncio
async def test_run_submitter_receives_only_authorized_context() -> None:
    repository = RecordingQualityRepository()
    dispatcher = RecordingDispatcher()
    service = QualityService(repository, dispatcher=dispatcher)  # type: ignore[arg-type]
    response = await service.run(
        "cookie-user",
        "check-1",
        RunQualityCheckRequest(taskId="task-existing", message="完整检查"),
    )
    assert response.model_dump() == {
        "accepted": True,
        "checkId": "check-1",
        "taskId": "quality-run-1",
    }
    assert dispatcher.records == [repository.created_runs[0]]
    assert dispatcher.records[0].source_task_id == "task-existing"
    assert dispatcher.records[0].message == "完整检查"
    assert repository.last_input_json == (
        '{"checkId":"check-1","sourceTaskId":"task-existing","message":"完整检查"}'
    )
    assert repository.authorized_task_ids == ["task-existing", "task-existing"]


@pytest.mark.asyncio
async def test_repeated_quality_runs_create_distinct_persisted_run_ids() -> None:
    repository = RecordingQualityRepository()
    dispatcher = RecordingDispatcher()
    service = QualityService(repository, dispatcher=dispatcher)  # type: ignore[arg-type]

    first = await service.run("user-1", "check-1", RunQualityCheckRequest())
    with pytest.raises(ApiError) as caught:
        await service.run("user-1", "check-1", RunQualityCheckRequest())
    assert caught.value.status_code == 409
    assert caught.value.code == "QUALITY_RUN_ACTIVE"

    repository.active_run_id = None
    second = await service.run("user-1", "check-1", RunQualityCheckRequest())

    assert first.taskId == "quality-run-1"
    assert second.taskId == "quality-run-2"
    assert [record.run_id for record in dispatcher.records] == [
        "quality-run-1",
        "quality-run-2",
    ]


@pytest.mark.asyncio
async def test_run_rejects_task_that_does_not_match_check() -> None:
    repository = RecordingQualityRepository()
    service = QualityService(repository, dispatcher=RecordingDispatcher())  # type: ignore[arg-type]
    with pytest.raises(ApiError) as caught:
        await service.run(
            "cookie-user",
            "check-1",
            RunQualityCheckRequest(taskId="mismatch"),
        )
    assert caught.value.status_code == 403
    assert caught.value.code == "QUALITY_TASK_MISMATCH"


@pytest.mark.asyncio
async def test_internal_quality_context_and_result_stay_in_core() -> None:
    repository = RecordingQualityRepository()
    service = QualityService(repository, submitter=None)  # type: ignore[arg-type]

    context = await service.get_run_context(
        "user-1", "check-1", None, "检查一致性"
    )
    result = valid_quality_report()
    await service.complete_run("user-1", "check-1", result)

    assert context["chapterContent"] == "完整章节"
    assert repository.completed == ("check-1", "user-1", result)


@asynccontextmanager
async def quality_api_client(service: QualityService) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(testing=True)
    app.state.quality_service = service
    app.dependency_overrides[get_current_user] = lambda: AuthUser(
        id="cookie-user",
        username="alice",
        password_hash="",  # noqa: S106
        credit_balance_micros=0,
    )
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.mark.asyncio
async def test_run_api_returns_503_and_keeps_pending_when_submitter_missing() -> None:
    repository = RecordingQualityRepository()
    service = QualityService(repository, submitter=None)  # type: ignore[arg-type]
    async with quality_api_client(service) as client:
        response = await client.post("/api/v1/quality-checks/check-1/run", json={})
    assert response.status_code == 503
    assert response.json()["code"] == "QUALITY_RUN_UNAVAILABLE"
    assert repository.record.status == "pending"
    assert repository.updated is False


@pytest.mark.asyncio
async def test_run_api_returns_202_after_submitter_is_connected() -> None:
    repository = RecordingQualityRepository()
    service = QualityService(repository, dispatcher=RecordingDispatcher())  # type: ignore[arg-type]
    async with quality_api_client(service) as client:
        response = await client.post("/api/v1/quality-checks/check-1/run", json={})
    assert response.status_code == 202
    assert response.json()["accepted"] is True


@pytest.mark.asyncio
async def test_quality_http_rejects_string_encoded_boolean() -> None:
    repository = RecordingQualityRepository()
    service = QualityService(repository, submitter=None)  # type: ignore[arg-type]
    async with quality_api_client(service) as client:
        response = await client.patch(
            "/api/v1/quality-checks/check-1",
            json={"status": "pending", "resetResult": "true"},
        )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


class OneRowResult:
    def __init__(self, row: tuple[object, ...] | None) -> None:
        self.row = row

    def one_or_none(self) -> tuple[object, ...] | None:
        return self.row


class TaskAuthSession:
    def __init__(self, row: tuple[object, ...] | None) -> None:
        self.row = row

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback

    async def execute(self, statement):
        del statement
        return OneRowResult(self.row)


def writing_task(*, novel_id: str = "novel-1", chapter_id: str = "chapter-1"):
    from inkforge_core.db.models import WritingTask

    now = datetime(2026, 7, 11, tzinfo=UTC)
    return WritingTask(
        id="task-1",
        novelId=novel_id,
        chapterId=chapter_id,
        selectedAgents="[]",
        targetWordCount=0,
        phase="active",
        createdAt=now,
        updatedAt=now,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "row",
    [
        None,
        pytest.param((writing_task(), "other-user"), id="其他用户"),
        pytest.param((writing_task(novel_id="other-novel"), "user-1"), id="其他小说"),
        pytest.param((writing_task(chapter_id="other-chapter"), "user-1"), id="其他章节"),
    ],
)
async def test_repository_rejects_unmatched_quality_task(row) -> None:
    from inkforge_core.quality.repository import QualityRepository

    repository = QualityRepository(lambda: TaskAuthSession(row))  # type: ignore[arg-type]

    async def require_check(session, check_id: str, user_id: str):
        del session, check_id, user_id
        return quality_check_model(), "novel-1"

    repository._require_check = require_check  # type: ignore[method-assign]
    with pytest.raises(ApiError) as caught:
        await repository.authorize_run("check-1", "user-1", "task-1")
    assert caught.value.status_code == 403
    assert caught.value.code == "QUALITY_TASK_MISMATCH"


@pytest.mark.asyncio
async def test_repository_accepts_task_with_same_owner_novel_and_chapter() -> None:
    from inkforge_core.quality.repository import QualityRepository

    repository = QualityRepository(  # type: ignore[arg-type]
        lambda: TaskAuthSession((writing_task(), "user-1"))
    )

    async def require_check(session, check_id: str, user_id: str):
        del session, check_id, user_id
        return quality_check_model(), "novel-1"

    repository._require_check = require_check  # type: ignore[method-assign]
    result = await repository.authorize_run("check-1", "user-1", "task-1")
    assert result.id == "check-1"


def quality_check_model():
    from inkforge_core.db.models import ChapterQualityCheck

    now = datetime(2026, 7, 11, tzinfo=UTC)
    return ChapterQualityCheck(
        id="check-1",
        chapterId="chapter-1",
        type="consistency",
        status="pending",
        title="一致性终检",
        createdAt=now,
        updatedAt=now,
    )


class QualityRunSession:
    def __init__(self, scalar_result: object | None) -> None:
        self.scalar_result = scalar_result
        self.added: list[object] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback

    def begin(self):
        return self

    async def scalar(self, statement):
        del statement
        return self.scalar_result

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = "quality-run-new"


def chapter_model():
    from inkforge_core.db.models import Chapter

    now = datetime(2026, 7, 11, tzinfo=UTC)
    return Chapter(
        id="chapter-1",
        novelId="novel-1",
        order=1,
        status="review",
        title="第一章",
        content="完整章节",
        createdAt=now,
        updatedAt=now,
    )


def quality_run_model(*, run_id: str, status: str):
    from inkforge_core.db.models import WorkflowRun

    now = datetime(2026, 7, 11, tzinfo=UTC)
    return WorkflowRun(
        id=run_id,
        chapterId="chapter-1",
        novelId="novel-1",
        userId="user-1",
        kind="quality_check",
        status=status,
        sourceType="quality_check",
        sourceId="check-1",
        input=json.dumps(
            {
                "checkId": "check-1",
                "sourceTaskId": None,
                "message": None,
                "chapterContent": "完整章节",
                "chapterContentSha256": hashlib.sha256(
                    "完整章节".encode()
                ).hexdigest(),
                "sourceUpdatedAt": "2026-07-11T00:00:00+00:00",
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        createdAt=now,
        updatedAt=now,
    )


def quality_repository_with_locked_records(session: QualityRunSession):
    from inkforge_core.quality.repository import QualityRepository

    repository = QualityRepository(lambda: session)  # type: ignore[arg-type]
    chapter = chapter_model()
    check = quality_check_model()

    async def require_check(current_session, check_id: str, user_id: str):
        del current_session, check_id, user_id
        return check, chapter.novelId

    async def lock_chapter(current_session, check_id: str, user_id: str):
        del current_session, check_id, user_id
        return chapter

    async def lock_check(current_session, check_id: str):
        del current_session, check_id
        return check

    async def validate_task(current_session, record, user_id: str, task_id: str | None):
        del current_session, record, user_id, task_id

    repository._require_check = require_check  # type: ignore[method-assign]
    repository._lock_chapter_owner_for_check = lock_chapter  # type: ignore[method-assign]
    repository._lock_check = lock_check  # type: ignore[method-assign]
    repository._validate_task_binding = validate_task  # type: ignore[method-assign]
    return repository, chapter, check


@pytest.mark.asyncio
async def test_quality_success_persists_full_report_and_only_average() -> None:
    session = QualityRunSession("quality-run-current")
    repository, _, check = quality_repository_with_locked_records(session)
    run = quality_run_model(run_id="quality-run-current", status="running")
    report = valid_quality_report()

    async def require_bound(*args, **kwargs):
        del args, kwargs
        return run

    repository._require_bound_quality_run = require_bound  # type: ignore[method-assign]

    await repository.complete_run(
        "check-1",
        "user-1",
        report,
        run_id=run.id,
        novel_id="novel-1",
    )

    assert json.loads(run.output) == report
    assert check.scoreOverall == 84
    assert check.result == "完整一致性报告"
    assert check.qualityGate == "revise"
    assert check.rewriteBrief == "修正时间线"
    assert all(
        value is None
        for value in (
            check.scoreHook,
            check.scoreTension,
            check.scorePayoff,
            check.scorePacing,
            check.scoreEndingHook,
            check.scoreReaderPromise,
        )
    )


@pytest.mark.asyncio
async def test_repository_rejects_second_active_quality_run_atomically() -> None:
    active = quality_run_model(run_id="quality-run-active", status="running")
    session = QualityRunSession(active)
    repository, _, _ = quality_repository_with_locked_records(session)

    with pytest.raises(ApiError) as caught:
        await repository.create_run("check-1", "user-1", None, None)

    assert caught.value.status_code == 409
    assert caught.value.code == "QUALITY_RUN_ACTIVE"
    assert session.added == []


@pytest.mark.asyncio
async def test_repository_allows_new_quality_run_after_terminal_state() -> None:
    session = QualityRunSession(None)
    repository, _, _ = quality_repository_with_locked_records(session)

    created = await repository.create_run("check-1", "user-1", None, None)

    assert created.run_id
    assert len(session.added) == 1


@pytest.mark.asyncio
async def test_repository_marks_public_check_running_when_run_is_accepted() -> None:
    session = QualityRunSession(None)
    repository, _, check = quality_repository_with_locked_records(session)

    await repository.create_run("check-1", "user-1", None, None)

    assert check.status == "running"


@pytest.mark.asyncio
@pytest.mark.parametrize("chapter_status", ["drafting", "completed"])
async def test_repository_only_allows_quality_run_for_review_chapter(
    chapter_status: str,
) -> None:
    session = QualityRunSession(None)
    repository, chapter, check = quality_repository_with_locked_records(session)
    chapter.status = chapter_status

    with pytest.raises(ApiError) as caught:
        await repository.create_run("check-1", "user-1", None, None)

    assert caught.value.status_code == 409
    assert caught.value.code == "QUALITY_CHECK_CHAPTER_NOT_IN_REVIEW"
    assert check.status == "pending"
    assert session.added == []


@pytest.mark.asyncio
async def test_public_status_update_rejects_active_quality_run() -> None:
    active = quality_run_model(run_id="quality-run-active", status="running")
    session = QualityRunSession(active)
    repository, _, check = quality_repository_with_locked_records(session)

    with pytest.raises(ApiError) as caught:
        await repository.update_public_status(
            "check-1",
            "user-1",
            "skipped",
            False,
        )

    assert caught.value.status_code == 409
    assert caught.value.code == "QUALITY_RUN_ACTIVE"
    assert check.status == "pending"


@pytest.mark.asyncio
async def test_completed_chapter_rejects_quality_check_reset() -> None:
    session = QualityRunSession(None)
    repository, chapter, check = quality_repository_with_locked_records(session)
    chapter.status = "completed"
    check.status = "skipped"

    with pytest.raises(ApiError) as caught:
        await repository.update_public_status(
            "check-1",
            "user-1",
            "pending",
            True,
        )

    assert caught.value.status_code == 409
    assert caught.value.code == "QUALITY_CHECK_CHAPTER_COMPLETED"
    assert check.status == "skipped"


@pytest.mark.asyncio
async def test_quality_run_persists_complete_chapter_snapshot_and_hash() -> None:
    session = QualityRunSession(None)
    repository, chapter, _ = quality_repository_with_locked_records(session)

    await repository.create_run("check-1", "user-1", None, "检查当前正文")

    run = session.added[0]
    payload = json.loads(run.input)
    assert payload["chapterContent"] == chapter.content
    assert payload["chapterContentSha256"] == hashlib.sha256(
        chapter.content.encode("utf-8")
    ).hexdigest()
    assert payload["sourceUpdatedAt"] == "2026-07-11T00:00:00+00:00"


@pytest.mark.asyncio
async def test_quality_context_uses_persisted_snapshot_instead_of_live_content() -> None:
    session = QualityRunSession("quality-run-1")
    repository, chapter, _ = quality_repository_with_locked_records(session)
    run = quality_run_model(run_id="quality-run-1", status="running")
    original = "发起检查时的正文"
    run.input = json.dumps(
        {
            "checkId": "check-1",
            "sourceTaskId": None,
            "message": None,
            "chapterContent": original,
            "chapterContentSha256": hashlib.sha256(original.encode("utf-8")).hexdigest(),
            "sourceUpdatedAt": "2026-07-11T00:00:00+00:00",
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    chapter.content = "上下文读取前已变化的正文"

    async def require_bound(*args, **kwargs):
        del args, kwargs
        return run

    async def is_latest(*args, **kwargs):
        del args, kwargs
        return True

    repository._require_bound_quality_run = require_bound  # type: ignore[method-assign]
    repository._is_latest_quality_run = is_latest  # type: ignore[method-assign]

    context = await repository.get_run_context(
        "check-1",
        "user-1",
        None,
        None,
        run.id,
    )

    assert context["chapterContent"] == original


@pytest.mark.asyncio
async def test_stale_quality_success_only_settles_its_own_workflow_run() -> None:
    session = QualityRunSession("quality-run-new")
    repository, _, check = quality_repository_with_locked_records(session)
    stale = quality_run_model(run_id="quality-run-old", status="running")
    check.status = "completed"
    check.result = "新运行结果"

    async def require_bound(*args, **kwargs):
        del args, kwargs
        return stale

    repository._require_bound_quality_run = require_bound  # type: ignore[method-assign]
    report = valid_quality_report(report="旧运行结果")
    await repository.complete_run(
        "check-1",
        "user-1",
        report,
        run_id=stale.id,
        novel_id="novel-1",
    )

    assert stale.status == "completed"
    assert json.loads(stale.output) == report
    assert check.status == "completed"
    assert check.result == "新运行结果"


@pytest.mark.asyncio
async def test_stale_quality_failure_does_not_fail_latest_check() -> None:
    session = QualityRunSession("quality-run-new")
    repository, _, check = quality_repository_with_locked_records(session)
    stale = quality_run_model(run_id="quality-run-old", status="running")
    check.status = "completed"
    check.result = "新运行结果"

    async def require_bound(*args, **kwargs):
        del args, kwargs
        return stale

    repository._require_bound_quality_run = require_bound  # type: ignore[method-assign]
    await repository.fail_run(
        "check-1",
        "user-1",
        run_id=stale.id,
        novel_id="novel-1",
    )

    assert stale.status == "failed"
    assert check.status == "completed"
    assert check.result == "新运行结果"


@pytest.mark.asyncio
async def test_changed_content_cancels_quality_success_without_completing_check() -> None:
    session = QualityRunSession("quality-run-current")
    repository, chapter, check = quality_repository_with_locked_records(session)
    run = quality_run_model(run_id="quality-run-current", status="running")
    source = chapter.content
    run.input = json.dumps(
        {
            "checkId": "check-1",
            "sourceTaskId": None,
            "message": None,
            "chapterContent": source,
            "chapterContentSha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "sourceUpdatedAt": "2026-07-11T00:00:00+00:00",
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    chapter.content = "运行期间修改后的正文"
    check.status = "pending"
    check.result = None

    async def require_bound(*args, **kwargs):
        del args, kwargs
        return run

    async def is_latest(*args, **kwargs):
        del args, kwargs
        return True

    repository._require_bound_quality_run = require_bound  # type: ignore[method-assign]
    repository._is_latest_quality_run = is_latest  # type: ignore[method-assign]

    report = valid_quality_report(report="旧正文报告")
    await repository.complete_run(
        "check-1",
        "user-1",
        report,
        run_id=run.id,
        novel_id="novel-1",
    )

    assert run.status == "cancelled"
    assert json.loads(run.output) == report
    assert run.errorMessage == "QUALITY_SOURCE_CHANGED"
    assert check.status == "pending"
    assert check.result is None


@pytest.mark.asyncio
async def test_changed_content_cancels_quality_failure_without_failing_check() -> None:
    session = QualityRunSession("quality-run-current")
    repository, chapter, check = quality_repository_with_locked_records(session)
    run = quality_run_model(run_id="quality-run-current", status="running")
    source = chapter.content
    run.input = json.dumps(
        {
            "checkId": "check-1",
            "sourceTaskId": None,
            "message": None,
            "chapterContent": source,
            "chapterContentSha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "sourceUpdatedAt": "2026-07-11T00:00:00+00:00",
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    chapter.content = "运行期间修改后的正文"
    check.status = "pending"

    async def require_bound(*args, **kwargs):
        del args, kwargs
        return run

    async def is_latest(*args, **kwargs):
        del args, kwargs
        return True

    repository._require_bound_quality_run = require_bound  # type: ignore[method-assign]
    repository._is_latest_quality_run = is_latest  # type: ignore[method-assign]

    await repository.fail_run(
        "check-1",
        "user-1",
        run_id=run.id,
        novel_id="novel-1",
    )

    assert run.status == "cancelled"
    assert run.errorMessage == "QUALITY_SOURCE_CHANGED"
    assert check.status == "pending"


@pytest.mark.asyncio
async def test_stale_quality_run_cannot_reopen_context() -> None:
    session = QualityRunSession("quality-run-new")
    repository, _, check = quality_repository_with_locked_records(session)
    stale = quality_run_model(run_id="quality-run-old", status="failed")
    check.status = "completed"

    async def require_bound(*args, **kwargs):
        del args, kwargs
        return stale

    async def authorize(*args, **kwargs):
        del args, kwargs
        return QualityRecord(status=check.status)

    repository._require_bound_quality_run = require_bound  # type: ignore[method-assign]
    repository.authorize_run = authorize  # type: ignore[method-assign]

    with pytest.raises(ApiError) as caught:
        await repository.get_run_context(
            "check-1",
            "user-1",
            None,
            None,
            stale.id,
        )

    assert caught.value.status_code == 409
    assert caught.value.code == "QUALITY_RUN_NOT_ACTIVE"
    assert check.status == "completed"
