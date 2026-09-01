from __future__ import annotations

from datetime import UTC, datetime

import pytest
from inkforge_contracts import calculate_resolved_model_fingerprint
from inkforge_core.app import create_app
from inkforge_core.writing.schemas import WritingRunV2Response
from pydantic import ValidationError

ERROR_STATUS_CODES = (
    "400",
    "401",
    "403",
    "404",
    "409",
    "422",
    "429",
    "500",
    "503",
    "default",
)

MODEL_SHA = "a" * 64


def _v2_model_profile() -> dict[str, object]:
    return {
        "profile": "writer.chapter_selection.v1",
        "version": 1,
        "reasoningMode": "bounded",
        "deploymentProfileKey": "deployment.writer.chapter_selection.v1",
        "promptProfile": {
            "name": "prompt.writer.chapter_selection.v1",
            "version": 1,
            "sha256": MODEL_SHA,
        },
    }


def _v2_resolved_model() -> dict[str, object]:
    material = {
        "deploymentProfileKey": "deployment.writer.chapter_selection.v1",
        "provider": "fake",
        "model": "fake-writer",
        "transportProfile": "transport.fake.v1",
        "endpointProfile": "endpoint.local-fake.v1",
        "structuredOutputRoute": "responses_json_schema_v1",
        "capabilityVersion": "capability.fake.structured-output.v1",
        "reasoningMode": "bounded",
        "supportsRequestIdempotency": True,
    }
    return {
        **material,
        "deploymentFingerprint": calculate_resolved_model_fingerprint(
            deployment_profile_key="deployment.writer.chapter_selection.v1",
            provider="fake",
            model="fake-writer",
            transport_profile="transport.fake.v1",
            endpoint_profile="endpoint.local-fake.v1",
            structured_output_route="responses_json_schema_v1",
            capability_version="capability.fake.structured-output.v1",
            reasoning_mode="bounded",
            supports_request_idempotency=True,
        ),
    }


def _response_schema(operation: dict[str, object], status_code: str) -> object:
    responses = operation["responses"]
    assert isinstance(responses, dict)
    response = responses[status_code]
    assert isinstance(response, dict)
    return response["content"]["application/json"]["schema"]


def test_openapi_exposes_strict_long_serial_start_contract() -> None:
    document = create_app(testing=True).openapi()
    schemas = document["components"]["schemas"]
    request_schema = schemas["LongSerialStartWritingRunRequest"]

    assert request_schema["additionalProperties"] is False
    assert set(request_schema["required"]) >= {
        "clientRequestId",
        "workflow",
        "novelId",
        "chapterId",
        "operation",
        "target",
        "scope",
        "userInstruction",
    }
    assert request_schema["properties"]["workflow"]["const"] == "long_serial"
    metadata_schema = schemas["SelectionAttachmentMetadata"]
    assert metadata_schema["additionalProperties"] is False
    assert "selectedText" not in metadata_schema["properties"]
    assert request_schema["properties"]["selectionAttachmentMetadata"]["anyOf"]
    assert "selectedAgents" not in request_schema["properties"]
    body_schema = document["paths"]["/api/v1/writing/runs"]["post"][
        "requestBody"
    ]["content"]["application/json"]["schema"]
    assert {
        item["$ref"].rsplit("/", 1)[-1] for item in body_schema["anyOf"]
    } >= {
        "StartWritingRunRequest",
        "ShortMediumStartWritingRunRequest",
        "LongSerialStartWritingRunRequest",
    }


def test_openapi_exposes_strict_chapter_target_and_scope_contracts() -> None:
    schemas = create_app(testing=True).openapi()["components"]["schemas"]
    target_schema = schemas["ChapterTarget"]
    scope_schema = schemas["ChapterScope"]

    assert target_schema["additionalProperties"] is False
    assert set(target_schema["properties"]) == {"type", "id"}
    assert set(target_schema["required"]) == {"type", "id"}
    assert target_schema["properties"]["type"]["const"] == "chapter"
    assert target_schema["properties"]["id"]["minLength"] == 1

    assert scope_schema["additionalProperties"] is False
    assert set(scope_schema["properties"]) == {"kind", "chapterId"}
    assert set(scope_schema["required"]) == {"kind", "chapterId"}
    assert scope_schema["properties"]["kind"]["const"] == "chapter"
    assert scope_schema["properties"]["chapterId"]["minLength"] == 1


