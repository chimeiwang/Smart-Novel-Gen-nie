from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from typing import Any

import pytest
from inkforge_cli.cli import run
from inkforge_cli.config import MemoryConfigStore, ProfileConfig
from inkforge_cli.credentials import MemoryCredentialStore
from inkforge_cli.registry import get_command_registry
from inkforge_cli.runtime import CliDependencies


@dataclass
class RecordingApi:
    response: Any = field(
        default_factory=lambda: {"novelId": "novel-1", "chapterId": "chapter-1"}
    )
    calls: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        self.calls.append((method, path, kwargs))
        return self.response

    def login(self, username: str, password: str) -> tuple[dict[str, Any], str]:
        raise AssertionError("创建命令不应重新登录")

    def iter_sse(self, task_id: str, last_event_id: str | None = None) -> Any:
        raise AssertionError("创建命令不应连接 SSE")


def _dependencies(api: RecordingApi) -> CliDependencies:
    config = MemoryConfigStore()
    config.save(
        "default",
        ProfileConfig(origin="http://127.0.0.1:8000", username="tester"),
    )
    credentials = MemoryCredentialStore()
    credentials.set("default", "http://127.0.0.1:8000", "session-cookie")
    return CliDependencies(
        api_factory=lambda origin, token=None: api,
        config_store=config,
        credential_store=credentials,
        getpass_fn=lambda prompt: "unused",
        stdin_isatty=lambda: False,
    )


def _invoke(
    payload: dict[str, Any],
    api: RecordingApi,
    command: str = "long.novel.create",
) -> tuple[int, dict[str, Any], str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = run(
        [command],
        stdin=io.StringIO(json.dumps(payload, ensure_ascii=False)),
        stdout=stdout,
        stderr=stderr,
        dependencies=_dependencies(api),
    )
    return exit_code, json.loads(stdout.getvalue()), stderr.getvalue()


def test_long_novel_create_posts_fixed_long_serial_payload() -> None:
    api = RecordingApi()
    payload = {
        "profile": "default",
        "name": "雾港巡夜人",
        "summary": "灵潮初退时的遗产处置故事",
        "targetTotalWordCount": 800_000,
        "genre": "现代修仙",
        "protagonist": "陆沉",
        "coreSellingPoint": "以职业流程拆解失控洞天",
        "readerPromise": "每卷解决一处危险遗产",
        "firstChapterGoal": "接下第一份异常委托",
    }

    exit_code, output, stderr = _invoke(payload, api)

    assert exit_code == 0
    assert stderr == ""
    assert output["data"] == {"novelId": "novel-1", "chapterId": "chapter-1"}
    assert api.calls == [
        (
            "POST",
            "/api/v1/novels",
            {
                "json": {
                    "name": "雾港巡夜人",
                    "summary": "灵潮初退时的遗产处置故事",
                    "targetTotalWordCount": 800_000,
                    "genre": "现代修仙",
                    "protagonist": "陆沉",
                    "coreSellingPoint": "以职业流程拆解失控洞天",
                    "readerPromise": "每卷解决一处危险遗产",
                    "firstChapterGoal": "接下第一份异常委托",
                    "storyLengthProfile": "long_serial",
                }
            },
        )
    ]


def test_long_novel_create_supports_minimal_payload() -> None:
    api = RecordingApi()

    exit_code, _output, _stderr = _invoke({"name": "新长篇"}, api)

    assert exit_code == 0
    assert api.calls[0][2]["json"] == {
        "name": "新长篇",
        "storyLengthProfile": "long_serial",
    }


@pytest.mark.parametrize("name", [None, "", "  ", True, 123])
def test_long_novel_create_rejects_invalid_name_before_request(name: Any) -> None:
    api = RecordingApi()
    payload = {} if name is None else {"name": name}

    exit_code, output, _stderr = _invoke(payload, api)

    assert exit_code == 2
    assert output["error"]["code"] == "FIELD_REQUIRED"
    assert api.calls == []


@pytest.mark.parametrize(
    "field",
    [
        "storyLengthProfile",
        "clientRequestId",
        "sourceKind",
        "sourceText",
        "outputFile",
        "unexpected",
    ],
)
def test_long_novel_create_rejects_forbidden_fields_before_request(
    field: str,
) -> None:
    api = RecordingApi()

    exit_code, output, _stderr = _invoke({"name": "新长篇", field: "value"}, api)

    assert exit_code == 2
    assert output["error"]["code"] == "UNEXPECTED_FIELDS"
    assert api.calls == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("summary", 1),
        ("genre", False),
        ("protagonist", []),
        ("coreSellingPoint", {}),
        ("readerPromise", 1.5),
        ("firstChapterGoal", True),
        ("targetTotalWordCount", True),
        ("targetTotalWordCount", "800000"),
        ("targetTotalWordCount", 0),
    ],
)
def test_long_novel_create_rejects_invalid_optional_fields_before_request(
    field: str,
    value: Any,
) -> None:
    api = RecordingApi()

    exit_code, output, _stderr = _invoke({"name": "新长篇", field: value}, api)

    assert exit_code == 2
    assert output["error"]["code"] == "INVALID_FIELD"
    assert api.calls == []


