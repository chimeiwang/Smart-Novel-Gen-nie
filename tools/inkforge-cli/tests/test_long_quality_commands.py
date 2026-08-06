from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

import pytest
from inkforge_cli.api import CoreApiError
from inkforge_cli.commands.long import quality
from inkforge_cli.json_types import JsonObject
from inkforge_cli.runtime import CliInputError, CliRuntime


@dataclass
class RecordingApi:
    responses: list[Any] = field(default_factory=list)
    calls: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        self.calls.append((method, path, kwargs))
        response = self.responses.pop(0) if self.responses else {}
        if isinstance(response, Exception):
            raise response
        return response


@dataclass
class RuntimeStub:
    api: RecordingApi

    def require_api(self) -> RecordingApi:
        return self.api


def runtime(api: RecordingApi) -> CliRuntime:
    return cast(CliRuntime, RuntimeStub(api))


def payload(**values: object) -> JsonObject:
    return cast(JsonObject, values)


@pytest.mark.parametrize(
    ("handler", "method", "suffix", "input_values", "expected_body"),
    [
        (
            quality.run,
            "POST",
            "/run",
            {
                "clientRequestId": "quality-request-0001",
                "taskId": "task-1",
                "message": "重点检查人物动机",
            },
            {
                "clientRequestId": "quality-request-0001",
                "taskId": "task-1",
                "message": "重点检查人物动机",
            },
        ),
        (
            quality.skip,
            "PATCH",
            "",
            {"expectedUpdatedAt": "2026-08-06T00:00:00Z"},
            {
                "status": "skipped",
                "resetResult": False,
                "expectedUpdatedAt": "2026-08-06T00:00:00Z",
            },
        ),
        (
            quality.reset,
            "PATCH",
            "",
            {"expectedUpdatedAt": "2026-08-06T00:00:00Z"},
            {
                "status": "pending",
                "resetResult": True,
                "expectedUpdatedAt": "2026-08-06T00:00:00Z",
            },
        ),
    ],
)
def test_quality_commands_send_only_the_fixed_public_contract(
    handler: Any,
    method: str,
    suffix: str,
    input_values: dict[str, object],
    expected_body: dict[str, object],
) -> None:
    api = RecordingApi(responses=[{"id": "check /?#"}])

    result = handler(
        runtime(api),
        payload(checkId="check /?#", profile="production", **input_values),
    )

    assert result["id"] == "check /?#"
    assert api.calls == [
        (
            method,
            f"/api/v1/quality-checks/check%20%2F%3F%23{suffix}",
            {"json": expected_body},
        )
    ]
    assert "profile" not in api.calls[0][2]["json"]


@pytest.mark.parametrize(
    "client_request_id",
    [None, "short", "x" * 129],
)
def test_quality_run_requires_a_caller_owned_stable_request_id(
    client_request_id: object,
) -> None:
    api = RecordingApi()
    values: dict[str, object] = {"checkId": "check-1"}
    if client_request_id is not None:
        values["clientRequestId"] = client_request_id

    with pytest.raises(CliInputError) as caught:
        quality.run(runtime(api), payload(**values))

    assert caught.value.code == "CLIENT_REQUEST_ID_REQUIRED"
    assert api.calls == []


@pytest.mark.parametrize("handler", [quality.skip, quality.reset])
@pytest.mark.parametrize("expected_updated_at", [None, "", 123, True])
def test_quality_cas_commands_require_expected_updated_at(
    handler: Any,
    expected_updated_at: object,
) -> None:
    api = RecordingApi()
    values: dict[str, object] = {"checkId": "check-1"}
    if expected_updated_at is not None:
        values["expectedUpdatedAt"] = expected_updated_at

    with pytest.raises(CliInputError) as caught:
        handler(runtime(api), payload(**values))

    assert caught.value.code in {"FIELD_REQUIRED", "INVALID_EXPECTED_UPDATED_AT"}
    assert api.calls == []


def test_quality_command_preserves_core_error_details_and_request_id() -> None:
    conflict = CoreApiError(
        409,
        code="QUALITY_CHECK_STALE_WRITE",
        message="质量检查状态已经变化",
        details={
            "expectedUpdatedAt": "2026-08-06T00:00:00Z",
            "currentUpdatedAt": "2026-08-06T00:00:01Z",
        },
        request_id="request-server-2",
    )
    api = RecordingApi(responses=[conflict])

    with pytest.raises(CoreApiError) as caught:
        quality.skip(
            runtime(api),
            payload(
                checkId="check-1",
                expectedUpdatedAt="2026-08-06T00:00:00Z",
            ),
        )

    assert caught.value is conflict
    assert caught.value.details == {
        "expectedUpdatedAt": "2026-08-06T00:00:00Z",
        "currentUpdatedAt": "2026-08-06T00:00:01Z",
    }
    assert caught.value.request_id == "request-server-2"
