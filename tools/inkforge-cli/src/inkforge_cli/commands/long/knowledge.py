from __future__ import annotations

from ...json_types import JsonObject
from ...runtime import CliRuntime
from .read import (
    public_id,
    query_fields,
    request_json,
    require_string,
    validate_read_payload,
)


def _novel_workspace_get(
    runtime: CliRuntime,
    payload: JsonObject,
    resource: str,
) -> JsonObject:
    validate_read_payload(payload, required=("novelId",))
    novel_id = require_string(payload, "novelId")
    return request_json(
        runtime,
        f"/api/v1/novels/{public_id(novel_id)}/workspace/{resource}",
    )


def get_planning(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    return _novel_workspace_get(runtime, payload, "planning")


def get_lore(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    return _novel_workspace_get(runtime, payload, "lore")


def get_resources(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    return _novel_workspace_get(runtime, payload, "resources")


def list_outline_nodes(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    validate_read_payload(payload, required=("novelId",))
    novel_id = require_string(payload, "novelId")
    return request_json(
        runtime,
        f"/api/v1/novels/{public_id(novel_id)}/outline-nodes",
    )


def list_foreshadowings(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    validate_read_payload(payload, required=("novelId",))
    novel_id = require_string(payload, "novelId")
    return request_json(
        runtime,
        f"/api/v1/novels/{public_id(novel_id)}/foreshadowings",
    )


def list_artifacts(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    filters = (
        "novelId",
        "chapterId",
        "taskId",
        "status",
        "kind",
        "cursor",
        "limit",
    )
    validate_read_payload(
        payload,
        required=("novelId",),
        optional=filters[1:],
    )
    return request_json(
        runtime,
        "/api/v1/review-artifacts",
        params=query_fields(payload, filters),
    )


def get_artifact(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    validate_read_payload(payload, required=("artifactId",))
    artifact_id = require_string(payload, "artifactId")
    return request_json(
        runtime,
        f"/api/v1/review-artifacts/{public_id(artifact_id)}",
    )


def get_quality_check(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    validate_read_payload(payload, required=("checkId",))
    check_id = require_string(payload, "checkId")
    return request_json(
        runtime,
        f"/api/v1/quality-checks/{public_id(check_id)}",
    )
