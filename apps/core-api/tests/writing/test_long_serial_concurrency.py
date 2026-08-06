from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from inkforge_core.db.models import (
    Chapter,
    Novel,
    ReviewArtifact,
    WritingRunCommand,
    WritingTask,
)
from inkforge_core.reviews import decision_orchestrator as decision_module
from inkforge_core.reviews import repository as review_repository_module
from inkforge_core.reviews.decision_orchestrator import (
    ReviewDecisionDependencies,
    ReviewDecisionOrchestrator,
)
from inkforge_core.reviews.repository import ArtifactRecord, ReviewRepository
from inkforge_core.reviews.schemas import (
    ArtifactDecisionResponse,
    ReviewArtifactDecisionRequest,
)
from inkforge_core.writing.commands import WritingCommandRecord
from inkforge_core.writing.records import TaskRecord
from inkforge_core.writing.schemas import WritingRunOutcome, WritingRunOutcomeResult
from inkforge_core.writing.sse import InMemoryWritingEventStore, stream_task_events
from inkforge_core.writing.transaction_locks import (
    LockedWritingRows,
    WritingLockRequest,
    lock_writing_rows,
)


class _Transaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback


class _OuterSession:
    def begin(self) -> _Transaction:
        return _Transaction()

    async def __aenter__(self) -> _OuterSession:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback

    async def connection(self) -> object:
        return object()


class _OuterFactory:
    def __call__(self) -> _OuterSession:
        return _OuterSession()


def _task() -> TaskRecord:
    return TaskRecord(
        id="task-1",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id="chapter-1",
        writing_session_id="session-1",
        phase="awaiting_user_review",
        graph_state_json="{}",
    )


def _artifact() -> ArtifactRecord:
    now = datetime(2026, 8, 6, tzinfo=UTC)
    return ArtifactRecord(
        id="artifact-1",
        novel_id="novel-1",
        chapter_id="chapter-1",
        task_id="task-1",
        workflow_run_id="run-1",
        artifact_key="draft-1",
        kind="chapter_draft",
        status="awaiting_user",
        title="正文草案",
        summary=None,
        payload={"kind": "chapter_draft", "content": "正文"},
        diff=None,
        created_by_agent="写作",
        updated_by_agent=None,
        reviewer_agent=None,
        revision=1,
        created_at=now,
        updated_at=now,
    )


class _Lookup:
    def __init__(self, trace: list[str]) -> None:
        self.trace = trace

    async def get_by_idempotency_key(
        self, user_id: str, client_request_id: str
    ) -> WritingCommandRecord | None:
        assert (user_id, client_request_id) == (
            "user-1",
            "decision-request-0001",
        )
        self.trace.append("fast-replay")
        return None


class _ArtifactRepository:
    def __init__(self, trace: list[str]) -> None:
        self.trace = trace

    async def require_artifact(self, user_id: str, artifact_id: str) -> ArtifactRecord:
        del user_id, artifact_id
        self.trace.append("unlocked-artifact-read")
        return _artifact()

    async def lock_decision_scope(
        self, user_id: str, artifact_id: str
    ) -> ArtifactRecord:
        del user_id, artifact_id
        self.trace.append("scope-lock")
        return _artifact()


class _DecisionService:
    def __init__(self, trace: list[str]) -> None:
        self.trace = trace

    async def decide(self, *args: object, **kwargs: object) -> ArtifactDecisionResponse:
        del args, kwargs
        self.trace.append("decision")
        return ArtifactDecisionResponse(
            artifactId="artifact-1",
            decision="approve",
            savedCount=1,
        )


class _CommandRepository:
    def __init__(self, trace: list[str]) -> None:
        self.trace = trace

    async def get_by_idempotency_key(
        self, user_id: str, client_request_id: str
    ) -> WritingCommandRecord | None:
        del user_id, client_request_id
        self.trace.append("locked-replay")
        return None

    async def require_owned_task(self, user_id: str, task_id: str) -> TaskRecord:
        del user_id, task_id
        self.trace.append("task-read")
        return _task()

    async def create_artifact_decision(self, **kwargs: Any) -> WritingCommandRecord:
        self.trace.append("command-create")
        return WritingCommandRecord(
            id=kwargs["command_id"],
            task=_task(),
            kind="artifact_decision",
            payload=kwargs["payload"],
            status="pending",
            attempt_count=0,
            artifact_id=kwargs["artifact_id"],
            decision=kwargs["decision"],
            result=kwargs["result"],
        )


