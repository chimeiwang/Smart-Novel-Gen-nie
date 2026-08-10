from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from inkforge_contracts.long_serial import (
    AbsenceSentinel,
    SelectionAttachmentMetadata,
    SelectionTarget,
    SourceBinding,
)
from inkforge_core.db.models import (
    Chapter,
    Novel,
    WritingMessage,
    WritingRunCommand,
    WritingTask,
)
from inkforge_core.errors import ApiError
from inkforge_core.writing import commands as commands_module
from inkforge_core.writing.commands import (
    WritingRunCommandRepository,
    _capture_selection_snapshot,
    _long_serial_operation_definition,
    _require_long_serial_profile,
    _require_no_active_long_serial_mutation,
    _validate_selection_attachment_metadata,
)
from inkforge_core.writing.idempotency import request_fingerprint
from inkforge_core.writing.recovery import deserialize_graph_snapshot
from inkforge_core.writing.schemas import (
    LongSerialStartWritingRunRequest,
    ResumeWritingRunRequest,
)
from inkforge_core.writing.transaction_locks import (
    LockedWritingRows,
    WritingLockRequest,
)
from pydantic import ValidationError

NOW = datetime(2026, 8, 5, 10, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_selection_snapshot_uses_unicode_codepoints_and_authoritative_hashes() -> None:
    content = "甲😀乙"
    target = SelectionTarget(
        resourceType="chapter_content",
        resourceId="chapter-1",
        baseUpdatedAt=NOW,
        baseContentHash=hashlib.sha256(content.encode()).hexdigest(),
        selectionStart=1,
        selectionEnd=2,
        selectedTextHash=hashlib.sha256("😀".encode()).hexdigest(),
    )

    class Session:
        async def scalar(self, statement: object) -> object:
            del statement
            return SimpleNamespace(
                id="chapter-1",
                novelId="novel-1",
                content=content,
                updatedAt=NOW,
            )

    snapshot = await _capture_selection_snapshot(
        Session(),
        novel_id="novel-1",
        chapter_id="chapter-1",
        operation="rewrite_chapter_selection",
        target=target,
    )
    assert snapshot["selectedText"] == "😀"
    assert snapshot["selectionStart"] == 1
    assert snapshot["selectionEnd"] == 2


@pytest.mark.asyncio
async def test_selection_snapshot_conflict_is_raised_before_task_creation() -> None:
    target = SelectionTarget(
        resourceType="chapter_content",
        resourceId="chapter-1",
        baseUpdatedAt=NOW,
        baseContentHash="a" * 64,
        selectionStart=0,
        selectionEnd=1,
        selectedTextHash="b" * 64,
    )

    class Session:
        async def scalar(self, statement: object) -> object:
            del statement
            return SimpleNamespace(
                id="chapter-1",
                novelId="novel-1",
                content="changed",
                updatedAt=NOW,
            )

    with pytest.raises(ApiError) as error:
        await _capture_selection_snapshot(
            Session(),
            novel_id="novel-1",
            chapter_id="chapter-1",
            operation="rewrite_chapter_selection",
            target=target,
        )
    assert error.value.status_code == 409


def valid_request_values() -> dict[str, object]:
    return {
        "clientRequestId": "long-start-00000001",
        "workflow": "long_serial",
        "novelId": "novel-1",
        "chapterId": "chapter-1",
        "writingSessionId": None,
        "operation": "write_chapter",
        "target": {"type": "chapter", "id": "chapter-1"},
        "scope": {"kind": "chapter", "chapterId": "chapter-1"},
        "targetWordCount": 4_000,
        "userInstruction": "  写出雨夜的不可逆选择  ",
    }


def source_bindings() -> tuple[SourceBinding, ...]:
    return (
        SourceBinding(
            resourceType="chapter",
            resourceId="chapter-1",
            exists=True,
            updatedAt=NOW,
            contentSha256="a" * 64,
            revision=None,
            absenceSentinel=None,
        ),
        SourceBinding(
            resourceType="outline",
            resourceId="novel:novel-1:outline",
            exists=False,
            updatedAt=None,
            contentSha256=None,
            revision=None,
            absenceSentinel=AbsenceSentinel(
                resourceType="novel", resourceId="novel-1"
            ),
        ),
    )


def test_long_serial_start_body_is_strict_and_preserves_instruction() -> None:
    request = LongSerialStartWritingRunRequest.model_validate(valid_request_values())

    assert request.workflow == "long_serial"
    assert request.userInstruction == "  写出雨夜的不可逆选择  "

    with pytest.raises(ValidationError, match="extra_forbidden"):
        LongSerialStartWritingRunRequest.model_validate(
            {**valid_request_values(), "selectedAgents": ["写作"]}
        )
    with pytest.raises(ValidationError):
        LongSerialStartWritingRunRequest.model_validate(
            {**valid_request_values(), "userInstruction": "   "}
        )


def test_long_serial_selection_request_requires_target_and_derives_unicode_length() -> None:
    values = {
        **valid_request_values(),
        "operation": "rewrite_chapter_selection",
        "selectionTarget": {
            "resourceType": "chapter_content",
            "resourceId": "chapter-1",
            "baseUpdatedAt": "2026-08-05T10:00:00Z",
            "baseContentHash": "a" * 64,
            "selectionStart": 0,
            "selectionEnd": 3,
            "selectedTextHash": "b" * 64,
        },
    }
    request = LongSerialStartWritingRunRequest.model_validate(values)
    assert request.selectionTarget is not None
    assert request.targetWordCount == 4_000

    with pytest.raises(ValidationError):
        LongSerialStartWritingRunRequest.model_validate(
            {**values, "selectionTarget": None}
        )

    with pytest.raises(ValidationError):
        LongSerialStartWritingRunRequest.model_validate(
            {
                **values,
                "operation": "rewrite_outline_selection",
                "selectionTarget": {**values["selectionTarget"], "resourceType": "chapter_content"},
            }
        )


def test_selection_attachment_metadata_is_strict_and_keeps_ui_preview_only() -> None:
    metadata = SelectionAttachmentMetadata.model_validate(
        {
            "resourceType": "chapter_content",
            "resourceId": "chapter-1",
            "sourceLabel": "第 1 章",
            "baseUpdatedAt": "2026-08-05T10:00:00Z",
            "baseContentHash": "a" * 64,
            "selectionStart": 1,
            "selectionEnd": 2,
            "selectedTextHash": "b" * 64,
            "selectionPreview": "😀",
        }
    )
    assert metadata.selectionPreview == "😀"
    with pytest.raises(ValidationError):
        SelectionAttachmentMetadata.model_validate(
            {**metadata.model_dump(mode="json"), "selectedText": "权威正文"}
        )


def test_selection_attachment_metadata_rejects_preview_not_derived_from_snapshot() -> None:
    target = SelectionTarget(
        resourceType="chapter_content",
        resourceId="chapter-1",
        baseUpdatedAt=NOW,
        baseContentHash="a" * 64,
        selectionStart=0,
        selectionEnd=2,
        selectedTextHash="b" * 64,
    )
    metadata = SelectionAttachmentMetadata(
        resourceType="chapter_content",
        resourceId="chapter-1",
        sourceLabel="第 1 章",
        baseUpdatedAt=NOW,
        baseContentHash="a" * 64,
        selectionStart=0,
        selectionEnd=2,
        selectedTextHash="b" * 64,
        selectionPreview="篡改",
    )
    with pytest.raises(ApiError):
        _validate_selection_attachment_metadata(
            metadata,
            target,
            {
                "resourceType": "chapter_content",
                "resourceId": "chapter-1",
                "baseUpdatedAt": NOW.isoformat(),
                "baseContentHash": "a" * 64,
                "selectionStart": 0,
                "selectionEnd": 2,
                "selectedTextHash": "b" * 64,
                "selectedText": "正文",
            },
        )

@pytest.mark.parametrize(
    "changes",
    [
        {"operation": "create_outline"},
        {"target": {"type": "chapter", "id": "chapter-2"}},
        {"scope": {"kind": "chapter", "chapterId": "chapter-2"}},
        {"scope": {"kind": "novel"}},
    ],
)
def test_long_serial_start_rejects_unsupported_operation_or_scope(
    changes: dict[str, object],
) -> None:
    request = LongSerialStartWritingRunRequest.model_validate(
        {**valid_request_values(), **changes}
    )

    with pytest.raises(ApiError) as error:
        _long_serial_operation_definition(request)

    assert error.value.status_code == 409
    assert error.value.code == "LONG_SCOPE_NOT_SUPPORTED"


def test_long_serial_start_derives_agents_from_public_definition() -> None:
    request = LongSerialStartWritingRunRequest.model_validate(valid_request_values())

    definition = _long_serial_operation_definition(request)

    assert definition.principalAgent == "写作"
    assert definition.reviewers == ("校验", "编辑")
    assert definition.artifactKind == "chapter_draft"


class ScalarSession:
    def __init__(self, values: Sequence[object | None]) -> None:
        self.values = list(values)
        self.statements: list[object] = []

    async def scalar(self, statement: object) -> object | None:
        self.statements.append(statement)
        return self.values.pop(0)


@pytest.mark.asyncio
async def test_long_serial_profile_is_checked_only_at_start() -> None:
    await _require_long_serial_profile(  # type: ignore[arg-type]
        ScalarSession(["long_serial"]), "novel-1"
    )

    with pytest.raises(ApiError) as error:
        await _require_long_serial_profile(  # type: ignore[arg-type]
            ScalarSession(["short_medium"]), "novel-1"
        )

    assert error.value.code == "LONG_WORKFLOW_MISMATCH"


class RowsResult:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[object, ...]]:
        return self._rows


