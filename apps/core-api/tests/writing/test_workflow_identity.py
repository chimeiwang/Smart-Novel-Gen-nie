from __future__ import annotations

import json

import pytest
from inkforge_contracts.short_story import ShortStoryAnchors, ShortStoryOutlineDraft
from inkforge_core.db.models import Chapter, Novel, ReviewArtifact, WritingBible
from inkforge_core.errors import ApiError
from inkforge_core.writing.commands import (
    WritingCommandRecord,
    _assert_start_command_semantics,
    _latest_workflow_identity,
    _resolve_start_workflow_identity,
)
from inkforge_core.writing.records import TaskRecord
from inkforge_core.writing.schemas import StartWritingRunRequest


class RowResult:
    def __init__(self, value: tuple[object, ...] | None) -> None:
        self.value = value

    def one_or_none(self) -> tuple[object, ...] | None:
        return self.value


class IdentitySession:
    def __init__(
        self,
        row: tuple[object, ...] | None,
        *,
        scalars: list[object | None] | None = None,
    ) -> None:
        self.row = row
        self.scalars = list(scalars or [])

    async def execute(self, statement: object) -> RowResult:
        del statement
        return RowResult(self.row)

    async def scalar(self, statement: object) -> object | None:
        del statement
        if not self.scalars:
            raise AssertionError("收到未预期的 scalar 查询")
        return self.scalars.pop(0)


def _request(
    *, operation: str = "develop_short_outline", target: int = 6000
) -> StartWritingRunRequest:
    return StartWritingRunRequest.model_validate(
        {
            "clientRequestId": "request-00000001",
            "novelId": "novel-1",
            "chapterId": "chapter-1",
            "workflowKind": "short_medium",
            "operation": operation,
            "targetWordCount": target,
            "userMessage": "生成完整大纲",
        }
    )


def _rows(
    *,
    profile: str = "short_medium",
    target: int | None = 6000,
    chapter_title: str = "正文",
):
    novel = Novel(id="novel-1", userId="user-1", name="测试", summary="原始灵感")
    chapter = Chapter(id="chapter-1", novelId="novel-1", title=chapter_title, order=1)
    bible = WritingBible(
        id="bible-1",
        novelId="novel-1",
        storyLengthProfile=profile,
        targetTotalWordCount=target,
    )
    return novel, chapter, bible


@pytest.mark.asyncio
@pytest.mark.parametrize("target", [6000, 80000])
async def test_core_resolves_short_outline_identity_from_persisted_bible(target: int) -> None:
    identity = await _resolve_start_workflow_identity(
        IdentitySession(_rows(target=target), scalars=[1]),  # type: ignore[arg-type]
        "user-1",
        _request(target=target),
    )

    assert identity == {
        "workflowKind": "short_medium",
        "operation": "develop_short_outline",
        "targetTotalWordCount": target,
        "source": {
            "kind": "short_outline_inspiration",
            "originalInspiration": "原始灵感",
        },
    }


@pytest.mark.asyncio
async def test_legacy_short_project_with_single_renamed_chapter_can_start() -> None:
    identity = await _resolve_start_workflow_identity(
        IdentitySession(_rows(chapter_title="旧项目第一章"), scalars=[1]),  # type: ignore[arg-type]
        "user-1",
        _request(),
    )

    assert identity["workflowKind"] == "short_medium"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("rows", "scalars", "code"),
    [
        (_rows(profile="long_serial"), [], "WRITING_WORKFLOW_MISMATCH"),
        (_rows(target=5999), [], "SHORT_STORY_TARGET_INVALID"),
        (_rows(target=80001), [], "SHORT_STORY_TARGET_INVALID"),
        (_rows(target=7000), [], "SHORT_STORY_TARGET_MISMATCH"),
        (_rows(), [2], "SHORT_STORY_CHAPTER_INVALID"),
    ],
)
async def test_core_rejects_persisted_short_identity_mismatch_before_task_creation(
    rows: tuple[Novel, Chapter, WritingBible],
    scalars: list[object | None],
    code: str,
) -> None:
    with pytest.raises(ApiError) as caught:
        await _resolve_start_workflow_identity(
            IdentitySession(rows, scalars=scalars),  # type: ignore[arg-type]
            "user-1",
            _request(),
        )
    assert caught.value.code == code


