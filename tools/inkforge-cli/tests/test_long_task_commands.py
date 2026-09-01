from __future__ import annotations

import importlib
import io
import json
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any

import pytest
from inkforge_cli.api import CoreApiError
from inkforge_cli.cli import run
from inkforge_cli.config import MemoryConfigStore, ProfileConfig
from inkforge_cli.credentials import MemoryCredentialStore
from inkforge_cli.runtime import (
    CliDependencies,
    CliInputError,
    CliRuntime,
    command_exit_code,
)


@dataclass
class RecordingApi:
    error: CoreApiError | None = None
    calls: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, object]:
        self.calls.append((method, path, kwargs))
        if self.error is not None:
            raise self.error
        return {"accepted": True}


def _module() -> ModuleType:
    return importlib.import_module("inkforge_cli.commands.long.task_mutations")


def _spec(module: ModuleType, name: str) -> Any:
    return next(
        spec for spec in module.TASK_MUTATION_COMMAND_SPECS if spec.name == name
    )


def _runtime(spec: Any, api: RecordingApi) -> CliRuntime:
    return CliRuntime(
        spec=spec,
        argv=(),
        dependencies=CliDependencies(
            api_factory=lambda origin, token=None: api,
            config_store=MemoryConfigStore(),
            credential_store=MemoryCredentialStore(),
            getpass_fn=lambda prompt: "unused",
            stdin_isatty=lambda: False,
        ),
        api=api,
        profile="default",
        origin="http://127.0.0.1:8000",
    )


def _invoke_direct(
    payload: dict[str, Any],
    api: RecordingApi,
) -> tuple[int, dict[str, Any]]:
    profile = payload.get("profile", "default")
    assert isinstance(profile, str)
    config = MemoryConfigStore()
    config.save(
        profile,
        ProfileConfig(origin="http://127.0.0.1:8000", username="tester"),
    )
    credentials = MemoryCredentialStore()
    credentials.set(profile, "http://127.0.0.1:8000", "session-cookie")
    stdout = io.StringIO()
    exit_code = run(
        ["long.agent.start"],
        stdin=io.StringIO(json.dumps(payload, ensure_ascii=False)),
        stdout=stdout,
        stderr=io.StringIO(),
        dependencies=CliDependencies(
            api_factory=lambda origin, token=None: api,
            config_store=config,
            credential_store=credentials,
            getpass_fn=lambda prompt: "unused",
            stdin_isatty=lambda: False,
        ),
    )
    return exit_code, json.loads(stdout.getvalue())


def _start_payload(operation: str = "plan_chapter") -> dict[str, Any]:
    return {
        "clientRequestId": "long-start-20260806-0001",
        "novelId": "novel-1",
        "chapterId": "chapter-1",
        "writingSessionId": "session-1",
        "operation": operation,
        "target": {"type": "chapter", "id": "chapter-1"},
        "scope": {"kind": "chapter", "chapterId": "chapter-1"},
        "targetWordCount": 4000,
        "userInstruction": "处理当前章节",
        "profile": "production",
    }


def test_task_mutation_specs_require_identity_and_stable_request_ids() -> None:
    specs = _module().TASK_MUTATION_COMMAND_SPECS

    assert {spec.name for spec in specs} == {
        "long.agent.start",
        "long.task.resume",
        "long.task.cancel",
    }
    assert all(spec.mutation and spec.requiresIdentity for spec in specs)
    assert all(spec.requiresClientRequestId for spec in specs)
    assert all(spec.fileOutput.kind == "none" for spec in specs)


@pytest.mark.parametrize(
    "operation",
    ["answer_question", "plan_chapter", "write_chapter", "review_chapter"],
)
def test_agent_start_sends_exact_explicit_long_serial_contract(
    operation: str,
) -> None:
    module = _module()
    spec = _spec(module, "long.agent.start")
    api = RecordingApi()
    payload = _start_payload(operation)
    expected = {key: value for key, value in payload.items() if key != "profile"}
    expected["workflow"] = "long_serial"

    spec.handler(_runtime(spec, api), payload)

    assert api.calls == [
        ("POST", "/api/v1/writing/runs", {"json": expected})
    ]
    sent = api.calls[0][2]["json"]
    assert sent["target"] == payload["target"]
    assert sent["scope"] == payload["scope"]
    assert "selectedAgents" not in sent


def test_answer_question_preserves_exact_business_body_and_instruction() -> None:
    module = _module()
    spec = _spec(module, "long.agent.start")
    api = RecordingApi()
    payload = _start_payload("answer_question")
    payload.pop("targetWordCount")
    payload["clientRequestId"] = "long-answer-20260901-0001"
    payload["userInstruction"] = "\u2003这一章的主要冲突是什么？\n请保留原格式。\u3000"
    expected = {key: value for key, value in payload.items() if key != "profile"}
    expected["workflow"] = "long_serial"

    spec.handler(_runtime(spec, api), payload)

    assert api.calls == [
        ("POST", "/api/v1/writing/runs", {"json": expected})
    ]
    assert api.calls[0][2]["json"]["clientRequestId"] == payload["clientRequestId"]
    assert api.calls[0][2]["json"]["userInstruction"] == payload["userInstruction"]


