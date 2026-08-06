from __future__ import annotations

import json

import pytest
from inkforge_core.db.models import WritingRunCommand
from inkforge_core.writing.cancellation import (
    WritingRunCancellationService,
    build_cancel_command_payload,
    build_cancelled_command_result,
)
from inkforge_core.writing.schemas import (
    CancelWritingRunRequest,
    CancelWritingRunResponse,
)


def test_cancel_command_payload_only_describes_the_cancelled_job() -> None:
    payload = build_cancel_command_payload(
        client_request_id="cancel-request-0001",
        task_id="task-1",
        cancelled_command_id="command-1",
        cancelled_job_id="job-1",
    )

    assert set(payload) == {"_inkforgeCommand", "job"}
    assert payload["_inkforgeCommand"]["commandKind"] == "cancel"
    assert payload["_inkforgeCommand"]["resourceIdentity"] == {"taskId": "task-1"}
    assert payload["_inkforgeCommand"]["normalizedBody"] == {}
    assert payload["job"] == {
        "cancelledCommandId": "command-1",
        "cancelledJobId": "job-1",
    }


def test_active_artifact_decision_cancel_preserves_accepted_response() -> None:
    accepted = {
        "artifactId": "artifact-1",
        "taskId": "task-1",
        "commandId": "decision-1",
        "decision": "approve",
        "status": "pending",
        "savedCount": 1,
        "deleted": False,
    }
    current = WritingRunCommand(
        id="decision-1",
        taskId="task-1",
        kind="artifact_decision",
        resultJson=json.dumps(
            {
                **accepted,
                "_inkforgeArtifactDecisionAcceptedResponse": accepted,
            }
        ),
    )

    result = build_cancelled_command_result(
        current,
        cancel_command_id="cancel-1",
        cancelled_job_id="decision-1",
    )

    assert result == {
        "code": "WRITING_RUN_CANCELLED_BY_USER",
        "cancelCommandId": "cancel-1",
        "cancelledJobId": "decision-1",
        "_inkforgeArtifactDecisionAcceptedResponse": accepted,
    }


def test_cancel_request_and_response_use_the_public_contract() -> None:
    request = CancelWritingRunRequest(clientRequestId="cancel-request-0001")
    response = CancelWritingRunResponse(
        taskId="task-1",
        commandId="cancel-1",
        commandStatus="succeeded",
        effective=False,
        alreadyTerminal=True,
        cancelledCommandId=None,
        cancelledJobId=None,
    )

    assert request.clientRequestId == "cancel-request-0001"
    assert response.model_dump() == {
        "taskId": "task-1",
        "commandId": "cancel-1",
        "commandStatus": "succeeded",
        "effective": False,
        "alreadyTerminal": True,
        "cancelledCommandId": None,
        "cancelledJobId": None,
    }


@pytest.mark.asyncio
async def test_cancel_service_only_kicks_pending_commands() -> None:
    class Repository:
        async def create_cancel(
            self, user_id: str, task_id: str, request: CancelWritingRunRequest
        ) -> CancelWritingRunResponse:
            assert (user_id, task_id, request.clientRequestId) == (
                "user-1",
                "task-1",
                "cancel-request-0001",
            )
            return CancelWritingRunResponse(
                taskId=task_id,
                commandId="cancel-1",
                commandStatus="pending",
                effective=True,
                alreadyTerminal=False,
                cancelledCommandId="command-1",
                cancelledJobId="command-1",
            )

    class Dispatcher:
        def __init__(self) -> None:
            self.calls = 0

        async def run_once(self) -> int:
            self.calls += 1
            return 1

    dispatcher = Dispatcher()
    service = WritingRunCancellationService(Repository(), dispatcher)  # type: ignore[arg-type]

    response = await service.cancel(
        "user-1",
        "task-1",
        CancelWritingRunRequest(clientRequestId="cancel-request-0001"),
    )

    assert response.commandId == "cancel-1"
    assert dispatcher.calls == 1