def test_openapi_resume_request_no_longer_accepts_artifact_decision() -> None:
    schemas = create_app(testing=True).openapi()["components"]["schemas"]
    request_schema = schemas["ResumeWritingRunRequest"]

    assert request_schema["additionalProperties"] is False
    assert set(request_schema["properties"]) == {
        "clientRequestId",
        "writingSessionId",
        "userMessage",
    }
    assert set(request_schema["required"]) == {"clientRequestId"}
    assert "artifactId" not in request_schema["properties"]
    assert "decision" not in request_schema["properties"]


def test_openapi_exposes_filtered_writing_run_list() -> None:
    document = create_app(testing=True).openapi()
    operation = document["paths"]["/api/v1/writing/runs"]["get"]
    parameters = {
        parameter["name"]: parameter for parameter in operation["parameters"]
    }

    assert parameters["novelId"]["required"] is True
    assert {
        "novelId",
        "chapterId",
        "writingSessionId",
        "operation",
        "outcome",
        "cursor",
        "limit",
    } <= set(parameters)
    assert parameters["limit"]["schema"]["default"] == 50
    assert parameters["limit"]["schema"]["maximum"] == 100


def test_openapi_exposes_run_list_status_checkpoint_and_outcome_contracts() -> None:
    document = create_app(testing=True).openapi()
    schemas = document["components"]["schemas"]
    paths = document["paths"]

    assert _response_schema(paths["/api/v1/writing/runs"]["get"], "200") == {
        "$ref": "#/components/schemas/WritingRunListResponse"
    }
    assert _response_schema(
        paths["/api/v1/writing/runs/{task_id}"]["get"], "200"
    ) == {"$ref": "#/components/schemas/WritingRunStatusPublicResponse"}

    list_schema = schemas["WritingRunListResponse"]
    assert list_schema["additionalProperties"] is False
    assert set(list_schema["properties"]) == {"items", "nextCursor"}
    assert set(list_schema["required"]) == {"items", "nextCursor"}
    assert list_schema["properties"]["items"]["items"] == {
        "$ref": "#/components/schemas/WritingRunPublicListItem"
    }

    status_properties = schemas["WritingRunStatusResponse"]["properties"]
    assert status_properties["checkpoint"]["anyOf"][0] == {
        "$ref": "#/components/schemas/WritingRunCheckpointResponse"
    }
    assert status_properties["outcome"] == {
        "$ref": "#/components/schemas/WritingRunOutcome"
    }
    assert {
        "target",
        "scope",
        "activeArtifactId",
        "recoverable",
        "reviewReport",
    } <= set(status_properties)

    checkpoint_schema = schemas["WritingRunCheckpointResponse"]
    checkpoint_fields = {
        "eventSequence",
        "phase",
        "operationStage",
        "operationStep",
    }
    assert checkpoint_schema["additionalProperties"] is False
    assert set(checkpoint_schema["properties"]) == checkpoint_fields
    assert set(checkpoint_schema["required"]) == checkpoint_fields

    outcome_schema = schemas["WritingRunOutcome"]
    assert outcome_schema["additionalProperties"] is False
    assert set(outcome_schema["required"]) == set(outcome_schema["properties"])
    assert outcome_schema["properties"]["state"]["enum"] == [
        "queued",
        "running",
        "waiting_user",
        "succeeded",
        "failed",
        "cancelled",
        "inconsistent",
    ]
    assert outcome_schema["properties"]["result"] == {
        "$ref": "#/components/schemas/WritingRunOutcomeResult"
    }


