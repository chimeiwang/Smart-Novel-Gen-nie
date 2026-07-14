from __future__ import annotations

import json
from pathlib import Path

from inkforge_contracts import AgentEvent

EXAMPLES_PATH = Path(__file__).parents[1] / "contracts" / "writing-sse-events.json"
REQUIRED_EVENTS = {
    "artifact_awaiting_user_approval",
    "agent_status",
    "completed",
    "error",
    "update_builder_validation_failed",
    "review_artifact_requested",
}


def test_shared_writing_sse_examples_are_valid_agent_event_envelopes() -> None:
    examples = json.loads(EXAMPLES_PATH.read_text(encoding="utf-8"))

    assert {item["event"] for item in examples} == REQUIRED_EVENTS
    for item in examples:
        envelope = AgentEvent.model_validate(item["envelope"])
        assert envelope.event == item["event"]
        assert envelope.sequence > 0
        assert "type" not in envelope.data
