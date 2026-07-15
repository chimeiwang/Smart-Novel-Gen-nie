from __future__ import annotations

from dataclasses import replace
from datetime import datetime

import pytest
from inkforge_contracts.jobs import AgentJobStatus
from inkforge_core.writing.command_dispatcher import WritingRunCommandDispatcher
from inkforge_core.writing.commands import WritingCommandRecord
from inkforge_core.writing.records import TaskRecord


def command(command_id: str = "command-1") -> WritingCommandRecord:
    return WritingCommandRecord(
        id=command_id,
        task=TaskRecord(
            id="task-1",
            user_id="user-1",
            novel_id="novel-1",
            chapter_id="chapter-1",
            writing_session_id="session-1",
            phase="active",
            graph_state_json=None,
        ),
        kind="resume",
        payload={"resume": True, "chapterId": "chapter-1"},
        status="pending",
        attempt_count=0,
    )


class Repository:
    def __init__(self, commands: list[WritingCommandRecord]) -> None:
        self.commands = commands
        self.submitted_ids: list[str] = []
        self.terminal_ids: list[tuple[str, AgentJobStatus]] = []
        self.failed_attempts: list[tuple[str, str]] = []

    async def claim_due(
        self,
        limit: int,
        active_stale_before: datetime,
    ) -> list[WritingCommandRecord]:
        del active_stale_before
        return self.commands[:limit]

    async def mark_agent_active(self, command_id: str) -> WritingCommandRecord:
        self.submitted_ids.append(command_id)
        return replace(self.commands[0], status="submitted")

    async def settle_dispatch_terminal(
        self,
        command_id: str,
        agent_status: AgentJobStatus,
    ) -> WritingCommandRecord:
        self.terminal_ids.append((command_id, agent_status))
        return replace(self.commands[0], status="failed")

    async def record_dispatch_failure(
        self, command_id: str, error_code: str
    ) -> WritingCommandRecord:
        self.failed_attempts.append((command_id, error_code))
        return replace(self.commands[0], attempt_count=1)


class RecordingSubmitter:
    def __init__(
        self,
        statuses: dict[str, AgentJobStatus] | None = None,
    ) -> None:
        self.job_ids: list[str] = []
        self.statuses = statuses or {}

    async def submit_command(self, value: WritingCommandRecord) -> AgentJobStatus:
        self.job_ids.append(value.id)
        return self.statuses.get(value.id, "queued")


@pytest.mark.asyncio
async def test_dispatch_failure_keeps_command_pending() -> None:
    repository = Repository([command()])

    class FailingSubmitter:
        async def submit_command(self, value: WritingCommandRecord) -> AgentJobStatus:
            del value
            raise ConnectionError("Agent Service 暂时不可用")

    dispatcher = WritingRunCommandDispatcher(repository, FailingSubmitter())

    assert await dispatcher.run_once() == 0
    assert repository.submitted_ids == []
    assert repository.failed_attempts == [("command-1", "ConnectionError")]


@pytest.mark.asyncio
async def test_dispatch_records_then_propagates_deterministic_error() -> None:
    repository = Repository([command()])

    class InvalidSubmitter:
        async def submit_command(self, value: WritingCommandRecord) -> AgentJobStatus:
            del value
            raise TypeError("提交调用契约错误")

    dispatcher = WritingRunCommandDispatcher(repository, InvalidSubmitter())

    with pytest.raises(TypeError, match="提交调用契约错误"):
        await dispatcher.run_once()

    assert repository.failed_attempts == [("command-1", "TypeError")]


@pytest.mark.asyncio
async def test_dispatch_uses_command_id_as_stable_job_id() -> None:
    repository = Repository([command("command-stable")])
    submitter = RecordingSubmitter()

    completed = await WritingRunCommandDispatcher(repository, submitter).run_once()

    assert completed == 1
    assert submitter.job_ids == ["command-stable"]
    assert repository.submitted_ids == ["command-stable"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["completed", "failed", "cancelled"])
async def test_dispatch_converges_existing_terminal_job(status: AgentJobStatus) -> None:
    repository = Repository([command("command-terminal")])
    submitter = RecordingSubmitter({"command-terminal": status})

    completed = await WritingRunCommandDispatcher(repository, submitter).run_once()

    assert completed == 1
    assert repository.submitted_ids == []
    assert repository.terminal_ids == [("command-terminal", status)]


@pytest.mark.asyncio
async def test_dispatch_continues_after_one_command_fails() -> None:
    repository = Repository([command("bad"), command("good")])

    class PartialSubmitter(RecordingSubmitter):
        async def submit_command(self, value: WritingCommandRecord) -> AgentJobStatus:
            if value.id == "bad":
                raise TimeoutError
            return await super().submit_command(value)

    submitter = PartialSubmitter()
    dispatcher = WritingRunCommandDispatcher(repository, submitter)

    assert await dispatcher.run_once() == 1
    assert submitter.job_ids == ["good"]
    assert repository.failed_attempts == [("bad", "TimeoutError")]