@pytest.mark.parametrize("writing_session_id", [None, ""])
def test_answer_question_requires_non_empty_writing_session_before_business_api(
    writing_session_id: object,
) -> None:
    module = _module()
    spec = _spec(module, "long.agent.start")
    api = RecordingApi()
    payload = _start_payload("answer_question")
    if writing_session_id is None:
        payload.pop("writingSessionId")
    else:
        payload["writingSessionId"] = writing_session_id

    with pytest.raises(CliInputError) as caught:
        spec.handler(_runtime(spec, api), payload)

    assert caught.value.code == "WRITING_SESSION_REQUIRED"
    assert api.calls == []


def test_answer_question_rejects_explicit_null_session_before_business_api() -> None:
    module = _module()
    spec = _spec(module, "long.agent.start")
    api = RecordingApi()
    payload = _start_payload("answer_question")
    payload["writingSessionId"] = None

    with pytest.raises(CliInputError) as caught:
        spec.handler(_runtime(spec, api), payload)

    assert caught.value.code == "WRITING_SESSION_REQUIRED"
    assert api.calls == []


def test_answer_question_rejects_unicode_only_whitespace_before_business_api() -> None:
    module = _module()
    spec = _spec(module, "long.agent.start")
    api = RecordingApi()
    payload = _start_payload("answer_question")
    payload["userInstruction"] = "\u0085\u2003\u3000\n\t"

    with pytest.raises(CliInputError) as caught:
        spec.handler(_runtime(spec, api), payload)

    assert caught.value.code == "INVALID_USER_INSTRUCTION"
    assert api.calls == []


@pytest.mark.parametrize(
    ("field", "value", "expected_code"),
    [
        ("target", {"type": "chapter", "id": "chapter-2"}, "INVALID_TARGET"),
        ("scope", {"kind": "chapter", "chapterId": "chapter-2"}, "INVALID_SCOPE"),
        ("scope", {"kind": "novel"}, "INVALID_SCOPE"),
    ],
)
def test_answer_question_rejects_non_matching_chapter_target_or_scope_locally(
    field: str,
    value: object,
    expected_code: str,
) -> None:
    module = _module()
    spec = _spec(module, "long.agent.start")
    api = RecordingApi()
    payload = _start_payload("answer_question")
    payload[field] = value

    with pytest.raises(CliInputError) as caught:
        spec.handler(_runtime(spec, api), payload)

    assert caught.value.code == expected_code
    assert api.calls == []


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ({"writingSessionId": None}, "WRITING_SESSION_REQUIRED"),
        ({"scope": {"kind": "novel"}}, "INVALID_SCOPE"),
        ({"userInstruction": "\u0085\u2003\u3000"}, "INVALID_USER_INSTRUCTION"),
    ],
)
def test_direct_cli_rejects_invalid_answer_without_any_business_api_request(
    mutation: dict[str, Any],
    expected_code: str,
) -> None:
    api = RecordingApi()
    payload = _start_payload("answer_question")
    payload.update(mutation)

    exit_code, frame = _invoke_direct(payload, api)

    assert exit_code == 2
    assert frame["error"]["code"] == expected_code
    assert api.calls == []


def test_agent_start_sends_selection_identity_without_selected_text() -> None:
    module = _module()
    spec = _spec(module, "long.agent.start")
    api = RecordingApi()
    payload = _start_payload("rewrite_chapter_selection")
    payload["selectionTarget"] = {
        "resourceType": "chapter_content",
        "resourceId": "chapter-1",
        "baseUpdatedAt": "2026-08-10T00:00:00Z",
        "baseContentHash": "a" * 64,
        "selectionStart": 2,
        "selectionEnd": 8,
        "selectedTextHash": "b" * 64,
    }

    spec.handler(_runtime(spec, api), payload)

    sent = api.calls[0][2]["json"]
    assert sent["selectionTarget"] == payload["selectionTarget"]
    assert "selectedText" not in sent


def test_outline_selection_uses_outline_scope_and_identity() -> None:
    module = _module()
    spec = _spec(module, "long.agent.start")
    api = RecordingApi()
    payload = _start_payload("rewrite_outline_selection")
    payload["scope"] = {"kind": "novel"}
    payload["selectionTarget"] = {
        "resourceType": "outline_content",
        "resourceId": "outline-1",
        "baseUpdatedAt": "2026-08-10T00:00:00Z",
        "baseContentHash": "a" * 64,
        "selectionStart": 2,
        "selectionEnd": 8,
        "selectedTextHash": "b" * 64,
    }

    spec.handler(_runtime(spec, api), payload)

    sent = api.calls[0][2]["json"]
    assert sent["scope"] == {"kind": "novel"}
    assert sent["selectionTarget"]["resourceType"] == "outline_content"