@pytest.mark.asyncio
async def test_write_short_story_uses_latest_applied_strong_outline_source() -> None:
    payload = ShortStoryOutlineDraft(
        originalInspiration="原始灵感",
        corePremise="守夜人必须决定是否让全城记住被抹去的人。",
        anchors=ShortStoryAnchors(mustKeep=["遗忘"], confirmed=[], avoid=[]),
        sections=[{"id": "section-1", "title": "异变", "events": "发现遗忘规律。"}],
    )
    artifact = ReviewArtifact(
        id="artifact-1",
        novelId="novel-1",
        chapterId="chapter-1",
        kind="outline_draft",
        status="applied",
        revision=3,
        payloadJson=json.dumps(payload.model_dump(mode="json"), ensure_ascii=False),
    )

    identity = await _resolve_start_workflow_identity(
        IdentitySession(_rows(), scalars=[1, artifact]),  # type: ignore[arg-type]
        "user-1",
        _request(operation="write_short_story"),
    )

    assert identity["source"]["outlineArtifactId"] == "artifact-1"
    assert identity["source"]["outlineRevision"] == 3
    assert len(identity["source"]["outlineHash"]) == 64


@pytest.mark.asyncio
async def test_write_short_story_rejects_latest_outline_when_it_is_not_applied() -> None:
    latest = ReviewArtifact(
        id="artifact-new",
        novelId="novel-1",
        chapterId="chapter-1",
        kind="outline_draft",
        status="awaiting_user",
        revision=4,
        payloadJson="{}",
    )

    with pytest.raises(ApiError) as caught:
        await _resolve_start_workflow_identity(
            IdentitySession(_rows(), scalars=[1, latest]),  # type: ignore[arg-type]
            "user-1",
            _request(operation="write_short_story"),
        )
    assert caught.value.code == "SHORT_STORY_OUTLINE_NOT_APPROVED"


def test_start_idempotency_key_cannot_be_reused_with_different_semantics() -> None:
    command = WritingCommandRecord(
        id="command-1",
        task=TaskRecord(
            id="task-1",
            user_id="user-1",
            novel_id="novel-1",
            chapter_id="chapter-1",
            writing_session_id=None,
            phase="idle",
            graph_state_json=None,
        ),
        kind="start",
        payload={
            "startRequest": _request().model_dump(mode="json"),
        },
        status="pending",
        attempt_count=0,
    )
    _assert_start_command_semantics(command, _request())
    with pytest.raises(ApiError) as caught:
        _assert_start_command_semantics(command, _request(target=80000))
    assert caught.value.code == "IDEMPOTENCY_KEY_REUSED"


@pytest.mark.asyncio
async def test_resume_identity_is_copied_from_latest_authoritative_command() -> None:
    source = {
        "kind": "short_outline_inspiration",
        "originalInspiration": "绝不能从本轮用户消息重猜的灵感",
    }
    serialized = json.dumps(
        {
            "version": 1,
            "resume": False,
            "chapterId": "chapter-1",
            "writingSessionId": None,
            "resumeInput": None,
            "workflowKind": "short_medium",
            "operation": "develop_short_outline",
            "targetTotalWordCount": 6000,
            "source": source,
        },
        ensure_ascii=False,
    )

    identity = await _latest_workflow_identity(
        IdentitySession(None, scalars=[serialized]),  # type: ignore[arg-type]
        "task-1",
    )

    assert identity == {
        "workflowKind": "short_medium",
        "operation": "develop_short_outline",
        "targetTotalWordCount": 6000,
        "source": source,
    }


@pytest.mark.asyncio
async def test_legacy_task_without_identity_is_explicitly_long_serial() -> None:
    identity = await _latest_workflow_identity(
        IdentitySession(None, scalars=[json.dumps({"version": 1, "resume": False})]),  # type: ignore[arg-type]
        "task-1",
    )

    assert identity == {
        "workflowKind": "long_serial",
        "operation": None,
        "targetTotalWordCount": None,
        "source": None,
    }
