from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from inkforge_contracts.events import AgentEvent, RunFailureCallback
from inkforge_core.db.models import (
    Chapter,
    Novel,
    ReviewArtifact,
    User,
    WritingRunCommand,
    WritingTask,
)
from inkforge_core.writing.commands import WritingRunCommandRepository
from inkforge_core.writing.recovery import deserialize_graph_snapshot
from inkforge_core.writing.sse import InMemoryWritingEventStore
from inkforge_core.writing.tasks import WritingCallbackService, WritingTaskRepository
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TABLES = [
    User.__table__,
    Novel.__table__,
    Chapter.__table__,
    WritingTask.__table__,
    WritingRunCommand.__table__,
    ReviewArtifact.__table__,
]


@pytest_asyncio.fixture
async def session_factory(
    tmp_path: Path,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'short-story-failure.db').as_posix()}"
    )

    @event.listens_for(engine.sync_engine, "connect")
    def attach_public_schema(dbapi_connection: object, _record: object) -> None:
        dbapi_connection.execute("ATTACH DATABASE ':memory:' AS public")  # type: ignore[attr-defined]

    saved_defaults = [
        (column, column.server_default) for table in TABLES for column in table.columns
    ]
    try:
        for column, _default in saved_defaults:
            column.server_default = None
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda sync_connection: User.metadata.create_all(
                    sync_connection,
                    tables=TABLES,
                )
            )
            # SQLite 不识别模型上的 postgresql_where，测试库需显式还原生产环境的部分唯一索引。
            await connection.exec_driver_sql(
                'DROP INDEX public."WritingRunCommand_active_task_key"'
            )
            await connection.exec_driver_sql(
                'CREATE UNIQUE INDEX public."WritingRunCommand_active_task_key" '
                'ON "WritingRunCommand" ("taskId") '
                "WHERE \"status\" IN ('pending', 'submitted', 'processing')"
            )
    finally:
        for column, default in saved_defaults:
            column.server_default = default

    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def _seed_failure_target(
    factory: async_sessionmaker[AsyncSession],
    *,
    kind: str,
    status: str,
    short_medium: bool,
    command_artifact_id: str | None,
    snapshot_active_artifact_id: str | None = None,
    extra_artifact_ids: tuple[str, ...] = (),
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    profile = "short_medium" if short_medium else "long_serial"
    operation = (
        "develop_short_outline"
        if kind == "outline_draft"
        else "write_short_story"
    )
    source: dict[str, object] | None = None
    if short_medium and operation == "develop_short_outline":
        source = {
            "kind": "short_outline_inspiration",
            "originalInspiration": "一名守夜人发现黎明正在被偷走。",
        }
    elif short_medium:
        source = {
            "kind": "approved_short_outline",
            "outlineArtifactId": "outline-applied-1",
            "outlineRevision": 1,
            "outlineHash": "0" * 64,
        }
    snapshot: dict[str, object] = {
        "taskId": "task-1",
        "userId": "user-1",
        "novelId": "novel-1",
        "chapterId": "chapter-1",
        "targetWordCount": 6000,
        "conversationHistory": [],
        "currentOperation": {"kind": operation} if short_medium else None,
        "operationStage": "中短篇生成失败",
        "workflowKind": profile,
        "explicitOperation": operation if short_medium else None,
        "commandId": "command-1",
        "targetTotalWordCount": 6000 if short_medium else None,
        "commandSource": source,
        "phase": "error",
        "artifactStatus": "under_review",
        "errorMessage": "模型生成失败",
        "eventSequence": 0,
    }
    if snapshot_active_artifact_id is not None:
        snapshot["activeArtifactId"] = snapshot_active_artifact_id
    async with factory() as session:
        async with session.begin():
            session.add(
                User(
                    id="user-1",
                    username="owner",
                    passwordHash="hash",
                    creditBalanceMicros=0,
                )
            )
            session.add(Novel(id="novel-1", userId="user-1", name="测试小说"))
            session.add(
                Chapter(
                    id="chapter-1",
                    novelId="novel-1",
                    order=1,
                    status="drafting",
                    title="正文",
                    content="原正式正文",
                )
            )
            session.add(
                WritingTask(
                    id="task-1",
                    novelId="novel-1",
                    chapterId="chapter-1",
                    phase="error",
                    selectedAgents="写作",
                    targetWordCount=6000,
                    graphStateJson=json.dumps(snapshot, ensure_ascii=False),
                )
            )
            session.add(
                WritingRunCommand(
                    id="command-1",
                    taskId="task-1",
                    kind=(
                        "artifact_decision"
                        if command_artifact_id is not None
                        else "start"
                    ),
                    artifactId=command_artifact_id,
                    decision="revise" if command_artifact_id else None,
                    payloadJson=json.dumps(
                        {
                            "version": 1,
                            "resume": command_artifact_id is not None,
                            "chapterId": "chapter-1",
                            "writingSessionId": None,
                            "resumeInput": None,
                            "workflowKind": profile,
                            "operation": operation if short_medium else None,
                            "targetTotalWordCount": 6000 if short_medium else None,
                            "source": source,
                        }
                    ),
                    idempotencyKey="user-1:request-1",
                    status="processing",
                    attemptCount=0,
                    nextAttemptAt=now,
                )
            )
            session.add(
                ReviewArtifact(
                    id="artifact-1",
                    artifactKey="short-artifact-1",
                    novelId="novel-1",
                    chapterId="chapter-1",
                    taskId="task-1",
                    kind=kind,
                    status=status,
                    revision=4,
                    payloadJson=json.dumps(
                        {
                            "kind": kind,
                            "storyLengthProfile": profile,
                            "content": "上一完整版本",
                        },
                        ensure_ascii=False,
                    ),
                    createdByAgent="写作",
                )
            )
            for artifact_id in extra_artifact_ids:
                session.add(
                    ReviewArtifact(
                        id=artifact_id,
                        artifactKey=f"short-{artifact_id}",
                        novelId="novel-1",
                        chapterId="chapter-1",
                        taskId="task-1",
                        kind=kind,
                        status=status,
                        revision=4,
                        payloadJson=json.dumps(
                            {
                                "kind": kind,
                                "storyLengthProfile": profile,
                                "content": f"候选版本 {artifact_id}",
                            },
                            ensure_ascii=False,
                        ),
                        createdByAgent="写作",
                    )
                )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "status", "command_artifact_id"),
    [
        ("outline_draft", "draft", "artifact-1"),
        ("outline_draft", "awaiting_user", "artifact-1"),
        ("chapter_draft", "under_review", None),
        ("chapter_draft", "awaiting_user", None),
    ],
)
async def test_current_short_story_failure_callback_restores_artifact_for_user_decision(
    session_factory: async_sessionmaker[AsyncSession],
    kind: str,
    status: str,
    command_artifact_id: str | None,
) -> None:
    await _seed_failure_target(
        session_factory,
        kind=kind,
        status=status,
        short_medium=True,
        command_artifact_id=command_artifact_id,
        snapshot_active_artifact_id=(
            "artifact-1" if command_artifact_id is not None else None
        ),
    )
    repository = WritingTaskRepository(session_factory)
    events = InMemoryWritingEventStore()
    service = WritingCallbackService(repository, events)

    await service.fail(
        RunFailureCallback(
            protocolVersion="1.1",
            eventId="event-1",
            jobId="command-1",
            runId="task-1",
            taskId="task-1",
            sequence=1,
            code="AGENT_RUN_FAILED",
            message="中短篇生成失败",
            recoverable=True,
            occurredAt=datetime.now(UTC),
        )
    )
    replay = await repository.fail_with_command(
        "task-1", "command-1", "AGENT_RUN_FAILED", 2
    )

    async with session_factory() as session:
        artifact = await session.get(ReviewArtifact, "artifact-1")
        task = await session.get(WritingTask, "task-1")
        command = await session.get(WritingRunCommand, "command-1")

    assert replay.accepted is True
    assert replay.already_applied is True
    assert [event.event for event in await events.replay("task-1", None)] == ["error"]
    assert artifact is not None
    assert artifact.status == "awaiting_user"
    assert artifact.revision == 4
    assert json.loads(artifact.payloadJson)["content"] == "上一完整版本"
    assert task is not None and task.phase == "awaiting_user_review"
    assert task.graphStateJson is not None
    snapshot = json.loads(task.graphStateJson)
    assert snapshot["phase"] == "awaiting_user_review"
    assert snapshot["activeArtifactId"] == "artifact-1"
    assert snapshot["artifactStatus"] == "awaiting_user"
    assert snapshot.get("errorMessage") is None
    assert snapshot["currentOperation"]["kind"] == (
        "develop_short_outline" if kind == "outline_draft" else "write_short_story"
    )
    assert snapshot["currentOperation"]["requiresUserApproval"] is True
    recovered = deserialize_graph_snapshot(
        task.graphStateJson,
        expected_task_id="task-1",
        expected_user_id="user-1",
        expected_novel_id="novel-1",
        expected_chapter_id="chapter-1",
    )
    assert recovered.active_artifact_id == "artifact-1"
    assert command is not None and command.status == "failed"

    decision = await WritingRunCommandRepository(
        session_factory
    ).create_artifact_decision(
        command_id="command-approve",
        user_id="user-1",
        task_id="task-1",
        artifact_id="artifact-1",
        decision="approve",
        client_request_id="request-approve",
        payload={
            "decisionRequest": {
                "artifactId": "artifact-1",
                "decision": "approve",
                "expectedRevision": 4,
                "userMessage": None,
            }
        },
        result={"artifactId": "artifact-1", "decision": "approve"},
    )
    assert decision.status == "pending"
    assert decision.artifact_id == "artifact-1"