@pytest.mark.asyncio
async def test_artifact_decision_uses_advisory_and_scope_lock_before_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace: list[str] = []

    async def acquire_lock(*args: object, **kwargs: object) -> None:
        del args, kwargs
        trace.append("advisory-lock")

    async def resolve(*args: object, **kwargs: object) -> None:
        del args, kwargs
        trace.append("resolver")

    monkeypatch.setattr(
        decision_module,
        "acquire_idempotency_lock",
        acquire_lock,
        raising=False,
    )
    dependencies = ReviewDecisionDependencies(
        repository=_ArtifactRepository(trace),  # type: ignore[arg-type]
        service=_DecisionService(trace),  # type: ignore[arg-type]
        commands=_CommandRepository(trace),  # type: ignore[arg-type]
    )
    orchestrator = ReviewDecisionOrchestrator(
        _OuterFactory(),  # type: ignore[arg-type]
        command_lookup=_Lookup(trace),
        idempotency_resolver=resolve,
        dependencies_builder=lambda _factory: dependencies,
        transactional_factory_builder=lambda _connection: object(),
    )

    await orchestrator.decide(
        "user-1",
        "artifact-1",
        ReviewArtifactDecisionRequest(
            clientRequestId="decision-request-0001",
            expectedRevision=1,
            decision="approve",
        ),
    )

    assert trace == [
        "advisory-lock",
        "resolver",
        "scope-lock",
        "resolver",
        "task-read",
        "decision",
        "command-create",
    ]


class _Rows:
    def __init__(self, row: tuple[object, ...] | None) -> None:
        self.row = row

    def one_or_none(self) -> tuple[object, ...] | None:
        return self.row


class _DecisionScopeSession:
    def __init__(self, trace: list[str], artifact: ReviewArtifact) -> None:
        self.trace = trace
        self.artifact = artifact
        self.scalar_values = iter(
            ["command-current", "command-current", None, object()]
        )
        self.scalar_labels = iter(
            [
                "current-command-read",
                "current-command-lock",
                "active-command-lock",
                "source-command-lock",
            ]
        )

    async def __aenter__(self) -> _DecisionScopeSession:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback

    def begin(self) -> _Transaction:
        return _Transaction()

    async def execute(self, statement: object) -> _Rows:
        del statement
        self.trace.append("identity-read")
        return _Rows(("novel-1", "chapter-1", "task-1"))

    async def scalar(self, statement: object) -> object | None:
        del statement
        value = next(self.scalar_values)
        self.trace.append(next(self.scalar_labels))
        return value


@pytest.mark.asyncio
async def test_decision_scope_uses_unified_rows_before_current_and_source_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace: list[str] = []
    task = WritingTask(
        id="task-1",
        novelId="novel-1",
        chapterId="chapter-1",
        phase="awaiting_user_review",
    )
    artifact = ReviewArtifact(
        id="artifact-1",
        novelId="novel-1",
        chapterId="chapter-1",
        taskId="task-1",
        kind="chapter_draft",
        status="awaiting_user",
        payloadJson=(
            '{"kind":"chapter_draft",'
            '"_inkforgeControl":{"sourceCommandId":"command-source"}}'
        ),
        revision=1,
        createdAt=datetime(2026, 8, 6),
        updatedAt=datetime(2026, 8, 6),
    )
    current = WritingRunCommand(
        id="command-current",
        taskId="task-1",
        artifactId=None,
        status="succeeded",
    )
    session = _DecisionScopeSession(trace, artifact)

    async def unified_lock(*args: object, **kwargs: object) -> LockedWritingRows:
        del args
        request = kwargs["request"]
        assert request == WritingLockRequest(
            novel_id="novel-1",
            chapter_ids=("chapter-1",),
            task_id="task-1",
            artifact_id="artifact-1",
            command_id="command-current",
        )
        trace.append("unified-lock")
        return LockedWritingRows(
            novel=Novel(id="novel-1", userId="user-1"),
            chapters=(Chapter(id="chapter-1", novelId="novel-1"),),
            task=task,
            artifact=artifact,
            command=current,
        )

    monkeypatch.setattr(review_repository_module, "lock_writing_rows", unified_lock)
    repository = ReviewRepository(lambda: session)  # type: ignore[arg-type]

    locked = await repository.lock_decision_scope("user-1", "artifact-1")

    assert locked.id == "artifact-1"
    assert trace == [
        "identity-read",
        "current-command-read",
        "unified-lock",
        "current-command-lock",
        "active-command-lock",
        "source-command-lock",
    ]


