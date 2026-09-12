from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = ROOT / "contracts" / "core"
CANONICAL_OPENAPI = CONTRACT_ROOT / "openapi.json"
PUBLIC_OPENAPI = CONTRACT_ROOT / "public-openapi.json"
INTERNAL_ENDPOINTS = CONTRACT_ROOT / "internal-endpoints.json"
ROUTE_INVENTORY = CONTRACT_ROOT / "route-inventory.json"
BEHAVIOR_FIXTURES = (
    CONTRACT_ROOT / "behavior-fixtures" / "auth-novel-chapter.json",
    CONTRACT_ROOT / "behavior-fixtures" / "content-and-version.json",
)


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _operation_count(document: dict[str, Any]) -> int:
    methods = {"get", "post", "put", "patch", "delete"}
    return sum(
        method in methods
        for path_item in document["paths"].values()
        for method in path_item
    )


def test_canonical_openapi_is_java_owned_and_complete() -> None:
    document = _json(CANONICAL_OPENAPI)
    assert document["openapi"] == "3.0.3"
    assert document["x-inkforge-source-contract"] == "canonical-java"
    assert len(document["paths"]) == 166
    assert _operation_count(document) == 207
    assert all(
        "x-inkforge-exposure" in operation
        for path_item in document["paths"].values()
        for method, operation in path_item.items()
        if method in {"get", "post", "put", "patch", "delete"}
    )


def test_public_projection_excludes_internal_and_provider_media_schemas() -> None:
    canonical = _json(CANONICAL_OPENAPI)
    public = _json(PUBLIC_OPENAPI)
    assert public["openapi"] == "3.0.3"
    assert public["x-inkforge-source-contract"] == "openapi.json"
    assert len(public["paths"]) == 141
    assert _operation_count(public) == 182
    assert all(path.startswith("/api/v1/") for path in public["paths"])
    assert "/api/v1/video/provider-assets/{token}" not in public["paths"]
    assert not any(
        operation.get("x-inkforge-exposure") != "public"
        for path_item in public["paths"].values()
        for method, operation in path_item.items()
        if method in {"get", "post", "put", "patch", "delete"}
    )
    canonical_names = set(canonical["components"]["schemas"])
    assert set(public["components"]["schemas"]) <= canonical_names
    # 投影只保留公共路径的引用闭包，内部专用模型不能因完整契约被泄漏。
    assert len(public["components"]["schemas"]) < len(canonical["components"]["schemas"])


def test_numeric_engine_version_and_fixed_null_semantics_are_retained() -> None:
    document = _json(CANONICAL_OPENAPI)
    v2 = document["components"]["schemas"]["WritingRunV2Response"]
    assert v2["properties"]["engineVersion"]["x-inkforge-const"] == 2
    assert v2["properties"]["commandId"]["x-inkforge-fixed-null"] is True
    for schema_name in (
        "WritingRunStartResponse",
        "WritingRunStatusPublicResponse",
        "WritingRunPublicListItem",
        "CancelWritingRunPublicResponse",
    ):
        assert document["components"]["schemas"][schema_name]["discriminator"] == {
            "mapping": {
                "1": "#/components/schemas/"
                + (
                    "CancelWritingRunResponse"
                    if schema_name == "CancelWritingRunPublicResponse"
                    else "WritingRunListItem"
                    if schema_name == "WritingRunPublicListItem"
                    else "WritingRunStatusResponse"
                    if schema_name == "WritingRunStatusPublicResponse"
                    else "WritingRunResponse"
                ),
                "2": "#/components/schemas/WritingRunV2Response",
            },
            "propertyName": "engineVersion",
        }


