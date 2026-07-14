from __future__ import annotations

import hashlib
import json


def workflow_message_metadata(
    task_id: str,
    *,
    event_type: str,
    content: str,
    agent_id: str | None = None,
) -> str:
    return json.dumps(
        {
            "source": "workflow",
            "taskId": task_id,
            "eventType": event_type,
            "agentId": agent_id,
            "contentHash": hashlib.sha256(content.strip().encode()).hexdigest()[:24],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