def test_openapi_run_responses_use_explicit_engine_discriminators() -> None:
    document = create_app(testing=True).openapi()
    schemas = document["components"]["schemas"]
    paths = document["paths"]

    expected_unions = {
        "WritingRunStartResponse": "WritingRunResponse",
        "WritingRunStatusPublicResponse": "WritingRunStatusResponse",
        "WritingRunPublicListItem": "WritingRunListItem",
        "CancelWritingRunPublicResponse": "CancelWritingRunResponse",
    }
    for union_name, v1_name in expected_unions.items():
        schema = schemas[union_name]
        assert schema["discriminator"] == {
            "propertyName": "engineVersion",
            "mapping": {
                "1": f"#/components/schemas/{v1_name}",
                "2": "#/components/schemas/WritingRunV2Response",
            },
        }
        assert schema["oneOf"] == [
            {"$ref": f"#/components/schemas/{v1_name}"},
            {"$ref": "#/components/schemas/WritingRunV2Response"},
        ]

    assert _response_schema(paths["/api/v1/writing/runs"]["post"], "202") == {
        "$ref": "#/components/schemas/WritingRunStartResponse"
    }
    assert _response_schema(
        paths["/api/v1/writing/runs/{task_id}/cancel"]["post"], "202"
    ) == {"$ref": "#/components/schemas/CancelWritingRunPublicResponse"}

    for v1_name in (
        "WritingRunResponse",
        "WritingRunStatusResponse",
        "WritingRunListItem",
        "CancelWritingRunResponse",
    ):
        v1 = schemas[v1_name]
        assert v1["properties"]["engineVersion"]["const"] == 1
        assert {"engineVersion", "runId", "taskId"} <= set(v1["required"])
        assert {"activeSteps", "currentStep", "modelProfile", "resolvedModel"}.isdisjoint(
            v1["properties"]
        )

    v2 = schemas["WritingRunV2Response"]
    v2_fields = {
        "engineVersion",
        "runId",
        "taskId",
        "workflow",
        "operation",
        "status",
        "chapterId",
        "activeSteps",
        "currentStep",
        "cancelRequestedAt",
        "lastEventSequence",
        "revision",
        "artifact",
        "error",
        "commandId",
        "commandStatus",
    }
    assert v2["additionalProperties"] is False
    assert set(v2["properties"]) == v2_fields
    assert set(v2["required"]) == {
        "engineVersion",
        "runId",
        "taskId",
        "workflow",
        "status",
        "chapterId",
        "activeSteps",
        "lastEventSequence",
        "revision",
        "commandId",
        "commandStatus",
    }
    assert v2["properties"]["engineVersion"]["const"] == 2
    assert v2["properties"]["commandId"]["enum"] == [None]
    assert v2["properties"]["commandStatus"]["enum"] == [None]
    assert schemas["WorkflowCurrentStepSnapshot"]["properties"]["status"]["enum"] == [
        "pending",
        "running",
        "completed",
        "failed",
        "skipped",
    ]
    assert {"modelProfile", "resolvedModel", "latestProgress"} <= set(
        schemas["WorkflowCurrentStepSnapshot"]["required"]
    )
    progress_snapshot = schemas["WorkflowStepProgressSnapshot"]
    assert progress_snapshot["additionalProperties"] is False
    assert set(progress_snapshot["required"]) == {
        "progressSequence",
        "phase",
        "elapsedSeconds",
        "waitingOnProvider",
        "usageStatus",
    }


def test_openapi_review_artifact_list_is_bounded_and_detail_is_revision_conditional() -> None:
    document = create_app(testing=True).openapi()
    schemas = document["components"]["schemas"]
    legacy_list_operation = document["paths"]["/api/v1/review-artifacts"]["get"]
    summary_list_operation = document["paths"][
        "/api/v1/review-artifact-summaries"
    ]["get"]
    detail_operation = document["paths"][
        "/api/v1/review-artifacts/{artifact_id}"
    ]["get"]

    assert _response_schema(legacy_list_operation, "200") == {
        "$ref": "#/components/schemas/ReviewArtifactListResponse"
    }
    assert schemas["ReviewArtifactListResponse"]["properties"]["items"]["items"] == {
        "$ref": "#/components/schemas/ReviewArtifactResponse"
    }
    assert _response_schema(summary_list_operation, "200") == {
        "$ref": "#/components/schemas/ReviewArtifactSummaryListResponse"
    }
    assert schemas["ReviewArtifactSummaryListResponse"]["properties"]["items"][
        "items"
    ] == {
        "$ref": "#/components/schemas/ReviewArtifactSummaryResponse"
    }
    summary_fields = set(schemas["ReviewArtifactSummaryResponse"]["properties"])
    assert {
        "engineVersion",
        "id",
        "workflowRunId",
        "revision",
        "actionable",
        "updatedAt",
    } <= summary_fields
    assert {"payload", "diff", "evaluations"}.isdisjoint(summary_fields)
    assert "engineVersion" in schemas["ReviewArtifactResponse"]["required"]

    parameters = {
        (item["in"], item["name"]): item for item in detail_operation["parameters"]
    }
    revision_schema = parameters[("query", "revision")]["schema"]
    assert any(item.get("minimum") == 1 for item in revision_schema["anyOf"])
    assert ("header", "If-None-Match") in parameters
    assert "ETag" in detail_operation["responses"]["200"]["headers"]
    assert detail_operation["responses"]["304"]["description"]


