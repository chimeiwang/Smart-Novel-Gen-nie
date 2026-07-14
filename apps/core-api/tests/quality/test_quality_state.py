from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
import pytest
from inkforge_core.app import create_app
from inkforge_core.auth.dependencies import get_current_user
from inkforge_core.auth.repository import AuthUser
from inkforge_core.errors import ApiError
from inkforge_core.novels.schemas import QualityCheckDto
from inkforge_core.quality.dispatcher import QualityDispatchRecord
from inkforge_core.quality.schemas import RunQualityCheckRequest, UpdateQualityCheckRequest
from inkforge_core.quality.service import QualityService
from pydantic import ValidationError


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
    result = {
        "result": "检查报告",
        "scores": {"overall": 9},
        "qualityGate": "pass",
        "rewriteBrief": None,
    }
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