class ExecuteSession:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.rows = rows

    async def execute(self, statement: object) -> RowsResult:
        del statement
        return RowsResult(self.rows)


def explicit_start_payload(operation: str) -> str:
    return json.dumps(
        {
            "_inkforgeCommand": {
                "schemaVersion": 1,
                "clientRequestId": f"request-{operation}-0001",
                "commandKind": "start",
                "resourceIdentity": {
                    "novelId": "novel-1",
                    "chapterId": "chapter-1",
                },
                "normalizedBody": {},
                "requestFingerprint": "b" * 64,
            },
            "job": {"workflow": "long_serial", "operation": operation},
        }
    )


@pytest.mark.asyncio
async def test_mutating_start_rejects_active_mutating_and_waiting_user_task() -> None:
    active = WritingTask(
        id="task-busy",
        novelId="novel-1",
        chapterId="chapter-1",
        phase="awaiting_user_review",
    )

    with pytest.raises(ApiError) as error:
        await _require_no_active_long_serial_mutation(  # type: ignore[arg-type]
            ExecuteSession([(active, explicit_start_payload("write_chapter"))]),
            "chapter-1",
        )

    assert error.value.code == "WRITING_TARGET_BUSY"
    assert error.value.details == {"taskId": "task-busy"}


@pytest.mark.asyncio
async def test_review_task_does_not_occupy_mutating_conflict_key() -> None:
    review = WritingTask(
        id="task-review",
        novelId="novel-1",
        chapterId="chapter-1",
        phase="active",
    )

    await _require_no_active_long_serial_mutation(  # type: ignore[arg-type]
        ExecuteSession([(review, explicit_start_payload("review_chapter"))]),
        "chapter-1",
    )


