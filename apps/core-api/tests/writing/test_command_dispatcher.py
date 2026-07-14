from __future__ import annotations

from dataclasses import replace

import pytest
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
        self.failed_attempts: list[tuple[str, str]] = []

    async def claim_due(self, limit: int) -> list[WritingCommandRecord]:
        return self.commands[:limit]

    async def mark_submitted(self, command_id: str) -> WritingCommandRecord:
        self.submitted_ids.append(command_id)
        return replace(self.commands[0], status="submitted")

    async def record_dispatch_failure(
        self, command_id: str, error_code: str
    ) -> WritingCommandRecord:
        self.failed_attempts.append((command_id, error_code))
        return replace(self.commands[0], attempt_count=1)


class RecordingSubmitter:
    def __init__(self) -> None:
        self.job_ids: list[str] = []

    async def submit_command(self, value: WritingCommandRecord) -> None:
        self.job_ids.append(value.id)


@pytest.mark.asyncio
async def test_dispatch_failure_keeps_command_pending() -> None:
    repository = Repository([command()])

    class FailingSubmitter:
        async def submit_command(self, value: WritingCommandRecord) -> None:
            del value
            raise RuntimeError("Redis 暂时不可用，且这段详情不能持久化")

    dispatcher = WritingRunCommandDispatcher(repository, FailingSubmitter())

    assert await dispatcher.run_once() == 0
    assert repository.submitted_ids == []
    assert repository.failed_attempts == [("command-1", "RuntimeError")]


@pytest.mark.asyncio
async def test_dispatch_uses_command_id_as_stable_job_id() -> None:
    repository = Repository([command("command-stable")])
    submitter = RecordingSubmitter()

    completed = await WritingRunCommandDispatcher(repository, submitter).run_once()

    assert completed == 1
    assert submitter.job_ids == ["command-stable"]
    assert repository.submitted_ids == ["command-stable"]


@pytest.mark.asyncio
async def test_dispatch_continues_after_one_command_fails() -> None:
    repository = Repository([command("bad"), command("good")])

    class PartialSubmitter(RecordingSubmitter):
        async def submit_command(self, value: WritingCommandRecord) -> None:
            if value.id == "bad":
                raise TimeoutError
            await super().submit_command(value)

    submitter = PartialSubmitter()
    dispatcher = WritingRunCommandDispatcher(repository, submitter)

    assert await dispatcher.run_once() == 1
    assert submitter.job_ids == ["good"]
    assert repository.failed_attempts == [("bad", "TimeoutError")]