@pytest.mark.asyncio
async def test_recovered_snapshot_advances_past_failure_event_sequence(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_failure_target(
        session_factory,
        kind="chapter_draft",
        status="under_review",
        short_medium=True,
        command_artifact_id=None,
    )
    repository = WritingTaskRepository(session_factory)
    events = InMemoryWritingEventStore()
    service = WritingCallbackService(repository, events)

    await service.fail(
        RunFailureCallback(
            protocolVersion="1.1",
            eventId="event-failure",
            jobId="command-1",
            runId="task-1",
            taskId="task-1",
            sequence=1,
            code="AGENT_RUN_FAILED",
            message="中短篇生成失败",
            recoverable=True,
            occurredAt=datetime.now(UTC),
        )
    )
    async with session_factory() as session:
        task = await session.get(WritingTask, "task-1")
    assert task is not None and task.graphStateJson is not None
    recovered_sequence = json.loads(task.graphStateJson)["eventSequence"]
    assert recovered_sequence == 1

    decision = await WritingRunCommandRepository(
        session_factory
    ).create_artifact_decision(
        command_id="command-approve-after-recovery",
        user_id="user-1",
        task_id="task-1",
        artifact_id="artifact-1",
        decision="approve",
        client_request_id="request-approve-after-recovery",
        payload={
            "decisionRequest": {
                "artifactId": "artifact-1",
                "decision": "approve",
                "expectedRevision": 4,
                "userMessage": None,
            }
        },
        result={"artifactId": "artifact-1", "decision": "approve"},
    )
    await service.accept_event(
        AgentEvent(
            protocolVersion="1.1",
            eventId="event-resumed-start",
            jobId=decision.id,
            runId="task-1",
            taskId="task-1",
            sequence=recovered_sequence + 1,
            event="agent_start",
            data={"agentId": "写作", "agentName": "作家"},
            occurredAt=datetime.now(UTC),
        )
    )

    replay = await events.replay("task-1", None)
    assert [(item.event, item.sequence) for item in replay] == [
        ("error", 1),
        ("agent_start", 2),
    ]


@pytest.mark.asyncio
async def test_applied_short_story_artifact_is_not_recovered(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_failure_target(
        session_factory,
        kind="chapter_draft",
        status="applied",
        short_medium=True,
        command_artifact_id=None,
    )
    repository = WritingTaskRepository(session_factory)

    await repository.fail_with_command("task-1", "command-1", "AGENT_RUN_FAILED", 1)

    async with session_factory() as session:
        artifact = await session.get(ReviewArtifact, "artifact-1")
        task = await session.get(WritingTask, "task-1")

    assert artifact is not None and artifact.status == "applied"
    assert task is not None and task.phase == "error"


@pytest.mark.asyncio
async def test_long_serial_failure_does_not_change_artifact_status(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_failure_target(
        session_factory,
        kind="chapter_draft",
        status="under_review",
        short_medium=False,
        command_artifact_id="artifact-1",
    )
    repository = WritingTaskRepository(session_factory)

    await repository.fail_with_command("task-1", "command-1", "AGENT_RUN_FAILED", 1)

    async with session_factory() as session:
        artifact = await session.get(ReviewArtifact, "artifact-1")

    assert artifact is not None
    assert artifact.status == "under_review"


@pytest.mark.asyncio
async def test_start_failure_prefers_snapshot_active_artifact_id(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_failure_target(
        session_factory,
        kind="chapter_draft",
        status="under_review",
        short_medium=True,
        command_artifact_id=None,
        snapshot_active_artifact_id="artifact-2",
        extra_artifact_ids=("artifact-2",),
    )
    repository = WritingTaskRepository(session_factory)

    await repository.fail_with_command("task-1", "command-1", "AGENT_RUN_FAILED", 1)

    async with session_factory() as session:
        first = await session.get(ReviewArtifact, "artifact-1")
        second = await session.get(ReviewArtifact, "artifact-2")
        task = await session.get(WritingTask, "task-1")

    assert first is not None and first.status == "under_review"
    assert second is not None and second.status == "awaiting_user"
    assert task is not None and task.phase == "awaiting_user_review"
    assert json.loads(task.graphStateJson or "{}")["activeArtifactId"] == "artifact-2"


@pytest.mark.asyncio
async def test_start_failure_with_ambiguous_candidates_fails_closed(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_failure_target(
        session_factory,
        kind="chapter_draft",
        status="under_review",
        short_medium=True,
        command_artifact_id=None,
        snapshot_active_artifact_id=None,
        extra_artifact_ids=("artifact-2",),
    )
    repository = WritingTaskRepository(session_factory)

    await repository.fail_with_command("task-1", "command-1", "AGENT_RUN_FAILED", 1)

    async with session_factory() as session:
        artifacts = list(
            await session.scalars(
                select(ReviewArtifact).where(ReviewArtifact.taskId == "task-1")
            )
        )
        task = await session.get(WritingTask, "task-1")

    assert sorted(artifact.status for artifact in artifacts) == [
        "under_review",
        "under_review",
    ]
    assert task is not None and task.phase == "error"


@pytest.mark.asyncio
async def test_artifact_decision_failure_keeps_exact_artifact_binding(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_failure_target(
        session_factory,
        kind="outline_draft",
        status="draft",
        short_medium=True,
        command_artifact_id="artifact-1",
        snapshot_active_artifact_id="artifact-2",
        extra_artifact_ids=("artifact-2",),
    )
    repository = WritingTaskRepository(session_factory)

    await repository.fail_with_command("task-1", "command-1", "AGENT_RUN_FAILED", 1)

    async with session_factory() as session:
        first = await session.get(ReviewArtifact, "artifact-1")
        second = await session.get(ReviewArtifact, "artifact-2")
        task = await session.get(WritingTask, "task-1")

    assert first is not None and first.status == "awaiting_user"
    assert second is not None and second.status == "draft"
    assert task is not None
    assert json.loads(task.graphStateJson or "{}")["activeArtifactId"] == "artifact-1"
