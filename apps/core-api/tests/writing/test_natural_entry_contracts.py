from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from inkforge_core.app import create_app
from inkforge_core.auth.dependencies import get_current_user
from inkforge_core.writing.router import get_writing_task_service
from inkforge_core.writing.schemas import (
    ClarifyWritingRunRequest,
    NaturalStartWritingRunRequest,
    WritingRunStartRequest,
)
from inkforge_core.writing.tasks import WritingTaskService
from pydantic import TypeAdapter, ValidationError


def natural():
    return {
        "inputMode": "natural", "workflow": "long_serial",
        "clientRequestId": "natural-request-0001", "novelId": "novel-1",
        "chapterId": "chapter-1", "writingSessionId": "session-1",
        "userInstruction": "  先解释，再由我决定。\r\n  ",
    }


def clarification():
    return {
        "clientRequestId": "clarify-request-0001", "expectedRevision": 3,
        "decisionStepId": "decision-1", "userMessage": "  只需要问答。\r\n  ",
    }


def test_natural_public_branch_preserves_complete_text_and_is_unambiguous():
    request = TypeAdapter(WritingRunStartRequest).validate_python(natural())
    assert isinstance(request, NaturalStartWritingRunRequest)
    assert request.targetWordCount == 4000
    assert request.userInstruction == natural()["userInstruction"]
    for field in ("operation", "target", "scope", "selectionTarget", "selectedAgents"):
        with pytest.raises(ValidationError):
            TypeAdapter(WritingRunStartRequest).validate_python(natural() | {field: None})
    for field in natural():
        with pytest.raises(ValidationError):
            NaturalStartWritingRunRequest.model_validate(
                {key: value for key, value in natural().items() if key != field}
            )


@pytest.mark.parametrize("value", ["", " \r\n\ufeff\u0085", None, 1])
def test_natural_and_clarification_reject_invalid_message(value):
    with pytest.raises(ValidationError):
        NaturalStartWritingRunRequest.model_validate(natural() | {"userInstruction": value})
    with pytest.raises(ValidationError):
        ClarifyWritingRunRequest.model_validate(clarification() | {"userMessage": value})


@pytest.mark.parametrize("value", [True, 0, "3", 3.5])
def test_clarification_revision_is_a_strict_positive_integer(value):
    with pytest.raises(ValidationError):
        ClarifyWritingRunRequest.model_validate(clarification() | {"expectedRevision": value})


def test_clarification_is_not_legacy_resume_or_artifact_decision():
    request = ClarifyWritingRunRequest.model_validate(clarification())
    assert request.userMessage == clarification()["userMessage"]
    for field in ("artifactId", "decision", "editedContent", "writingSessionId", "operation"):
        with pytest.raises(ValidationError):
            ClarifyWritingRunRequest.model_validate(clarification() | {field: None})


def test_natural_openapi_exports_exact_dtos_and_clarification_endpoint():
    api = create_app(testing=True).openapi()
    schemas = api["components"]["schemas"]
    assert schemas["NaturalStartWritingRunRequest"]["additionalProperties"] is False
    assert schemas["ClarifyWritingRunRequest"]["additionalProperties"] is False
    operation = api["paths"]["/api/v1/writing/runs/{task_id}/clarification"]["post"]
    assert operation["operationId"] == (
        "clarify_writing_run_api_v1_writing_runs__task_id__clarification_post"
    )
    assert operation["responses"]["202"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/WritingRunV2Response"
    }


def test_python_rollback_explicitly_rejects_natural_and_clarification_without_writes():
    class NoWrites:
        async def create_start_with_task(self, *args):
            raise AssertionError("Python 回滚实例不得创建自然 V2 或旧任务")

    app = create_app(testing=True)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="user-1")
    app.dependency_overrides[get_writing_task_service] = lambda: WritingTaskService(
        NoWrites(), None
    )
    client = TestClient(app)
    response = client.post("/api/v1/writing/runs", json=natural())
    assert response.status_code == 409
    assert response.json()["code"] == "WORKFLOW_NATURAL_ENTRY_UNSUPPORTED"
    response = client.post("/api/v1/writing/runs/run-1/clarification", json=clarification())
    assert response.status_code == 409
    assert response.json()["code"] == "WORKFLOW_CLARIFICATION_UNSUPPORTED"
