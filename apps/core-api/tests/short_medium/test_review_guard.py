from __future__ import annotations

import pytest
from inkforge_core.errors import ApiError
from inkforge_core.reviews.repository import ReviewRepository
from inkforge_core.reviews.schemas import CreateArtifactRequest


class FailingSessionFactory:
    def __call__(self) -> object:
        raise AssertionError("守卫必须在打开数据库事务前拒绝")


@pytest.mark.asyncio
async def test_generic_create_rejects_short_medium_version_key() -> None:
    repository = ReviewRepository(FailingSessionFactory())  # type: ignore[arg-type]
    request = CreateArtifactRequest(
        runId="run-1",
        taskId="task-1",
        novelId="novel-1",
        artifactKey="short-medium:outline:novel-1",
        kind="outline_draft",
        status="awaiting_user",
        payload={"kind": "outline_draft", "content": "候选"},
        createdByAgent="剧情",
    )

    with pytest.raises(ApiError) as error:
        await repository.create_or_revise("user-1", request)

    assert error.value.code == "SHORT_MEDIUM_VERSION_ROUTE_REQUIRED"