@pytest.mark.parametrize("operation", ["rewrite_chapter_selection", "rewrite_outline_selection"])
def test_agent_start_requires_selection_target_for_selection_operations(operation: str) -> None:
    module = _module()
    spec = _spec(module, "long.agent.start")
    api = RecordingApi()
    payload = _start_payload(operation)

    with pytest.raises(CliInputError):
        spec.handler(_runtime(spec, api), payload)

    assert api.calls == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("operation", "rewrite_scene"),
        ("target", {"type": "chapter", "id": "chapter-2"}),
        ("scope", {"kind": "chapter", "chapterId": "chapter-2"}),
        ("selectedAgents", ["写作"]),
    ],
)
def test_agent_start_rejects_unsupported_or_inconsistent_inputs(
    field: str,
    value: object,
) -> None:
    module = _module()
    spec = _spec(module, "long.agent.start")
    api = RecordingApi()
    payload = _start_payload()
    payload[field] = value

    with pytest.raises(CliInputError):
        spec.handler(_runtime(spec, api), payload)

    assert api.calls == []


@pytest.mark.parametrize("request_id", ["x" * 15, "x" * 129])
@pytest.mark.parametrize(
    ("command", "payload"),
    [
        ("long.agent.start", _start_payload()),
        (
            "long.task.resume",
            {"taskId": "task-1", "clientRequestId": "placeholder-request-id"},
        ),
        (
            "long.task.cancel",
            {"taskId": "task-1", "clientRequestId": "placeholder-request-id"},
        ),
    ],
)
def test_task_mutations_require_request_ids_between_16_and_128_characters(
    command: str,
    payload: dict[str, Any],
    request_id: str,
) -> None:
    module = _module()
    spec = _spec(module, command)
    api = RecordingApi()
    payload = dict(payload)
    payload["clientRequestId"] = request_id

    with pytest.raises(CliInputError, match="clientRequestId"):
        spec.handler(_runtime(spec, api), payload)

    assert api.calls == []


def test_task_resume_sends_only_checkpoint_resume_fields() -> None:
    module = _module()
    spec = _spec(module, "long.task.resume")
    api = RecordingApi()

    spec.handler(
        _runtime(spec, api),
        {
            "taskId": "task/1",
            "clientRequestId": "long-resume-20260806-0001",
            "writingSessionId": "session-1",
            "userMessage": "继续执行",
            "profile": "production",
        },
    )

    assert api.calls == [
        (
            "POST",
            "/api/v1/writing/runs/task%2F1/resume",
            {
                "json": {
                    "clientRequestId": "long-resume-20260806-0001",
                    "writingSessionId": "session-1",
                    "userMessage": "继续执行",
                }
            },
        )
    ]


@pytest.mark.parametrize("field", ["artifactId", "decision", "editedContent"])
def test_task_resume_rejects_artifact_decision_fields(field: str) -> None:
    module = _module()
    spec = _spec(module, "long.task.resume")
    api = RecordingApi()
    payload: dict[str, Any] = {
        "taskId": "task-1",
        "clientRequestId": "long-resume-20260806-0001",
        field: "not-allowed",
    }

    with pytest.raises(CliInputError):
        spec.handler(_runtime(spec, api), payload)

    assert api.calls == []


def test_task_cancel_sends_only_caller_owned_request_id() -> None:
    module = _module()
    spec = _spec(module, "long.task.cancel")
    api = RecordingApi()

    spec.handler(
        _runtime(spec, api),
        {
            "taskId": "task/1",
            "clientRequestId": "long-cancel-20260806-0001",
            "profile": "production",
        },
    )

    assert api.calls == [
        (
            "POST",
            "/api/v1/writing/runs/task%2F1/cancel",
            {"json": {"clientRequestId": "long-cancel-20260806-0001"}},
        )
    ]


def test_task_conflict_preserves_server_details_and_long_exit_code() -> None:
    module = _module()
    spec = _spec(module, "long.agent.start")
    error = CoreApiError(
        409,
        code="WRITING_TARGET_BUSY",
        message="目标正被占用",
        details={"taskId": "task-existing"},
        request_id="request-server-1",
    )
    api = RecordingApi(error=error)

    with pytest.raises(CoreApiError) as caught:
        spec.handler(_runtime(spec, api), _start_payload())

    assert caught.value.code == "WRITING_TARGET_BUSY"
    assert caught.value.message == "目标正被占用"
    assert caught.value.details == {"taskId": "task-existing"}
    assert caught.value.request_id == "request-server-1"
    assert command_exit_code(spec, caught.value) == 4
    assert len(api.calls) == 1
