import pytest
from inkforge_agents.graph.snapshots import (
    deserialize_snapshot,
    serialize_snapshot,
    to_typescript_snapshot,
)
from inkforge_agents.graph.state import create_initial_state


def test_snapshot_uses_versioned_envelope_and_round_trips_stable_state() -> None:
    state = create_initial_state(
        task_id="task-1",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id="chapter-1",
        user_message="续写",
    )
    state["operationStage"] = "等待用户决策"
    serialized = serialize_snapshot(state)
    restored = deserialize_snapshot(serialized)

    assert serialized["version"] == 1
    assert restored["taskId"] == "task-1"
    assert restored["operationStage"] == "等待用户决策"

    rollback = to_typescript_snapshot(serialized)
    assert rollback["operationMode"] == "operation_graph"
    assert rollback["pendingUserResponse"] is False
    assert "runtime" not in rollback


def test_snapshot_accepts_core_flat_compatibility_state() -> None:
    state = create_initial_state(
        task_id="task-1",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id="chapter-1",
        user_message="继续修改",
    )
    state["phase"] = "waiting_user"
    state["activeArtifactId"] = "artifact-1"
    flat = {
        **to_typescript_snapshot(serialize_snapshot(state)),
        "operationMode": "operation_graph",
        "pendingUserResponse": True,
        "generatedContent": "",
        "pendingUpdates": None,
        "pendingAgentCall": None,
        "qualityCheckId": None,
        "artifactMode": "review_loop",
        "reviewerAgent": None,
        "reviewWorkerAgent": None,
        "reviserAgent": None,
        "pendingArtifactRevision": None,
    }

    restored = deserialize_snapshot(flat)

    assert restored["taskId"] == "task-1"
    assert flat["phase"] == "awaiting_user_review"
    assert restored["phase"] == "waiting_user"
    assert restored["activeArtifactId"] == "artifact-1"


@pytest.mark.parametrize(
    "forbidden",
    ["runtime", "callbacks", "novelData", "controlEvents", "streamCallbacks"],
)
def test_snapshot_rejects_runtime_only_fields(forbidden: str) -> None:
    state = create_initial_state(
        task_id="task-1",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id="chapter-1",
        user_message="续写",
    )
    state[forbidden] = {"unsafe": True}  # type: ignore[literal-required]

    with pytest.raises(ValueError, match="仅运行时字段"):
        serialize_snapshot(state)