def test_openapi_artifact_decision_is_an_engine_discriminated_union() -> None:
    document = create_app(testing=True).openapi()
    schemas = document["components"]["schemas"]
    operation = document["paths"][
        "/api/v1/review-artifacts/{artifact_id}/decision"
    ]["post"]

    assert _response_schema(operation, "202") == {
        "$ref": "#/components/schemas/ArtifactDecisionPublicResponse"
    }
    public_response = schemas["ArtifactDecisionPublicResponse"]
    assert public_response == {
        "oneOf": [
            {"$ref": "#/components/schemas/ArtifactDecisionAcceptedResponse"},
            {"$ref": "#/components/schemas/WritingRunV2Response"},
        ],
        "discriminator": {
            "propertyName": "engineVersion",
            "mapping": {
                "1": "#/components/schemas/ArtifactDecisionAcceptedResponse",
                "2": "#/components/schemas/WritingRunV2Response",
            },
        },
    }
    assert schemas["ArtifactDecisionAcceptedResponse"]["properties"][
        "engineVersion"
    ] == {
        "const": 1,
        "default": 1,
        "title": "Engineversion",
        "type": "integer",
    }
    decision_request = schemas["ReviewArtifactDecisionRequest"]
    assert decision_request["properties"]["engineVersion"]["default"] == 1
    assert (
        "expectedArtifactRevision"
        in decision_request["properties"]["expectedRevision"]["description"]
    )


def test_openapi_resume_is_explicitly_v1_only() -> None:
    document = create_app(testing=True).openapi()
    schemas = document["components"]["schemas"]
    operation = document["paths"]["/api/v1/writing/runs/{task_id}/resume"]["post"]

    assert _response_schema(operation, "202") == {
        "$ref": "#/components/schemas/ResumeWritingRunResponse"
    }
    response = schemas["ResumeWritingRunResponse"]
    assert response["properties"]["engineVersion"]["const"] == 1
    assert {"engineVersion", "runId", "taskId"} <= set(response["required"])
    assert "oneOf" not in response


def test_openapi_documents_v2_sse_control_and_durable_frames() -> None:
    operation = create_app(testing=True).openapi()["paths"][
        "/api/v1/writing/runs/{task_id}/events"
    ]["get"]
    response = operation["responses"]["200"]

    assert set(response["content"]) == {"text/event-stream"}
    assert response["content"]["text/event-stream"]["schema"] == {"type": "string"}
    assert response["x-inkforge-v2-sse"] == {
        "firstFrame": {
            "event": "run_snapshot",
            "schema": "inkforge_contracts.workflow_events.RunSnapshot",
        },
        "subsequentFrames": {
            "schema": "inkforge_contracts.workflow_events.WorkflowEventEnvelope",
        },
    }


def test_v2_public_projection_never_fakes_a_command() -> None:
    current_step = {
        "stepId": "step-1",
        "ordinal": 1,
        "purpose": "generation",
        "lane": "creative",
        "modelProfile": _v2_model_profile(),
        "resolvedModel": _v2_resolved_model(),
        "status": "running",
        "attemptCount": 1,
        "fencingToken": 2,
        "latestProgress": {
            "progressSequence": 3,
            "phase": "validating",
            "elapsedSeconds": 12,
            "waitingOnProvider": False,
            "usageStatus": "complete",
        },
        "errorCode": None,
    }
    payload = {
        "engineVersion": 2,
        "runId": "run-2",
        "taskId": "run-2",
        "workflow": "long_serial",
        "operation": "write_chapter",
        "status": "running",
        "chapterId": "chapter-1",
        "activeSteps": [current_step],
        "currentStep": current_step,
        "cancelRequestedAt": datetime(2026, 9, 1, tzinfo=UTC),
        "lastEventSequence": 7,
        "revision": 3,
        "artifact": None,
        "error": None,
        "commandId": None,
        "commandStatus": None,
    }

    response = WritingRunV2Response.model_validate(payload)
    assert response.currentStep is not None
    assert response.currentStep.status == "running"
    assert [step.stepId for step in response.activeSteps] == ["step-1"]
    assert response.currentStep.modelProfile is not None
    assert response.currentStep.modelProfile.profile == "writer.chapter_selection.v1"
    assert response.currentStep.resolvedModel is not None
    assert response.currentStep.resolvedModel.model == "fake-writer"
    assert response.currentStep.latestProgress is not None
    assert response.currentStep.latestProgress.progressSequence == 3
    assert response.commandId is response.commandStatus is None

    with pytest.raises(ValidationError, match="伪装"):
        WritingRunV2Response.model_validate({**payload, "commandId": "step-1"})
    with pytest.raises(ValidationError, match="兼容别名"):
        WritingRunV2Response.model_validate({**payload, "taskId": "task-other"})


