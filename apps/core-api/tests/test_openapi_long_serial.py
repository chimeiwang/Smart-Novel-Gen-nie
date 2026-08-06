from __future__ import annotations

from inkforge_core.app import create_app


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
