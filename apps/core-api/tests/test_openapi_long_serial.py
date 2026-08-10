from __future__ import annotations

from inkforge_core.app import create_app

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
    ) == {"$ref": "#/components/schemas/WritingRunStatusResponse"}

    list_schema = schemas["WritingRunListResponse"]
    assert list_schema["additionalProperties"] is False
    assert set(list_schema["properties"]) == {"items", "nextCursor"}
    assert set(list_schema["required"]) == {"items", "nextCursor"}
    assert list_schema["properties"]["items"]["items"] == {
        "$ref": "#/components/schemas/WritingRunListItem"
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
