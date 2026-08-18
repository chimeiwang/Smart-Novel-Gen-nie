from __future__ import annotations

import pytest
from inkforge_core.billing.repository import BillingRepository


class Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class Session:
    def __init__(self) -> None:
        self.values = [None, 5000]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def execute(self, statement):
        del statement
        return Result(self.values.pop(0))


class Factory:
    def __init__(self) -> None:
        self.session = Session()

    def __call__(self):
        return self.session


class VideoSession(Session):
    """依次模拟写作、质量未命中，最后命中活动视频任务。"""

    def __init__(self) -> None:
        self.values = [None, None, 5000]
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return await super().execute(statement)


class VideoFactory(Factory):
    def __init__(self) -> None:
        self.session = VideoSession()


@pytest.mark.asyncio
async def test_portrait_task_can_authorize_authenticated_user_balance() -> None:
    repository = BillingRepository(Factory())  # type: ignore[arg-type]

    context = await repository.get_authorization_context(
        "user-1", "task-1", "style:style-1"
    )

    assert context is not None
    assert context.balance_micros == 5000


@pytest.mark.asyncio
async def test_quality_check_can_authorize_owning_user_balance() -> None:
    repository = BillingRepository(Factory())  # type: ignore[arg-type]

    context = await repository.get_authorization_context(
        "user-1", "check-1", "novel-1"
    )

    assert context is not None
    assert context.balance_micros == 5000


@pytest.mark.asyncio
async def test_video_authorization_requires_active_task_status() -> None:
    """终态旧任务不能借队列重放再次取得真实模型授权。"""

    factory = VideoFactory()
    repository = BillingRepository(factory)  # type: ignore[arg-type]

    context = await repository.get_authorization_context(
        "user-1", "video-task-1", "novel-1"
    )

    assert context is not None
    video_query = factory.session.statements[-1]
    where_text = str(video_query.whereclause)
    assert '"VideoGenerationTask".status IN' in where_text
    assert video_query.compile().params["status_1"] == [
        "pending",
        "submitted",
        "processing",
    ]
