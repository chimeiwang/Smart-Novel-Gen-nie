from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from inkforge_contracts.long_serial import (
    AbsenceSentinel,
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
    _long_serial_operation_definition,
    _require_long_serial_profile,
    _require_no_active_long_serial_mutation,
)
from inkforge_core.writing.recovery import deserialize_graph_snapshot
from inkforge_core.writing.schemas import LongSerialStartWritingRunRequest
from inkforge_core.writing.transaction_locks import LockedWritingRows
from pydantic import ValidationError

NOW = datetime(2026, 8, 5, 10, 0, tzinfo=UTC)


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
    def __init__(self) -> None:
        self.added: list[object] = []

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
