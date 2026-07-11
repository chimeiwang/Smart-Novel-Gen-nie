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


@pytest.mark.asyncio
async def test_portrait_task_can_authorize_authenticated_user_balance() -> None:
    repository = BillingRepository(Factory())  # type: ignore[arg-type]

    context = await repository.get_authorization_context(
        "user-1", "task-1", "style:style-1"
    )

    assert context is not None
    assert context.balance_micros == 5000
