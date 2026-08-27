from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from inkforge_core.app import create_app

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = ROOT / "contracts" / "core"
PUBLIC_OPENAPI = CONTRACT_ROOT / "public-openapi-python-baseline.json"
PUBLIC_JAVA_OPENAPI = CONTRACT_ROOT / "public-openapi-java-baseline.json"
FULL_OPENAPI = CONTRACT_ROOT / "full-openapi-python-baseline.json"
JAVA_OPENAPI = CONTRACT_ROOT / "full-openapi-java-baseline.json"
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


def test_public_openapi_baseline_is_complete_and_current() -> None:
    baseline = _json(PUBLIC_OPENAPI)
    runtime = create_app(testing=True).openapi()

    assert len(baseline["paths"]) == 117
    assert _operation_count(baseline) == 150
    assert baseline == runtime


def test_full_openapi_baseline_covers_every_java_route() -> None:
    full = _json(FULL_OPENAPI)
    java = _json(JAVA_OPENAPI)

    assert len(full["paths"]) == 148
    assert _operation_count(full) == 181
    assert sum(path.startswith("/internal/v1/") for path in full["paths"]) == 30
    assert "/api/v1/video/provider-assets/{token}" in full["paths"]
    assert java["openapi"] == "3.0.3"
    assert java["paths"].keys() == full["paths"].keys()
    assert _operation_count(java) == _operation_count(full)
    source_schemas = set(full["components"]["schemas"])
    java_schemas = set(java["components"]["schemas"])
    # Java 专用投影只增加两个已在迁移 spec 中批准的流式响应占位；它们让
    # OpenAPI Generator 生成 StreamingResponseBody，不改变 Python 公共契约。
    assert java_schemas == source_schemas | {"BinaryFileStream", "WritingEventStream"}
    assert java["components"]["schemas"]["BinaryFileStream"]["format"] == "binary"
    assert java["components"]["schemas"]["WritingEventStream"]["format"] == "binary"
    assert {item["name"] for item in java["tags"]} == {
        "billing",
        "chapters",
        "debug",
        "identity",
        "lore",
        "novels",
        "operations",
        "outlines",
        "quality",
        "references",
        "reviews",
        "shortmedium",
        "styles",
        "video",
        "writing",
    }
    assert all(
        len(operation.get("tags", [])) == 1
        for path_item in java["paths"].values()
        for method, operation in path_item.items()
        if method in {"get", "post", "put", "patch", "delete"}
    )
    serialized_java = json.dumps(java, ensure_ascii=False)
    assert '"const"' not in serialized_java
    assert '"type": "null"' not in serialized_java
    upload_schema = java["components"]["schemas"][
        "Body_upload_reference_api_v1_styles__style_id__references_post"
    ]
    assert upload_schema["properties"]["file"]["format"] == "binary"


def test_public_java_openapi_is_safe_for_cli_generation() -> None:
    public = _json(PUBLIC_JAVA_OPENAPI)

    assert public["openapi"] == "3.0.3"
    assert public["x-inkforge-source-contract"] == (
        "public-openapi-python-baseline.json"
    )
    assert len(public["paths"]) == 117
    assert _operation_count(public) == 150
    assert all(not path.startswith("/internal/") for path in public["paths"])
    assert "/api/v1/video/provider-assets/{token}" not in public["paths"]


def test_hidden_and_public_route_inventory_is_complete() -> None:
    internal = _json(INTERNAL_ENDPOINTS)
    inventory = _json(ROUTE_INVENTORY)

    assert internal["schemaVersion"] == "core-internal-endpoints/1.0"
    assert len(internal["endpoints"]) == 30
    assert all(item["path"].startswith("/internal/v1/") for item in internal["endpoints"])

    assert inventory["schemaVersion"] == "core-route-inventory/1.0"
    assert len(inventory["routes"]) == 181
    assert sum(item["exposure"] == "public" for item in inventory["routes"]) == 150
    assert sum(item["exposure"] == "internal" for item in inventory["routes"]) == 30
    assert sum(item["exposure"] == "provider_media" for item in inventory["routes"]) == 1
    assert len({(item["method"], item["path"]) for item in inventory["routes"]}) == 181
    assert all(item["productModule"] and item["pythonTests"] for item in inventory["routes"])


