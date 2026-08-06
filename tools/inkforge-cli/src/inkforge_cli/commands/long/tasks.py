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


def list_tasks(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    filters = (
        "novelId",
        "chapterId",
        "writingSessionId",
        "operation",
        "outcome",
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
        "/api/v1/writing/runs",
        params=query_fields(payload, filters),
    )


def get_task(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    validate_read_payload(payload, required=("taskId",))
    task_id = require_string(payload, "taskId")
    return request_json(
        runtime,
        f"/api/v1/writing/runs/{public_id(task_id)}",
    )
