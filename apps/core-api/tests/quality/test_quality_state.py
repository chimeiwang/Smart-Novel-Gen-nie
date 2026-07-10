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
from inkforge_core.quality.schemas import RunQualityCheckRequest, UpdateQualityCheckRequest
from inkforge_core.quality.service import QualityService
from pydantic import ValidationError


@dataclass
class QualityRecord:
    id: str = "check-1"
    chapter_id: str = "chapter-1"
    type: str = "consistency"
    status: str = "pending"


class RecordingQualityRepository:
    def __init__(self) -> None:
        self.record = QualityRecord()
        self.updated = False

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


class RecordingSubmitter:
    def __init__(self) -> None:
        self.input: dict[str, str | None] | None = None

    async def submit(self, **kwargs: str | None) -> str:
        self.input = kwargs
        return "task-created"


@pytest.mark.asyncio
async def test_run_submitter_receives_only_authorized_context() -> None:
    repository = RecordingQualityRepository()
    submitter = RecordingSubmitter()
    service = QualityService(repository, submitter=submitter)  # type: ignore[arg-type]
    response = await service.run(
        "cookie-user",
        "check-1",
        RunQualityCheckRequest(taskId="task-existing", message="完整检查"),
    )
    assert response.model_dump() == {
        "accepted": True,
        "checkId": "check-1",
        "taskId": "task-created",
    }
    assert submitter.input == {
        "user_id": "cookie-user",
        "check_id": "check-1",
        "task_id": "task-existing",
        "message": "完整检查",
    }


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
    service = QualityService(repository, submitter=RecordingSubmitter())  # type: ignore[arg-type]
    async with quality_api_client(service) as client:
        response = await client.post("/api/v1/quality-checks/check-1/run", json={})
    assert response.status_code == 202
    assert response.json()["accepted"] is True
