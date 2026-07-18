import pytest
from inkforge_contracts import ShortStoryChapterDraft, ShortStoryOutlineDraft
from inkforge_core.app import create_app
from inkforge_core.errors import ApiError
from inkforge_core.reviews.apply import resolve_apply_target
from inkforge_core.reviews.diff import ArtifactPatchError, apply_text_replace_patch
from inkforge_core.reviews.repository import ReviewRepository
from inkforge_core.reviews.schemas import (
    CreateArtifactRequest,
    ReviewArtifactDecisionRequest,
    SaveShortStoryOutlineRequest,
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


def _short_outline_payload() -> dict[str, object]:
    return {
        "kind": "outline_draft",
        "storyLengthProfile": "short_medium",
        "originalInspiration": "一封来自未来的信。",
        "corePremise": "主人公必须决定是否相信未来的自己。",
        "anchors": {"mustKeep": ["未来来信"], "confirmed": [], "avoid": []},
        "sections": [{"id": "sec-1", "title": "来信", "events": "主人公收到信。"}],
        "content": "服务端将重建此字段",
        "changeSummary": "首次生成",
        "anchorChanges": [],
    }


def test_short_outline_payload_is_strongly_validated_without_breaking_legacy_outline() -> None:
    request = CreateArtifactRequest.model_validate(
        {
            "runId": "run-1",
            "taskId": "task-1",
            "novelId": "novel-1",
            "artifactKey": "outline-1",
            "kind": "outline_draft",
            "status": "awaiting_user",
            "payload": _short_outline_payload(),
            "createdByAgent": "剧情",
        }
    )
    assert isinstance(request.payload, ShortStoryOutlineDraft)
    assert request.payload.content.startswith("# 原始灵感")

    with pytest.raises(ValidationError):
        CreateArtifactRequest.model_validate(
            {
                **request.model_dump(mode="json"),
                "payload": {**_short_outline_payload(), "targetWordCount": 1000},
            }
        )

    legacy = CreateArtifactRequest.model_validate(
        {
            "runId": "run-1",
            "taskId": "task-1",
            "novelId": "novel-1",
            "kind": "outline_draft",
            "status": "draft",
            "payload": {"kind": "outline_draft", "content": "旧长篇大纲"},
            "createdByAgent": "剧情",
        }
    )
    assert legacy.payload == {"kind": "outline_draft", "content": "旧长篇大纲"}


def test_short_story_chapter_payload_is_strongly_typed() -> None:
    content = "甲" * 6000
    request = CreateArtifactRequest.model_validate(
        {
            "runId": "run-1",
            "taskId": "task-1",
            "novelId": "novel-1",
            "chapterId": "chapter-1",
            "artifactKey": "short-story-draft",
            "kind": "chapter_draft",
            "status": "under_review",
            "payload": {
                "kind": "chapter_draft",
                "storyLengthProfile": "short_medium",
                "content": content,
                "metadata": {
                    "sourceOutlineArtifactId": "outline-1",
                    "sourceOutlineRevision": 1,
                    "sourceOutlineHash": "a" * 64,
                    "targetWordCount": 6000,
                    "actualWordCount": 6000,
                    "targetChapterId": "chapter-1",
                    "baseChapterHash": "b" * 64,
                    "generationCommandId": "command-1",
                    "automaticRewriteCount": 0,
                    "generationReason": "user_request",
                },
            },
            "createdByAgent": "写作",
        }
    )

    assert isinstance(request.payload, ShortStoryChapterDraft)
    with pytest.raises(ValidationError):
        CreateArtifactRequest.model_validate(
            {
                **request.model_dump(mode="json"),
                "payload": {
                    **request.payload.model_dump(mode="json"),
                    "content": "字数被篡改",
                },
            }
        )


def test_decisions_require_revision_and_short_outline_edit_has_no_content_shortcut() -> None:
    with pytest.raises(ValidationError):
        ReviewArtifactDecisionRequest.model_validate(
            {"clientRequestId": "request-00000001", "decision": "approve"}
        )
    decision = ReviewArtifactDecisionRequest.model_validate(
        {
            "clientRequestId": "request-00000001",
            "decision": "approve",
            "expectedRevision": 2,
        }
    )
    assert decision.expectedRevision == 2

    edit = SaveShortStoryOutlineRequest.model_validate(
        {
            "expectedRevision": 2,
            "corePremise": "新的核心前提",
            "anchors": {"mustKeep": [], "confirmed": [], "avoid": []},
            "sections": [{"title": "开端", "events": "事件发生。"}],
            "changeSummary": "用户直接编辑",
        }
    )
    assert edit.sections[0].id is None
    with pytest.raises(ValidationError):
        SaveShortStoryOutlineRequest.model_validate(
            {**edit.model_dump(), "content": "不接受用户维护派生全文"}
        )


def test_public_openapi_exposes_short_outline_and_revision_routes() -> None:
    document = create_app(testing=True).openapi()
    schemas = document["components"]["schemas"]
    paths = document["paths"]

    assert "ShortStoryOutlineDraft" in schemas
    assert "ShortStoryOutlineSection" in schemas
    assert "ShortStoryChapterDraft" in schemas
    assert "ShortStoryArtifactsResponse" in schemas
    assert "ShortStoryTaskStatus" in schemas
    assert "/api/v1/review-artifacts/{artifact_id}/revisions" in paths
    assert "/api/v1/review-artifacts/{artifact_id}/outline" in paths
    assert "/api/v1/novels/{novel_id}/short-story/artifacts" in paths
