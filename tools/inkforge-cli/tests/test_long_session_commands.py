from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from typing import Any

import pytest
from inkforge_cli.api import CoreTransportError
from inkforge_cli.cli import run
from inkforge_cli.config import MemoryConfigStore, ProfileConfig
from inkforge_cli.credentials import MemoryCredentialStore
from inkforge_cli.registry import get_command_registry
from inkforge_cli.runtime import CliDependencies


@dataclass
class RecordingApi:
    calls: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)
    fail: bool = False
    response: dict[str, Any] = field(
        default_factory=lambda: {
            "id": "session-1",
            "novelId": "novel-1",
            "chapterId": "chapter-1",
            "title": "验收会话",
            "phase": "idle",
            "messages": [],
        }
    )

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        self.calls.append((method, path, kwargs))
        if self.fail:
            raise CoreTransportError()
        return self.response


def _invoke(
    payload: dict[str, Any],
    api: RecordingApi,
    *,
    authenticated: bool = True,
) -> tuple[int, dict[str, Any]]:
    config = MemoryConfigStore()
    credentials = MemoryCredentialStore()
    if authenticated:
        config.save("default", ProfileConfig(origin="http://127.0.0.1:8000", username="nie"))
        credentials.set("default", "http://127.0.0.1:8000", "test-session")
    output = io.StringIO()
    code = run(
        ["long.session.create"],
        stdin=io.StringIO(json.dumps(payload, ensure_ascii=False)),
        stdout=output,
        stderr=io.StringIO(),
        dependencies=CliDependencies(
            api_factory=lambda origin, token=None: api,
            config_store=config,
            credential_store=credentials,
            getpass_fn=lambda prompt: "unused",
            stdin_isatty=lambda: False,
        ),
    )
    return code, json.loads(output.getvalue())


@pytest.mark.parametrize("title_fields", [{}, {"title": None}, {"title": "  验收😀\r\n  "}])
def test_session_create_preserves_exact_body_and_original_response(
    title_fields: dict[str, Any],
) -> None:
    api = RecordingApi()
    body = {"novelId": "novel-1", "chapterId": "chapter-1", **title_fields}
    code, output = _invoke({"profile": "default", **body}, api)
    assert code == 0
    assert output == {"ok": True, "command": "long.session.create", "data": api.response}
    assert api.calls == [("POST", "/api/v1/writing/sessions", {"json": body})]


@pytest.mark.parametrize(
    "field_name,maximum", [("novelId", 256), ("chapterId", 256), ("title", 500)]
)
def test_session_create_counts_unicode_code_points_without_truncating(
    field_name: str, maximum: int
) -> None:
    api = RecordingApi()
    body = {"novelId": "n", "chapterId": "c", field_name: "😀" * maximum}
    assert _invoke(body, api)[0] == 0
    assert api.calls[0][2]["json"] == body
    api.calls.clear()
    body[field_name] += "😀"
    code, output = _invoke(body, api)
    assert code == 2
    assert output["error"]["code"] == "INVALID_FIELD"
    assert api.calls == []


@pytest.mark.parametrize("field_name", ["novelId", "chapterId", "title"])
@pytest.mark.parametrize("value", ["", True, 1, [], {}])
def test_session_create_rejects_invalid_fields_before_request(field_name: str, value: Any) -> None:
    api = RecordingApi()
    code, output = _invoke({"novelId": "n", "chapterId": "c", field_name: value}, api)
    assert code == 2
    assert output["error"]["code"] == "INVALID_FIELD"
    assert api.calls == []


@pytest.mark.parametrize("payload", [{}, {"novelId": "n"}, {"chapterId": "c"}])
def test_session_create_requires_both_ids(payload: dict[str, Any]) -> None:
    api = RecordingApi()
    code, output = _invoke(payload, api)
    assert code == 2
    assert output["error"]["code"] == "FIELD_REQUIRED"
    assert api.calls == []


@pytest.mark.parametrize(
    "field_name", ["clientRequestId", "origin", "token", "model", "outputFile", "unknown"]
)
def test_session_create_rejects_unknown_fields(field_name: str) -> None:
    api = RecordingApi()
    code, output = _invoke({"novelId": "n", "chapterId": "c", field_name: "value"}, api)
    assert code == 2
    assert output["error"]["code"] == "UNEXPECTED_FIELDS"
    assert api.calls == []


def test_session_create_requires_identity_and_never_retries_unknown_network_outcome() -> None:
    api = RecordingApi(fail=True)
    body = {"novelId": "n", "chapterId": "c"}
    code, output = _invoke(body, api, authenticated=False)
    assert code == 3
    assert output["error"]["code"] == "AUTH_REQUIRED"
    assert api.calls == []
    code, output = _invoke(body, api)
    assert code == 5
    assert output["error"]["code"] == "CORE_TRANSPORT_ERROR"
    assert len(api.calls) == 1


def test_session_create_metadata_does_not_invent_idempotency() -> None:
    spec = get_command_registry()["long.session.create"]
    assert spec.inputMode == "json"
    assert spec.outputMode == "json"
    assert spec.fileOutput.kind == "none"
    assert spec.mutation is True
    assert spec.requiresIdentity is True
    assert spec.requiresClientRequestId is False