class _ScalarLockSession:
    def __init__(self, values: list[object]) -> None:
        self.values = iter(values)

    async def scalar(self, statement: object) -> object | None:
        del statement
        return next(self.values)


@pytest.mark.asyncio
async def test_current_command_lock_uses_task_binding_not_artifact_binding() -> None:
    command = WritingRunCommand(
        id="command-current",
        taskId="task-1",
        artifactId=None,
    )

    locked = await lock_writing_rows(  # type: ignore[arg-type]
        _ScalarLockSession(
            [
                Novel(id="novel-1", userId="user-1"),
                Chapter(id="chapter-1", novelId="novel-1"),
                WritingTask(
                    id="task-1",
                    novelId="novel-1",
                    chapterId="chapter-1",
                ),
                ReviewArtifact(
                    id="artifact-1",
                    novelId="novel-1",
                    chapterId="chapter-1",
                    taskId="task-1",
                ),
                command,
            ]
        ),
        user_id="user-1",
        request=WritingLockRequest(
            novel_id="novel-1",
            chapter_ids=("chapter-1",),
            task_id="task-1",
            artifact_id="artifact-1",
            command_id="command-current",
        ),
    )

    assert locked.command is command


@dataclass(slots=True)
class _RaceState:
    task_phase: str = "awaiting_user_review"
    active_command: str | None = None
    artifact_status: str = "awaiting_user"
    chapter_version: int = 1
    approved_plan_exists: bool = False


class _LockTable:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    async def transaction(
        self,
        keys: tuple[str, ...],
        action: Callable[[], str],
        *,
        acquired: asyncio.Event | None = None,
        release: asyncio.Event | None = None,
    ) -> str:
        held_locks: list[asyncio.Lock] = []
        try:
            for key in keys:
                lock = self._locks.setdefault(key, asyncio.Lock())
                await lock.acquire()
                held_locks.append(lock)
                await asyncio.sleep(0)
            if acquired is not None:
                acquired.set()
            if release is not None:
                await release.wait()
            return action()
        finally:
            for lock in reversed(held_locks):
                lock.release()


async def _run_ordered_race(
    first_factory: Callable[[asyncio.Event, asyncio.Event], Awaitable[str]],
    second_factory: Callable[[], Awaitable[str]],
) -> tuple[str, str]:
    acquired = asyncio.Event()
    release = asyncio.Event()
    first = asyncio.create_task(first_factory(acquired, release))
    await asyncio.wait_for(acquired.wait(), timeout=1)
    second = asyncio.create_task(second_factory())
    await asyncio.sleep(0)
    release.set()
    first_result, second_result = await asyncio.wait_for(
        asyncio.gather(first, second),
        timeout=1,
    )
    return first_result, second_result


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["approve", "revise", "discard"])
async def test_decision_and_new_start_have_deterministic_results_in_both_orders(
    decision: str,
) -> None:
    keys = {
        "decision": ("novel", "chapter", "task", "artifact", "command"),
        "start": ("novel", "chapter"),
    }

    async def one_order(decision_first: bool) -> tuple[str, str]:
        state = _RaceState()
        locks = _LockTable()

        def decide() -> str:
            if state.artifact_status != "awaiting_user":
                return "artifact_conflict"
            state.artifact_status = {
                "approve": "applied",
                "revise": "draft",
                "discard": "discarded",
            }[decision]
            state.active_command = "artifact_decision"
            return "decision_accepted"

        def start() -> str:
            if state.task_phase not in {"completed", "error"}:
                return "WRITING_TARGET_BUSY"
            state.active_command = "start"
            return "start_accepted"

        def run_decision() -> Awaitable[str]:
            return locks.transaction(keys["decision"], decide)

        def run_start() -> Awaitable[str]:
            return locks.transaction(keys["start"], start)
        if decision_first:
            return await _run_ordered_race(
                lambda acquired, release: locks.transaction(
                    keys["decision"],
                    decide,
                    acquired=acquired,
                    release=release,
                ),
                run_start,
            )
        first, second = await _run_ordered_race(
            lambda acquired, release: locks.transaction(
                keys["start"],
                start,
                acquired=acquired,
                release=release,
            ),
            run_decision,
        )
        return second, first

    assert await one_order(True) == (
        "decision_accepted",
        "WRITING_TARGET_BUSY",
    )
    assert await one_order(False) == (
        "decision_accepted",
        "WRITING_TARGET_BUSY",
    )