def test_route_inventory_and_internal_projection_are_language_neutral() -> None:
    internal = _json(INTERNAL_ENDPOINTS)
    inventory = _json(ROUTE_INVENTORY)
    assert internal["schemaVersion"] == "core-internal-endpoints/2.0"
    assert len(internal["endpoints"]) == 24
    assert all(item["exposure"] == "internal" for item in internal["endpoints"])
    assert inventory["schemaVersion"] == "core-route-inventory/2.0"
    assert len(inventory["routes"]) == 207
    assert sum(item["exposure"] == "public" for item in inventory["routes"]) == 182
    assert sum(item["exposure"] == "internal" for item in inventory["routes"]) == 24
    assert sum(item["exposure"] == "provider_media" for item in inventory["routes"]) == 1
    assert len({(item["method"], item["path"]) for item in inventory["routes"]}) == 207
    forbidden = {"baselineCommit", "endpointModule", "sourceFile", "sourceLine", "pythonTests"}
    assert not forbidden.intersection(inventory)
    assert all(not forbidden.intersection(item) for item in inventory["routes"])
    assert all(item["operationId"] for item in inventory["routes"])


def test_clarification_route_keeps_strict_public_contract() -> None:
    path = "/api/v1/writing/runs/{task_id}/clarification"
    for document in (_json(PUBLIC_OPENAPI),):
        operation = document["paths"][path]["post"]
        assert operation["operationId"] == (
            "clarify_writing_run_api_v1_writing_runs__task_id__clarification_post"
        )
        assert operation["requestBody"]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ClarifyWritingRunRequest"
        }
        assert operation["responses"]["202"]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/WritingRunV2Response"
        }
        request = document["components"]["schemas"]["ClarifyWritingRunRequest"]
        assert request["additionalProperties"] is False
        assert set(request["required"]) == {
            "clientRequestId", "expectedRevision", "decisionStepId", "userMessage"
        }


def test_cross_language_fixtures_are_present_and_read_only() -> None:
    required = {
        CONTRACT_ROOT / "error-fixtures" / "api-error.json",
        CONTRACT_ROOT / "error-fixtures" / "validation-error.json",
        CONTRACT_ROOT / "error-fixtures" / "not-found.json",
        CONTRACT_ROOT / "sse-fixtures" / "event.txt",
        CONTRACT_ROOT / "sse-fixtures" / "heartbeat.txt",
        CONTRACT_ROOT / "sse-fixtures" / "run-outcome.txt",
        CONTRACT_ROOT / "service-auth-fixtures" / "golden-request.json",
        CONTRACT_ROOT / "service-auth-fixtures" / "public-jwks.json",
        CONTRACT_ROOT / "http-fixtures" / "pagination-cursor.json",
        CONTRACT_ROOT / "http-fixtures" / "request-id.json",
        CONTRACT_ROOT / "http-fixtures" / "session-cookie.json",
        CONTRACT_ROOT / "http-fixtures" / "file-download.json",
        CONTRACT_ROOT / "http-fixtures" / "trailing-slash-redirect.json",
    }
    assert all(path.is_file() and path.stat().st_size > 0 for path in required)
    golden = _json(CONTRACT_ROOT / "service-auth-fixtures" / "golden-request.json")
    assert golden["schemaVersion"] == "service-auth-golden-request/1.0"
    assert golden["expectedFailures"]["expired"] == "SERVICE_AUTHENTICATION_FAILED"
    assert golden["expectedFailures"]["wrongBody"] == "SERVICE_REQUEST_BINDING_INVALID"

    for path in BEHAVIOR_FIXTURES:
        fixture = _json(path)
        assert fixture["schemaVersion"] == "inkforge-core-behavior/1.0"
        assert fixture["steps"]
        assert all(step["path"].startswith("/api/v1/") for step in fixture["steps"])
        assert all("/internal/" not in step["path"] for step in fixture["steps"])
        assert all(
            query["sql"].strip().upper().startswith("SELECT ")
            and ";" not in query["sql"]
            and not re.search(
                r"\b(?:INSERT|UPDATE|DELETE|ALTER|DROP|TRUNCATE|CREATE)\b", query["sql"], re.I
            )
            for query in fixture["snapshotQueries"]
        )


def test_core_contract_generator_reports_no_drift() -> None:
    result = subprocess.run(  # noqa: S603 - 固定的仓库契约检查器
        ["node", str(ROOT / "scripts" / "build_core_openapi.mjs"), "--check"],  # noqa: S607
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