def test_openapi_writing_run_paths_use_unified_error_response() -> None:
    paths = create_app(testing=True).openapi()["paths"]
    operations = (
        paths["/api/v1/writing/runs"]["post"],
        paths["/api/v1/writing/runs"]["get"],
        paths["/api/v1/writing/runs/{task_id}"]["get"],
        paths["/api/v1/writing/runs/{task_id}/resume"]["post"],
    )

    for operation in operations:
        for status_code in ERROR_STATUS_CODES:
            assert _response_schema(operation, status_code) == {
                "$ref": "#/components/schemas/ErrorResponse"
            }
        assert "HTTPValidationError" not in str(operation["responses"]["422"])


def test_openapi_exposes_creative_material_write_versions() -> None:
    document = create_app(testing=True).openapi()
    schemas = document["components"]["schemas"]

    expected_contracts = {
        "ContentRequest": (
            {"content", "expectedUpdatedAt"},
            {"content", "expectedUpdatedAt"},
        ),
        "WritingBibleRequest": ({
            "storyLengthProfile",
            "targetTotalWordCount",
            "genre",
            "targetReaders",
            "coreSellingPoint",
            "readerPromise",
            "appealModel",
            "taboo",
            "comparableTitles",
            "notes",
            "expectedUpdatedAt",
        }, {"expectedUpdatedAt"}),
        "PlotProgressRequest": ({
            "currentStage",
            "currentGoal",
            "currentConflict",
            "nextMilestone",
            "expectedUpdatedAt",
        }, {"currentStage", "expectedUpdatedAt"}),
        "ApplyStyleRequest": (
            {"styleId", "expectedStyleId"},
            {"styleId", "expectedStyleId"},
        ),
    }
    for schema_name, (fields, required) in expected_contracts.items():
        schema = schemas[schema_name]
        assert schema["additionalProperties"] is False
        assert set(schema["properties"]) == fields
        assert set(schema["required"]) == required

    assert "storyProgressUpdatedAt" in schemas["WorkspacePlanningResponse"][
        "properties"
    ]
    assert "storyProgressUpdatedAt" in schemas["WorkspacePlanningResponse"]["required"]

    for schema_name in (
        "CreateCharacterRequest",
        "CreateItemRequest",
        "CreateLocationRequest",
        "CreateFactionRequest",
        "CreateGlossaryRequest",
        "CreateExperienceRequest",
        "CreateRelationRequest",
        "CreateReferenceRequest",
    ):
        assert "clientRequestId" in schemas[schema_name]["required"]

    for schema_name in (
        "UpdateCharacterRequest",
        "UpdateItemRequest",
        "UpdateLocationRequest",
        "UpdateFactionRequest",
        "UpdateGlossaryRequest",
        "UpdateExperienceRequest",
        "UpdateRelationRequest",
        "UpdateReferenceRequest",
        "DeleteEntityRequest",
        "DeleteReferenceRequest",
    ):
        assert "expectedUpdatedAt" in schemas[schema_name]["required"]


def test_public_openapi_does_not_leak_internal_reference_index_contracts() -> None:
    document = create_app(testing=True).openapi()
    serialized = str(document)

    assert "/internal/v1/" not in serialized
    for internal_schema in (
        "CompleteReferenceIndexRequest",
        "FailReferenceIndexRequest",
        "ReferenceIndexContextRequest",
        "ReferenceIndexContextResponse",
    ):
        assert internal_schema not in document["components"]["schemas"]