@pytest.mark.asyncio
async def test_start_vs_start_serializes_without_deadlock() -> None:
    for _ in range(20):
        active = False
        locks = _LockTable()

        def start() -> str:
            nonlocal active
            if active:
                return "WRITING_TARGET_BUSY"
            active = True
            return "start_accepted"

        def run_first(
            acquired: asyncio.Event,
            release: asyncio.Event,
            lock_table: _LockTable = locks,
        ) -> Awaitable[str]:
            return lock_table.transaction(
                ("novel", "chapter"),
                start,
                acquired=acquired,
                release=release,
            )

        def run_second(lock_table: _LockTable = locks) -> Awaitable[str]:
            return lock_table.transaction(("novel", "chapter"), start)

        first, second = await _run_ordered_race(run_first, run_second)

        assert (first, second) == ("start_accepted", "WRITING_TARGET_BUSY")


@pytest.mark.asyncio
async def test_cancel_vs_complete_is_determined_by_task_command_lock_order() -> None:
    async def one_order(cancel_first: bool) -> tuple[str, str]:
        state = {"task": "active", "command": "processing"}
        locks = _LockTable()

        def cancel() -> str:
            if state["task"] == "completed":
                return "cancel_noop"
            if state["command"] == "processing":
                state["command"] = "failed"
                return "cancel_effective"
            return "cancel_noop"

        def complete() -> str:
            if state["command"] != "processing":
                return "WRITING_JOB_MISMATCH"
            state["command"] = "succeeded"
            state["task"] = "completed"
            return "complete_applied"

        cancel_keys = ("novel", "chapter", "task", "command")
        complete_keys = ("task", "command")
        if cancel_first:
            return await _run_ordered_race(
                lambda acquired, release: locks.transaction(
                    cancel_keys,
                    cancel,
                    acquired=acquired,
                    release=release,
                ),
                lambda: locks.transaction(complete_keys, complete),
            )
        complete_result, cancel_result = await _run_ordered_race(
            lambda acquired, release: locks.transaction(
                complete_keys,
                complete,
                acquired=acquired,
                release=release,
            ),
            lambda: locks.transaction(cancel_keys, cancel),
        )
        return cancel_result, complete_result

    assert await one_order(True) == (
        "cancel_effective",
        "WRITING_JOB_MISMATCH",
    )
    assert await one_order(False) == ("cancel_noop", "complete_applied")


@pytest.mark.asyncio
async def test_cancel_vs_decision_preserves_artifact_precondition() -> None:
    async def one_order(cancel_first: bool) -> tuple[str, str]:
        state = {"artifact": "awaiting_user", "decision": "none"}
        locks = _LockTable()
        keys = ("novel", "chapter", "task", "artifact", "command")

        def cancel() -> str:
            if state["artifact"] == "awaiting_user":
                return "ARTIFACT_DECISION_REQUIRED"
            state["decision"] = "cancelled"
            return "cancel_effective"

        def decide() -> str:
            if state["artifact"] != "awaiting_user":
                return "ARTIFACT_NOT_AWAITING_USER"
            state["artifact"] = "applied"
            state["decision"] = "pending"
            return "decision_accepted"

        if cancel_first:
            return await _run_ordered_race(
                lambda acquired, release: locks.transaction(
                    keys,
                    cancel,
                    acquired=acquired,
                    release=release,
                ),
                lambda: locks.transaction(keys, decide),
            )
        decision_result, cancel_result = await _run_ordered_race(
            lambda acquired, release: locks.transaction(
                keys,
                decide,
                acquired=acquired,
                release=release,
            ),
            lambda: locks.transaction(keys, cancel),
        )
        return cancel_result, decision_result

    assert await one_order(True) == (
        "ARTIFACT_DECISION_REQUIRED",
        "decision_accepted",
    )
    assert await one_order(False) == ("cancel_effective", "decision_accepted")


