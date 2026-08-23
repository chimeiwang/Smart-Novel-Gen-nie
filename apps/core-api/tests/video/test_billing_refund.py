"""视频规划结构失败的积分补偿测试。"""

from __future__ import annotations

import pytest
from inkforge_contracts.video import VideoPlanFailureCallback
from inkforge_core.billing.request_ids import video_task_billing_request_prefix
from inkforge_core.db.models import CreditLedger, VideoGenerationTask
from inkforge_core.video.repository import (
    _is_refundable_video_plan_failure,
    _refund_failed_video_plan,
)


class _Rows:
    def __init__(self, values: list[CreditLedger]) -> None:
        self._values = values

    def all(self) -> list[CreditLedger]:
        return self._values


class _RefundSession:
    def __init__(
        self,
        *,
        scalar_values: list[object],
        charges: list[CreditLedger] | None = None,
    ) -> None:
        self._scalar_values = iter(scalar_values)
        self._charges = charges or []
        self.added: list[object] = []

    async def scalar(self, statement: object) -> object:
        del statement
        return next(self._scalar_values)

    async def scalars(self, statement: object) -> _Rows:
        del statement
        return _Rows(self._charges)

    def add(self, value: object) -> None:
        self.added.append(value)


def _failure(message: str) -> VideoPlanFailureCallback:
    return VideoPlanFailureCallback(
        protocolVersion="1.0",
        eventId="event-1",
        jobId="job-1",
        runId="run-1",
        taskId="task-1",
        novelId="novel-1",
        projectId="project-1",
        sceneId="scene-1",
        code="VIDEO_PLAN_FAILED",
        message=message,
        recoverable=True,
    )


def test_only_exhausted_structured_business_failure_is_refundable() -> None:
    assert _is_refundable_video_plan_failure(
        _failure("VIDEO_SCENE_PLAN_INVALID：摄影灯光阶段：schema_violation")
    )
    assert not _is_refundable_video_plan_failure(_failure("供应商暂时不可用"))
    assert not _is_refundable_video_plan_failure(
        _failure("VIDEO_SCENE_PLAN_INVALID：失败").model_copy(update={"recoverable": False})
    )


@pytest.mark.asyncio
async def test_refund_aggregates_only_task_scoped_charges_and_writes_one_ledger() -> None:
    task = VideoGenerationTask(id="task-1")
    prefix = video_task_billing_request_prefix(task.id)
    charges = [
        CreditLedger(
            userId="user-1",
            type="ai_charge",
            amountMicros=-120,
            balanceAfterMicros=880,
            requestId=f"{prefix}grant-1",
        ),
        CreditLedger(
            userId="user-1",
            type="ai_charge",
            amountMicros=-80,
            balanceAfterMicros=800,
            requestId=f"{prefix}grant-2",
        ),
    ]
    session = _RefundSession(
        scalar_values=["user-1", None, 1_000],
        charges=charges,
    )

    await _refund_failed_video_plan(  # type: ignore[arg-type]
        session,
        task=task,
        novel_id="novel-1",
    )

    assert len(session.added) == 1
    refund = session.added[0]
    assert isinstance(refund, CreditLedger)
    assert refund.type == "video_plan_refund"
    assert refund.amountMicros == 200
    assert refund.balanceAfterMicros == 1_000
    assert refund.requestId == f"{prefix}refund"


@pytest.mark.asyncio
async def test_existing_refund_makes_compensation_idempotent() -> None:
    task = VideoGenerationTask(id="task-1")
    existing = CreditLedger(
        userId="user-1",
        type="video_plan_refund",
        amountMicros=200,
        balanceAfterMicros=1_000,
        requestId=f"{video_task_billing_request_prefix(task.id)}refund",
    )
    session = _RefundSession(scalar_values=["user-1", existing])

    await _refund_failed_video_plan(  # type: ignore[arg-type]
        session,
        task=task,
        novel_id="novel-1",
    )

    assert session.added == []