class TransactionSession:
    def __init__(self, scalar_values: list[object | None] | None = None) -> None:
        self.added: list[object] = []
        self.scalar_values = list(scalar_values or [])

    async def __aenter__(self) -> TransactionSession:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[None]:
        yield

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        for value in self.added:
            if isinstance(value, WritingTask):
                value.id = value.id or "task-created"
                value.createdAt = value.createdAt or NOW.replace(tzinfo=None)
                value.updatedAt = value.updatedAt or NOW.replace(tzinfo=None)
            elif isinstance(value, WritingRunCommand):
                value.id = value.id or "command-created"
                value.createdAt = value.createdAt or NOW.replace(tzinfo=None)
                value.updatedAt = value.updatedAt or NOW.replace(tzinfo=None)

    async def scalar(self, statement: object) -> object | None:
        del statement
        if not self.scalar_values:
            raise AssertionError("收到未预期的标量查询")
        return self.scalar_values.pop(0)


class SessionFactory:
    def __init__(self, session: TransactionSession) -> None:
        self.session = session

    def __call__(self) -> TransactionSession:
        return self.session


@pytest.mark.asyncio
async def test_long_serial_start_persists_authoritative_envelope_and_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = TransactionSession()
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory(session)
    )
    novel = Novel(id="novel-1", userId="user-1")
    target_chapter = Chapter(id="chapter-1", novelId="novel-1")

    async def no_replay(*args: object, **kwargs: object) -> None:
        del args, kwargs
        return None

    async def locked(*args: object, **kwargs: object) -> LockedWritingRows:
        del args, kwargs
        return LockedWritingRows(
            novel=novel,
            chapters=(target_chapter,),
            task=None,
            artifact=None,
            command=None,
        )

    async def no_op(*args: object, **kwargs: object) -> None:
        del args, kwargs

    async def captured(*args: object, **kwargs: object) -> tuple[SourceBinding, ...]:
        del args, kwargs
        return source_bindings()

    monkeypatch.setattr(commands_module, "acquire_idempotency_lock", no_op)
    monkeypatch.setattr(
        commands_module, "_resolve_long_serial_start_response", no_replay
    )
    monkeypatch.setattr(commands_module, "lock_writing_rows", locked)
    monkeypatch.setattr(commands_module, "_require_long_serial_profile", no_op)
    monkeypatch.setattr(
        commands_module, "_require_no_active_long_serial_mutation", no_op
    )
    monkeypatch.setattr(commands_module, "capture_chapter_source_bindings", captured)

    response = await repository.create_start_with_task(
        "user-1",
        LongSerialStartWritingRunRequest.model_validate(valid_request_values()),
    )

    task = next(value for value in session.added if isinstance(value, WritingTask))
    command = next(
        value for value in session.added if isinstance(value, WritingRunCommand)
    )
    envelope = json.loads(command.payloadJson)
    job = envelope["job"]
    assert response.id == task.id
    assert task.selectedAgents == "写作,校验,编辑"
    assert task.conversationHistory == json.dumps(
        [{"content": "  写出雨夜的不可逆选择  ", "role": "user"}],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert command.idempotencyKey == "v1:user-1:long-start-00000001"
    assert envelope["_inkforgeCommand"]["commandKind"] == "start"
    assert envelope["_inkforgeCommand"]["clientRequestId"] == (
        "long-start-00000001"
    )
    assert job["workflow"] == "long_serial"
    assert job["operation"] == "write_chapter"
    assert job["sourceBindings"][1]["exists"] is False
    assert "clientRequestId" not in job
    assert json.loads(task.graphStateJson)["scope"] == {
        "kind": "chapter",
        "chapterId": "chapter-1",
    }


@pytest.mark.asyncio
async def test_long_serial_selection_metadata_is_persisted_on_user_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = "hello😀world"
    selected = "ell"
    full_hash = hashlib.sha256(content.encode()).hexdigest()
    selected_hash = hashlib.sha256(selected.encode()).hexdigest()
    request_values = {
        **valid_request_values(),
        "writingSessionId": "session-1",
        "operation": "rewrite_chapter_selection",
        "selectionTarget": {
            "resourceType": "chapter_content",
            "resourceId": "chapter-1",
            "baseUpdatedAt": NOW.isoformat(),
            "baseContentHash": full_hash,
            "selectionStart": 1,
            "selectionEnd": 4,
            "selectedTextHash": selected_hash,
        },
        "selectionAttachmentMetadata": {
            "resourceType": "chapter_content",
            "resourceId": "chapter-1",
            "sourceLabel": "第 1 章",
            "baseUpdatedAt": NOW.isoformat(),
            "baseContentHash": full_hash,
            "selectionStart": 1,
            "selectionEnd": 4,
            "selectedTextHash": selected_hash,
            "selectionPreview": selected,
        },
    }
    session = TransactionSession()
    repository = WritingRunCommandRepository(SessionFactory(session))

    async def no_op(*args: object, **kwargs: object) -> None:
        del args, kwargs

    async def locked(*args: object, **kwargs: object) -> LockedWritingRows:
        del args, kwargs
        return LockedWritingRows(
            novel=Novel(id="novel-1", userId="user-1"),
            chapters=(Chapter(id="chapter-1", novelId="novel-1"),),
            task=None,
            artifact=None,
            command=None,
        )

    async def captured(*args: object, **kwargs: object) -> tuple[SourceBinding, ...]:
        del args, kwargs
        return source_bindings()

    async def snapshot(*args: object, **kwargs: object) -> dict[str, object]:
        del args, kwargs
        return {
            "resourceType": "chapter_content",
            "resourceId": "chapter-1",
            "baseUpdatedAt": NOW.isoformat(),
            "baseContentHash": full_hash,
            "selectionStart": 1,
            "selectionEnd": 4,
            "selectedTextHash": selected_hash,
            "selectedText": selected,
            "contextBefore": "h",
            "contextAfter": "o😀world",
            "sourceSnapshot": {
                "resourceType": "chapter_content",
                "resourceId": "chapter-1",
                "content": content,
                "updatedAt": NOW.isoformat(),
                "contentSha256": full_hash,
            },
        }

    monkeypatch.setattr(commands_module, "acquire_idempotency_lock", no_op)
    monkeypatch.setattr(commands_module, "_resolve_long_serial_start_response", no_op)
    monkeypatch.setattr(commands_module, "lock_writing_rows", locked)
    monkeypatch.setattr(commands_module, "_require_long_serial_profile", no_op)
    monkeypatch.setattr(commands_module, "_require_session_binding", no_op)
    monkeypatch.setattr(commands_module, "_require_no_active_long_serial_mutation", no_op)
    monkeypatch.setattr(commands_module, "capture_chapter_source_bindings", captured)
    monkeypatch.setattr(commands_module, "_capture_selection_snapshot", snapshot)
    monkeypatch.setattr(commands_module, "_touch_writing_session", no_op)

    await repository.create_start_with_task(
        "user-1", LongSerialStartWritingRunRequest.model_validate(request_values)
    )
    message = next(value for value in session.added if isinstance(value, WritingMessage))
    assert json.loads(message.metadata_ or "{}")["source"]["selectionPreview"] == selected


def _long_serial_start_envelope() -> str:
    job = {
        "version": 1,
        "workflow": "long_serial",
        "chapterId": "chapter-1",
        "writingSessionId": None,
        "operation": "write_chapter",
        "target": {"type": "chapter", "id": "chapter-1"},
        "scope": {"kind": "chapter", "chapterId": "chapter-1"},
        "sourceBindings": [
            binding.model_dump(mode="json") for binding in source_bindings()
        ],
        "targetWordCount": 4_000,
        "userInstruction": "写出雨夜的不可逆选择",
        "resume": False,
        "resumeInput": None,
    }
    return json.dumps(
        {
            "_inkforgeCommand": {
                "schemaVersion": 1,
                "clientRequestId": "long-start-00000001",
                "commandKind": "start",
                "resourceIdentity": {
                    "novelId": "novel-1",
                    "chapterId": "chapter-1",
                },
                "normalizedBody": {"workflow": "long_serial"},
                "requestFingerprint": "b" * 64,
            },
            "job": job,
        }
    )


@pytest.mark.asyncio
async def test_long_serial_resume_reuses_authoritative_start_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owned_task = WritingTask(
        id="task-1",
        novelId="novel-1",
        chapterId="chapter-1",
        writingSessionId=None,
        phase="active",
        targetWordCount=4_000,
        selectedAgents="写作,校验,编辑",
        createdAt=NOW.replace(tzinfo=None),
        updatedAt=NOW.replace(tzinfo=None),
    )
    owned_task.graphStateJson = json.dumps(
        {
            "taskId": owned_task.id,
            "userId": "user-1",
            "novelId": owned_task.novelId,
            "chapterId": owned_task.chapterId,
            "targetWordCount": owned_task.targetWordCount,
            "conversationHistory": [],
            "phase": "active",
            "eventSequence": 1,
            "currentOperation": {"kind": "write_chapter"},
            "operationStage": "执行创作操作",
            "callbackJobId": "command-current",
        }
    )
    source_command = WritingRunCommand(
        id="command-current",
        taskId=owned_task.id,
        kind="start",
        payloadJson=_long_serial_start_envelope(),
        idempotencyKey="key-command-current",
        status="succeeded",
        attemptCount=0,
        nextAttemptAt=NOW.replace(tzinfo=None),
        createdAt=NOW.replace(tzinfo=None),
        updatedAt=NOW.replace(tzinfo=None),
    )
    session = TransactionSession([None, _long_serial_start_envelope()])
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory(session)
    )
    order: list[str] = []
    lock_requests: list[WritingLockRequest] = []

    async def advisory(*args: object, **kwargs: object) -> None:
        del args, kwargs
        order.append("advisory")

    async def no_replay(*args: object, **kwargs: object) -> None:
        del args, kwargs
        order.append("replay")

    async def identity(*args: object, **kwargs: object) -> tuple[str, str]:
        del args, kwargs
        order.append("identity")
        return "novel-1", "chapter-1"

    async def locked(
        *args: object, **kwargs: object
    ) -> LockedWritingRows:
        del args
        request = kwargs["request"]
        assert isinstance(request, WritingLockRequest)
        order.append("lock")
        lock_requests.append(request)
        return LockedWritingRows(
            novel=Novel(id="novel-1", userId="user-1"),
            chapters=(Chapter(id="chapter-1", novelId="novel-1"),),
            task=owned_task,
            artifact=None,
            command=source_command,
        )

    async def unexpected_owned_task(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("resume 不得先锁 WritingTask")

    async def no_active_command(*args: object, **kwargs: object) -> None:
        del args, kwargs
        order.append("busy")

    async def current_command_id(*args: object, **kwargs: object) -> str:
        del args, kwargs
        order.append("current")
        return source_command.id

    async def supersede(*args: object, **kwargs: object) -> None:
        del args, kwargs
        order.append("supersede")

    monkeypatch.setattr(commands_module, "acquire_idempotency_lock", advisory)
    monkeypatch.setattr(
        commands_module,
        "_resolve_long_serial_resume_response",
        no_replay,
        raising=False,
    )
    monkeypatch.setattr(repository, "_require_owned_task_identity", identity)
    monkeypatch.setattr(repository, "_find_current_command_id", current_command_id)
    monkeypatch.setattr(repository, "_require_owned_task", unexpected_owned_task)
    monkeypatch.setattr(commands_module, "lock_writing_rows", locked)
    monkeypatch.setattr(repository, "_require_no_active_command", no_active_command)
    monkeypatch.setattr(commands_module, "supersede_waiting_for_new_command", supersede)

    await repository.create_resume_with_message(
        "user-1",
        "task-1",
        ResumeWritingRunRequest(
            clientRequestId="long-resume-000001",
            userMessage="保留当前视角，继续",
        ),
    )

    command = next(
        value for value in session.added if isinstance(value, WritingRunCommand)
    )
    envelope = json.loads(command.payloadJson)
    metadata = envelope["_inkforgeCommand"]
    job = envelope["job"]
    normalized_body = {
        "writingSessionId": None,
        "userMessage": "保留当前视角，继续",
    }
    assert command.idempotencyKey == "v1:user-1:long-resume-000001"
    assert metadata["commandKind"] == "resume"
    assert metadata["resourceIdentity"] == {"taskId": "task-1"}
    assert metadata["normalizedBody"] == normalized_body
    assert metadata["requestFingerprint"] == request_fingerprint(
        command_kind="resume",
        resource_identity={"taskId": "task-1"},
        body=normalized_body,
    )
    assert job["workflow"] == "long_serial"
    assert job["operation"] == "write_chapter"
    assert job["target"] == {"type": "chapter", "id": "chapter-1"}
    assert job["scope"] == {"kind": "chapter", "chapterId": "chapter-1"}
    assert job["sourceBindings"][0]["resourceType"] == "chapter"
    assert job["targetWordCount"] == 4_000
    assert job["userInstruction"] == "写出雨夜的不可逆选择"
    assert job["resume"] is True
    assert job["resumeInput"] == {"userMessage": "保留当前视角，继续"}
    assert lock_requests == [
        WritingLockRequest(
            novel_id="novel-1",
            chapter_ids=("chapter-1",),
            task_id="task-1",
            command_id="command-current",
        )
    ]
    assert order == [
        "advisory",
        "replay",
        "identity",
        "current",
        "lock",
        "replay",
        "busy",
        "supersede",
    ]


@pytest.mark.asyncio
async def test_second_idempotency_check_wins_before_busy_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = TransactionSession()
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory(session)
    )
    existing = commands_module.WritingRunResponse(
        id="task-existing",
        novelId="novel-1",
        chapterId="chapter-1",
        writingSessionId=None,
        phase="idle",
        targetWordCount=4_000,
        selectedAgents=["写作", "校验", "编辑"],
        createdAt=NOW,
        updatedAt=NOW,
        commandId="command-existing",
        commandStatus="pending",
    )
    order: list[str] = []
    replay_values = [None, existing]

    async def replay(*args: object, **kwargs: object) -> object:
        del args, kwargs
        order.append("replay")
        return replay_values.pop(0)

    async def no_op(*args: object, **kwargs: object) -> None:
        del args, kwargs

    async def locked(*args: object, **kwargs: object) -> LockedWritingRows:
        del args, kwargs
        order.append("lock")
        return LockedWritingRows(
            novel=Novel(id="novel-1", userId="user-1"),
            chapters=(Chapter(id="chapter-1", novelId="novel-1"),),
            task=None,
            artifact=None,
            command=None,
        )

    async def profile(*args: object, **kwargs: object) -> None:
        del args, kwargs
        order.append("profile")

    async def busy(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("第二次幂等命中后不应检查目标占用")

    monkeypatch.setattr(commands_module, "acquire_idempotency_lock", no_op)
    monkeypatch.setattr(commands_module, "_resolve_long_serial_start_response", replay)
    monkeypatch.setattr(commands_module, "lock_writing_rows", locked)
    monkeypatch.setattr(commands_module, "_require_long_serial_profile", profile)
    monkeypatch.setattr(
        commands_module, "_require_no_active_long_serial_mutation", busy
    )

    response = await repository.create_start_with_task(
        "user-1",
        LongSerialStartWritingRunRequest.model_validate(valid_request_values()),
    )

    assert response.id == "task-existing"
    assert order == ["replay", "lock", "profile", "replay"]
    assert session.added == []


@pytest.mark.asyncio
async def test_long_serial_session_binding_is_rechecked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = valid_request_values()
    values["writingSessionId"] = "session-1"
    session = TransactionSession()
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory(session)
    )
    observed: list[tuple[str, str, str, str]] = []

    async def no_replay(*args: object, **kwargs: object) -> None:
        del args, kwargs

    async def locked(*args: object, **kwargs: object) -> LockedWritingRows:
        del args, kwargs
        return LockedWritingRows(
            novel=Novel(id="novel-1", userId="user-1"),
            chapters=(Chapter(id="chapter-1", novelId="novel-1"),),
            task=None,
            artifact=None,
            command=None,
        )

    async def no_op(*args: object, **kwargs: object) -> None:
        del args, kwargs

    async def binding(
        _session: object,
        user_id: str,
        session_id: str,
        novel_id: str,
        chapter_id: str,
    ) -> None:
        observed.append((user_id, session_id, novel_id, chapter_id))

    async def captured(*args: object, **kwargs: object) -> tuple[SourceBinding, ...]:
        del args, kwargs
        return source_bindings()

    monkeypatch.setattr(commands_module, "acquire_idempotency_lock", no_op)
    monkeypatch.setattr(commands_module, "_resolve_long_serial_start_response", no_replay)
    monkeypatch.setattr(commands_module, "lock_writing_rows", locked)
    monkeypatch.setattr(commands_module, "_require_long_serial_profile", no_op)
    monkeypatch.setattr(commands_module, "_require_session_binding", binding)
    monkeypatch.setattr(
        commands_module, "_require_no_active_long_serial_mutation", no_op
    )
    monkeypatch.setattr(commands_module, "capture_chapter_source_bindings", captured)
    monkeypatch.setattr(commands_module, "_touch_writing_session", no_op)

    response = await repository.create_start_with_task(
        "user-1", LongSerialStartWritingRunRequest.model_validate(values)
    )

    task = next(value for value in session.added if isinstance(value, WritingTask))
    snapshot = deserialize_graph_snapshot(
        task.graphStateJson or "",
        expected_task_id=response.id,
        expected_user_id="user-1",
        expected_novel_id="novel-1",
        expected_chapter_id="chapter-1",
    )
    raw_snapshot = json.loads(task.graphStateJson or "{}")

    assert snapshot.task_id == response.id
    assert raw_snapshot["workflow"] == "long_serial"
    assert raw_snapshot["operation"] == "write_chapter"
    assert raw_snapshot["target"] == {"type": "chapter", "id": "chapter-1"}
    assert raw_snapshot["scope"] == {
        "kind": "chapter",
        "chapterId": "chapter-1",
    }
    assert raw_snapshot["sourceBindings"][0]["resourceType"] == "chapter"
    assert observed == [("user-1", "session-1", "novel-1", "chapter-1")]
    assert any(isinstance(value, WritingMessage) for value in session.added)