def test_long_novel_create_registry_metadata_is_exact() -> None:
    spec = get_command_registry()["long.novel.create"]

    assert spec.inputMode == "json"
    assert spec.outputMode == "json"
    assert spec.fileOutput.kind == "none"
    assert spec.mutation is True
    assert spec.requiresIdentity is True
    assert spec.requiresClientRequestId is False


def test_long_novel_summary_save_puts_exact_cas_payload() -> None:
    api = RecordingApi(response={"id": "novel-1", "summary": "新摘要"})

    exit_code, output, stderr = _invoke(
        {
            "profile": "default",
            "novelId": "novel/1",
            "summary": "新摘要",
            "expectedUpdatedAt": "2026-08-09T00:00:00Z",
        },
        api,
        "long.novel.summary.save",
    )

    assert exit_code == 0
    assert stderr == ""
    assert output["data"] == {"id": "novel-1", "summary": "新摘要"}
    assert api.calls == [
        (
            "PUT",
            "/api/v1/novels/novel%2F1/summary",
            {
                "json": {
                    "summary": "新摘要",
                    "expectedUpdatedAt": "2026-08-09T00:00:00Z",
                }
            },
        )
    ]


def test_long_novel_summary_save_supports_explicit_null() -> None:
    api = RecordingApi(response={"id": "novel-1", "summary": None})

    exit_code, _output, _stderr = _invoke(
        {
            "novelId": "novel-1",
            "summary": None,
            "expectedUpdatedAt": "2026-08-09T00:00:00Z",
        },
        api,
        "long.novel.summary.save",
    )

    assert exit_code == 0
    assert api.calls[0][2]["json"]["summary"] is None


@pytest.mark.parametrize(
    "payload",
    [
        {"summary": "摘要", "expectedUpdatedAt": "2026-08-09T00:00:00Z"},
        {"novelId": "novel-1", "expectedUpdatedAt": "2026-08-09T00:00:00Z"},
        {"novelId": "novel-1", "summary": "摘要"},
        {"novelId": "novel-1", "summary": 1, "expectedUpdatedAt": "v1"},
        {"novelId": "novel-1", "summary": "摘要", "expectedUpdatedAt": ""},
        {
            "novelId": "novel-1",
            "summary": "摘要",
            "expectedUpdatedAt": "v1",
            "outputFile": "result.json",
        },
        {
            "novelId": "novel-1",
            "summary": "摘要",
            "expectedUpdatedAt": "v1",
            "clientRequestId": "request-12345678",
        },
        {
            "novelId": "novel-1",
            "summary": "摘要",
            "expectedUpdatedAt": "v1",
            "unexpected": True,
        },
    ],
)
def test_long_novel_summary_save_rejects_invalid_payload(payload: dict[str, Any]) -> None:
    api = RecordingApi()

    exit_code, output, _stderr = _invoke(
        payload,
        api,
        "long.novel.summary.save",
    )

    assert exit_code == 2
    assert output["error"]["code"] in {
        "FIELD_REQUIRED",
        "INVALID_FIELD",
        "INVALID_EXPECTED_UPDATED_AT",
        "UNEXPECTED_FIELDS",
    }
    assert api.calls == []


def test_long_novel_summary_save_registry_metadata_is_exact() -> None:
    spec = get_command_registry()["long.novel.summary.save"]

    assert spec.inputMode == "json"
    assert spec.outputMode == "json"
    assert spec.fileOutput.kind == "none"
    assert spec.mutation is True
    assert spec.requiresIdentity is True
    assert spec.requiresClientRequestId is False