def test_cross_language_fixtures_are_present_and_bounded() -> None:
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
    assert golden["claims"]["iat"] == 1_800_000_000
    assert golden["claims"]["exp"] == 1_800_000_120
    assert golden["expectedFailures"]["expired"] == "SERVICE_AUTHENTICATION_FAILED"
    assert golden["expectedFailures"]["wrongAudience"] == "SERVICE_AUTHENTICATION_FAILED"
    assert golden["expectedFailures"]["wrongBody"] == "SERVICE_REQUEST_BINDING_INVALID"
    assert golden["expectedFailures"]["replay"] == "SERVICE_TOKEN_REPLAYED"


def test_behavior_fixture_is_explicit_public_and_snapshot_queries_are_read_only() -> None:
    total_steps = 0
    scenarios: set[str] = set()
    for path in BEHAVIOR_FIXTURES:
        fixture = _json(path)
        steps = fixture["steps"]
        captured: set[str] = set()

        assert fixture["schemaVersion"] == "inkforge-core-behavior/1.0"
        assert fixture["scenario"] not in scenarios
        scenarios.add(fixture["scenario"])
        assert len({step["name"] for step in steps}) == len(steps)
        total_steps += len(steps)
        for step in steps:
            serialized_input = json.dumps(
                {"path": step["path"], "body": step.get("body")},
                ensure_ascii=False,
            )
            referenced = set(
                re.findall(r"\$\{([A-Za-z][A-Za-z0-9]*)}", serialized_input)
            )
            assert referenced <= captured
            assert step["method"] in {"GET", "POST", "PUT", "PATCH", "DELETE"}
            assert step["path"].startswith("/api/v1/")
            assert "/internal/" not in step["path"]
            assert isinstance(step["expectedStatus"], int)
            assert all(
                isinstance(pointer, str) and pointer.startswith("/")
                for pointer in step.get("normalizePointers", [])
            )
            for derived in step.get("derivedNormalizations", []):
                assert set(derived) == {
                    "algorithm",
                    "pointer",
                    "documentTypePointer",
                    "chapterIdPointer",
                    "baseVersionIdPointer",
                    "currentDraftHash",
                    "targetVersionIdPointer",
                    "diffPointer",
                }
                assert derived["algorithm"] == "shortMediumConfirmationHash"
                assert all(
                    isinstance(derived[name], str)
                    and derived[name].startswith("/")
                    for name in (
                        "pointer",
                        "documentTypePointer",
                        "chapterIdPointer",
                        "baseVersionIdPointer",
                        "targetVersionIdPointer",
                        "diffPointer",
                    )
                )
                assert re.fullmatch(r"[0-9a-f]{64}", derived["currentDraftHash"])
            definitions = step.get("capture", {})
            assert all(
                re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", name)
                and isinstance(pointer, str)
                and pointer.startswith("/")
                for name, pointer in definitions.items()
            )
            captured.update(definitions)

        queries = fixture["snapshotQueries"]
        assert queries
        for query in queries:
            sql = query["sql"].strip()
            assert sql.upper().startswith("SELECT ")
            assert ";" not in sql
            assert not re.search(
                r"\b(?:INSERT|UPDATE|DELETE|ALTER|DROP|TRUNCATE|CREATE)\b",
                sql,
                flags=re.IGNORECASE,
            )
            assert query["expectedRows"] > 0

    assert total_steps == 17


def test_export_script_reports_no_drift() -> None:
    result = subprocess.run(  # noqa: S603 -- 只执行当前解释器与仓库内固定脚本
        [sys.executable, str(ROOT / "scripts" / "export_core_migration_baseline.py"), "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
