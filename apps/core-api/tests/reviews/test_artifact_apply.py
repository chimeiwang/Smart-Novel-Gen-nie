from __future__ import annotations

from dataclasses import dataclass

import pytest
from inkforge_core.errors import ApiError
from inkforge_core.reviews.apply import FormalArtifactApplier
from inkforge_core.reviews.service import ReviewService


@dataclass
class Artifact:
    id: str = "artifact-1"
    status: str = "awaiting_user"
    kind: str = "chapter_draft"
    payload: dict[str, object] | None = None

    def __post_init__(self) -> None:
        if self.payload is None:
            self.payload = {"kind": self.kind, "content": "完整正文"}


class FakeReviewRepository:
    def __init__(self, artifact: Artifact | None = None) -> None:
        self.artifact = artifact or Artifact()
        self.transitions: list[tuple[str, str]] = []
        self.deleted = False

    async def require_artifact(self, user_id: str, artifact_id: str) -> Artifact:
        assert user_id == "user-1"
        assert artifact_id == "artifact-1"
        return self.artifact

    async def transition(self, artifact_id: str, current: str, target: str) -> None:
        assert self.artifact.status == current
        self.transitions.append((current, target))
        self.artifact.status = target

    async def discard(self, user_id: str, artifact_id: str) -> None:
        await self.require_artifact(user_id, artifact_id)
        self.deleted = True


class FakeApplier:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.payload: dict[str, object] | None = None

    async def apply(
        self,
        artifact: Artifact,
        *,
        user_id: str,
        edited_content: str | None,
        selected_update_refs: list[dict[str, object]] | None,
    ) -> int:
        del user_id, edited_content, selected_update_refs
        self.payload = artifact.payload
        if self.fail:
            raise ValueError("正式写入失败")
        return 1


@pytest.mark.asyncio
async def test_approve_transitions_through_applying_to_applied() -> None:
    repository = FakeReviewRepository()
    applier = FakeApplier()
    service = ReviewService(repository, applier)

    result = await service.decide("user-1", "artifact-1", "approve")

    assert repository.transitions == [
        ("awaiting_user", "applying"),
        ("applying", "applied"),
    ]
    assert result.savedCount == 1


@pytest.mark.asyncio
async def test_apply_failure_returns_artifact_to_awaiting_user() -> None:
    repository = FakeReviewRepository()
    service = ReviewService(repository, FakeApplier(fail=True))

    with pytest.raises(ApiError) as error:
        await service.decide("user-1", "artifact-1", "approve")

    assert error.value.status_code == 409
    assert repository.transitions[-1] == ("applying", "awaiting_user")


@pytest.mark.asyncio
async def test_discard_hard_deletes_artifact() -> None:
    repository = FakeReviewRepository()
    result = await ReviewService(repository, FakeApplier()).decide(
        "user-1", "artifact-1", "discard"
    )

    assert repository.deleted is True
    assert result.deleted is True


@pytest.mark.asyncio
async def test_revision_brief_cannot_be_approved() -> None:
    repository = FakeReviewRepository(Artifact(kind="revision_brief"))

    with pytest.raises(ApiError) as error:
        await ReviewService(repository, FakeApplier()).decide("user-1", "artifact-1", "approve")

    assert error.value.status_code == 400
    assert repository.transitions == []


class FakeFormalWrites:
    def __init__(self) -> None:
        self.content: str | None = None

    async def apply_outline(self, artifact: object, user_id: str, content: str) -> int:
        del artifact, user_id
        self.content = content
        return 1

    async def apply_chapter(self, artifact: object, user_id: str, content: str) -> int:
        del artifact, user_id
        self.content = content
        return 1

    async def apply_beat_plan(
        self, artifact: object, user_id: str, beat_plan: dict[str, object]
    ) -> int:
        del artifact, user_id
        self.content = str(beat_plan["chapterGoal"])
        return 1


class FakeUpdatesExecutor:
    def __init__(self) -> None:
        self.updates: dict[str, object] | None = None

    async def apply(self, novel_id: str, user_id: str, updates: dict[str, object]) -> int:
        del novel_id, user_id
        self.updates = updates
        return 1


@pytest.mark.asyncio
async def test_formal_applier_preserves_complete_edited_chapter_content() -> None:
    writes = FakeFormalWrites()
    applier = FormalArtifactApplier(writes, FakeUpdatesExecutor())
    artifact = Artifact()
    artifact.novel_id = "novel-1"
    artifact.chapter_id = "chapter-1"
    complete_content = "正文" * 20_000

    await applier.apply(
        artifact,
        user_id="user-1",
        edited_content=complete_content,
        selected_update_refs=None,
    )

    assert writes.content == complete_content


@pytest.mark.asyncio
async def test_formal_applier_filters_selected_agent_updates() -> None:
    executor = FakeUpdatesExecutor()
    applier = FormalArtifactApplier(FakeFormalWrites(), executor)
    artifact = Artifact(
        kind="agent_updates",
        payload={
            "kind": "agent_updates",
            "updates": {
                "characters": [
                    {"action": "update", "name": "甲"},
                    {"action": "update", "name": "乙"},
                ]
            },
        },
    )
    artifact.novel_id = "novel-1"
    artifact.chapter_id = None

    await applier.apply(
        artifact,
        user_id="user-1",
        edited_content=None,
        selected_update_refs=[{"section": "characters", "index": 1}],
    )

    assert executor.updates == {"characters": [{"action": "update", "name": "乙"}]}
