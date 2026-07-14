import pytest
from inkforge_core.errors import ApiError
from inkforge_core.reviews.apply import resolve_apply_target
from inkforge_core.reviews.diff import ArtifactPatchError, apply_text_replace_patch
from inkforge_core.reviews.repository import ReviewRepository
from inkforge_core.reviews.schemas import CreateArtifactRequest, assert_status_transition
from inkforge_core.reviews.updates import filter_agent_updates_by_selection
from pydantic import ValidationError


class TaskArtifactResult:
    def scalar_one_or_none(self):
        return None


class TaskArtifactSession:
    def __init__(self, owned_task: object | None) -> None:
        self.owned_task = owned_task
        self.statements: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback

    async def scalar(self, statement):
        self.statements.append(str(statement))
        return self.owned_task

    async def execute(self, statement):
        self.statements.append(str(statement))
        return TaskArtifactResult()


@pytest.mark.asyncio
async def test_foreign_task_artifact_is_not_disclosed() -> None:
    session = TaskArtifactSession(owned_task=None)
    repository = ReviewRepository(lambda: session)  # type: ignore[arg-type]

    with pytest.raises(ApiError) as caught:
        await repository.get_task_artifact("other-user", "task-1")

    assert caught.value.status_code == 404
    assert caught.value.code == "WRITING_TASK_NOT_FOUND"


@pytest.mark.asyncio
async def test_owned_task_without_artifact_returns_none() -> None:
    session = TaskArtifactSession(owned_task="task-1")
    repository = ReviewRepository(lambda: session)  # type: ignore[arg-type]

    assert await repository.get_task_artifact("owner", "task-1") is None
    assert '"WritingTask"' in session.statements[0]


def test_artifact_status_transition_rejects_skipping_user_confirmation() -> None:
    assert_status_transition("awaiting_user", "applying")
    with pytest.raises(ValueError, match="待审核草案不能"):
        assert_status_transition("draft", "applied")
    with pytest.raises(ValueError, match="待审核草案不能"):
        assert_status_transition("applied", "draft")


def test_text_patch_requires_exactly_one_match() -> None:
    payload = {"kind": "chapter_draft", "content": "前天接活。"}
    assert apply_text_replace_patch(payload, "前天", "今天") == {
        "kind": "chapter_draft",
        "content": "今天接活。",
    }
    with pytest.raises(ArtifactPatchError, match="实际匹配 0 次"):
        apply_text_replace_patch(payload, "昨天", "今天")
    with pytest.raises(ArtifactPatchError, match="实际匹配 2 次"):
        apply_text_replace_patch(
            {"kind": "chapter_draft", "content": "前天。前天。"},
            "前天",
            "今天",
        )


def test_revision_brief_can_never_be_applied_to_formal_data() -> None:
    assert resolve_apply_target({"kind": "revision_brief", "content": "请重写"}) is None
    assert resolve_apply_target({"kind": "chapter_draft", "content": "正文"}) == "chapter_content"


def test_partial_agent_updates_preserve_only_selected_items() -> None:
    updates = {
        "characters": [
            {"action": "update", "name": "甲"},
            {"action": "update", "name": "乙"},
        ],
        "outlineAdjustments": [{"action": "create", "title": "第一卷"}],
        "outlineTreeMode": "replace",
        "worldSetting": "新世界设定",
    }

    result = filter_agent_updates_by_selection(
        updates,
        [
            {"section": "characters", "index": 1},
            {"section": "outlineAdjustments"},
        ],
    )

    assert result == {
        "characters": [{"action": "update", "name": "乙"}],
        "outlineAdjustments": [{"action": "create", "title": "第一卷"}],
        "outlineTreeMode": "replace",
    }


def test_internal_artifact_request_is_strict_and_kind_matches_payload() -> None:
    with pytest.raises(ValidationError):
        CreateArtifactRequest.model_validate(
            {
                "runId": "run-1",
                "taskId": "task-1",
                "novelId": "novel-1",
                "kind": "chapter_draft",
                "status": "awaiting_user",
                "payload": {"kind": "outline_draft", "content": "大纲"},
                "createdByAgent": "写作",
            }
        )
    with pytest.raises(ValidationError):
        CreateArtifactRequest.model_validate(
            {
                "runId": "run-1",
                "taskId": "task-1",
                "novelId": "novel-1",
                "kind": "chapter_draft",
                "status": "awaiting_user",
                "payload": {"kind": "chapter_draft", "content": "正文"},
                "createdByAgent": "写作",
                "unexpected": True,
            }
        )