@pytest.mark.asyncio
async def test_approve_vs_chapter_save_uses_source_and_version_preconditions() -> None:
    async def one_order(approve_first: bool) -> tuple[str, str]:
        state = {"chapter_version": 1, "artifact": "awaiting_user"}
        locks = _LockTable()

        def approve() -> str:
            if state["chapter_version"] != 1:
                return "ARTIFACT_SOURCE_VERSION_CONFLICT"
            state["artifact"] = "applied"
            state["chapter_version"] += 1
            return "approve_applied"

        def save() -> str:
            if state["chapter_version"] != 1:
                return "CHAPTER_VERSION_CONFLICT"
            state["chapter_version"] += 1
            return "chapter_saved"

        approve_keys = ("novel", "chapter", "task", "artifact", "command")
        if approve_first:
            return await _run_ordered_race(
                lambda acquired, release: locks.transaction(
                    approve_keys,
                    approve,
                    acquired=acquired,
                    release=release,
                ),
                lambda: locks.transaction(("chapter",), save),
            )
        save_result, approve_result = await _run_ordered_race(
            lambda acquired, release: locks.transaction(
                ("chapter",),
                save,
                acquired=acquired,
                release=release,
            ),
            lambda: locks.transaction(approve_keys, approve),
        )
        return approve_result, save_result

    assert await one_order(True) == ("approve_applied", "CHAPTER_VERSION_CONFLICT")
    assert await one_order(False) == (
        "ARTIFACT_SOURCE_VERSION_CONFLICT",
        "chapter_saved",
    )


@pytest.mark.asyncio
async def test_absent_beat_plan_create_vs_approve_is_serialized() -> None:
    async def one_order(approve_first: bool) -> tuple[str, str]:
        state = {"approved_plan": False}
        locks = _LockTable()

        def approve() -> str:
            if state["approved_plan"]:
                return "ARTIFACT_SOURCE_VERSION_CONFLICT"
            state["approved_plan"] = True
            return "approve_applied"

        def create() -> str:
            if state["approved_plan"]:
                return "BEAT_PLAN_ALREADY_EXISTS"
            state["approved_plan"] = True
            return "beat_plan_created"

        approve_keys = ("novel", "chapter", "task", "artifact", "command")
        create_keys = ("novel", "chapter")
        if approve_first:
            return await _run_ordered_race(
                lambda acquired, release: locks.transaction(
                    approve_keys,
                    approve,
                    acquired=acquired,
                    release=release,
                ),
                lambda: locks.transaction(create_keys, create),
            )
        create_result, approve_result = await _run_ordered_race(
            lambda acquired, release: locks.transaction(
                create_keys,
                create,
                acquired=acquired,
                release=release,
            ),
            lambda: locks.transaction(approve_keys, approve),
        )
        return approve_result, create_result

    assert await one_order(True) == ("approve_applied", "BEAT_PLAN_ALREADY_EXISTS")
    assert await one_order(False) == (
        "ARTIFACT_SOURCE_VERSION_CONFLICT",
        "beat_plan_created",
    )


@pytest.mark.asyncio
async def test_cancelled_postgres_outcome_closes_stream_without_redis_boundary() -> None:
    outcome = WritingRunOutcome(
        state="cancelled",
        code="WRITING_RUN_CANCELLED_BY_USER",
        taskTerminal=True,
        streamShouldClose=True,
        reconciliationRequired=False,
        currentCommand=None,
        result=WritingRunOutcomeResult(kind="none", ready=False),
        observedAt=datetime.now(UTC),
    )

    async def outcome_provider() -> WritingRunOutcome:
        return outcome

    stream = stream_task_events(
        InMemoryWritingEventStore(),
        "task-1",
        last_event_id=None,
        outcome_provider=outcome_provider,
        poll_interval_seconds=0,
        heartbeat_interval_seconds=1,
    )

    first = await asyncio.wait_for(anext(stream), timeout=1)
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(anext(stream), timeout=1)

    assert "event: run_outcome" in first
    assert '"state":"cancelled"' in first
    assert "completed" not in first
