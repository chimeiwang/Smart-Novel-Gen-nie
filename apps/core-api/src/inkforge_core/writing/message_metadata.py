from __future__ import annotations

import hashlib
import json


def workflow_message_metadata(
    task_id: str,
    *,
    event_type: str,
    content: str,
    agent_id: str | None = None,
    artifact_id: str | None = None,
    source_revision: int | None = None,
    intent: str | None = None,
) -> str:
    metadata: dict[str, str | int | None] = {
        "source": "workflow",
        "taskId": task_id,
        "eventType": event_type,
        "agentId": agent_id,
        "contentHash": hashlib.sha256(content.strip().encode()).hexdigest()[:24],
    }
    if artifact_id is not None:
        metadata["artifactId"] = artifact_id
    if source_revision is not None:
        metadata["sourceRevision"] = source_revision
    if intent is not None:
        metadata["intent"] = intent
    return json.dumps(
        metadata,
        ensure_ascii=False,
        sort_keys=True,
    )
