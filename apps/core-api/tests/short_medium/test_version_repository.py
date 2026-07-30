from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

import pytest
from inkforge_core.db.models import WritingRunCommand
from inkforge_core.short_medium.repository import (
    VersionRecord,
    WorkDocument,
    _SqlDocumentTransaction,
)
from inkforge_core.short_medium.schemas import DocumentVersionPayload

NOW = datetime(2026, 7, 30, tzinfo=UTC)


class RecordingSession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        return None


def candidate_version() -> VersionRecord:
    content = "候选正文"
    return VersionRecord(
        id="version-1",
        novel_id="novel-1",
        chapter_id="chapter-1",
        artifact_key="short-medium:manuscript:chapter-1",
        status="awaiting_user",
        summary=None,
        payload=DocumentVersionPayload(
            kind="chapter_draft",
            documentType="manuscript",
            versionNumber=1,
            baseVersionId=None,
            source="agent",
            content=content,
            contentHash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            sourceTaskId="task-1",
            sourceJobId="job-1",
            sourceOutlineVersionId="outline-1",
        ),
        diff=None,
        created_by_agent="写作",
        task_id="task-1",
        created_at=NOW,
        updated_at=NOW,
        applied_at=None,
    )


@pytest.mark.asyncio
async def test_save_adoption_replay_uses_existing_command_constraint_values() -> None:
    session = RecordingSession()
    transaction = _SqlDocumentTransaction(
        session,  # type: ignore[arg-type]
        WorkDocument(
            novel_id="novel-1",
            chapter_id="chapter-1",
            document_type="manuscript",
            artifact_key="short-medium:manuscript:chapter-1",
            content="",
            updated_at=NOW,
        ),
        object(),  # type: ignore[arg-type]
        [],
    )

    await transaction.save_adoption_replay(
        "short-medium:adopt:version-1:request-12345678",
        candidate_version(),
        '{"versionId":"version-1"}',
    )

    command = session.added[-1]
    assert isinstance(command, WritingRunCommand)
    assert command.taskId == "task-1"
    assert command.artifactId == "version-1"
    assert (
        command.idempotencyKey
        == "short-medium:adopt:version-1:request-12345678"
    )
    assert command.kind == "artifact_decision"
    assert command.decision == "approve"
    assert command.status == "succeeded"
    assert json.loads(command.payloadJson) == {"artifactId": "version-1"}
    assert command.resultJson is not None
    assert json.loads(command.resultJson) == {"versionId": "version-1"}
