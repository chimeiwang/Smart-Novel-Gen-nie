import pytest
from inkforge_core.errors import ApiError
from inkforge_core.reviews.apply import resolve_apply_target
from inkforge_core.reviews.diff import ArtifactPatchError, apply_text_replace_patch
from inkforge_core.reviews.repository import ReviewRepository
from inkforge_core.reviews.schemas import (
    CreateArtifactRequest,
    ReviewArtifactDecisionRequest,
    assert_status_transition,
)
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


@pytest.mark.parametrize("value", [True, False, 0, -1])
def test_create_artifact_expected_revision_is_strict_positive_integer(value: object) -> None:
    with pytest.raises(ValidationError):
        CreateArtifactRequest.model_validate(
            {
                "runId": "run-1",
                "taskId": "task-1",
                "novelId": "novel-1",
                "jobId": "job-1",
                "kind": "chapter_draft",
                "status": "under_review",
                "payload": {"kind": "chapter_draft", "content": "正文"},
                "createdByAgent": "写作",
                "expectedRevision": value,
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


def test_artifact_decision_expected_revision_rejects_boolean() -> None:
    with pytest.raises(ValidationError):
        ReviewArtifactDecisionRequest.model_validate(
            {
                "clientRequestId": "client-request-1234",
                "expectedRevision": True,
                "decision": "revise",
            }
        )


def test_artifact_decision_omitted_engine_version_preserves_v1_shape() -> None:
    request = ReviewArtifactDecisionRequest.model_validate(
        {
            "clientRequestId": "client-request-v1-0001",
            "expectedRevision": 3,
            "decision": "approve",
            "editedContent": "V1 全文编辑保持兼容",
            "selectedUpdateRefs": [{"section": "characters", "index": 0}],
        }
    )

    assert request.engineVersion == 1
    assert request.editedContent == "V1 全文编辑保持兼容"
    assert request.selectedUpdateRefs is not None


def test_artifact_decision_v2_accepts_selection_approve_and_explicit_revise() -> None:
    approve = ReviewArtifactDecisionRequest.model_validate(
        {
            "engineVersion": 2,
            "clientRequestId": "client-request-v2-approve",
            "expectedRevision": 7,
            "decision": "approve",
            "editedReplacement": "只替换冻结选区",
        }
    )
    revise = ReviewArtifactDecisionRequest.model_validate(
        {
            "engineVersion": 2,
            "clientRequestId": "client-request-v2-revise",
            "expectedRevision": 7,
            "decision": "revise",
            "userMessage": "保留含义，压缩动作描写",
        }
    )

    assert approve.engineVersion == revise.engineVersion == 2
    assert approve.editedReplacement == "只替换冻结选区"
    assert revise.userMessage == "保留含义，压缩动作描写"


@pytest.mark.parametrize(
    ("decision", "extra"),
    [
        ("approve", {"editedContent": "禁止用全文伪装选区"}),
        ("approve", {"selectedUpdateRefs": [{"section": "characters"}]}),
        ("approve", {"editedReplacement": "   "}),
        ("discard", {"editedReplacement": "不能在丢弃时编辑"}),
        ("revise", {}),
        ("revise", {"userMessage": "   "}),
    ],
)
def test_artifact_decision_v2_rejects_ambiguous_or_incomplete_shape(
    decision: str, extra: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        ReviewArtifactDecisionRequest.model_validate(
            {
                "engineVersion": 2,
                "clientRequestId": "client-request-v2-invalid",
                "expectedRevision": 1,
                "decision": decision,
                **extra,
            }
        )
