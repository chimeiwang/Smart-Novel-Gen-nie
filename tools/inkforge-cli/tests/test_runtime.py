from __future__ import annotations

import io
import json
from collections.abc import Generator

import pytest
from inkforge_cli.api import CoreApiError, CoreTransportError
from inkforge_cli.registry import CommandSpec, FileOutputSpec
from inkforge_cli.runtime import (
    CliInputError,
    LocalFileError,
    RuntimeContractError,
    command_exit_code,
    emit_command_result,
)


def _unused_handler(runtime: object, payload: dict[str, object]) -> dict[str, object]:
    return payload


def _spec(*, output_mode: str, name: str = "test.command") -> CommandSpec:
    return CommandSpec(
        name=name,
        handler=_unused_handler,
        inputMode="json",
        outputMode=output_mode,  # type: ignore[arg-type]
        fileOutput=FileOutputSpec(kind="none"),
        mutation=False,
        requiresIdentity=False,
        requiresClientRequestId=False,
    )


def test_json_command_emits_exactly_one_success_object() -> None:
    stdout = io.StringIO()

    code = emit_command_result(
        _spec(output_mode="json"),
        {"value": "正文尾部😀"},
        stdout,
    )

    assert code == 0
    assert json.loads(stdout.getvalue()) == {
        "ok": True,
        "command": "test.command",
        "data": {"value": "正文尾部😀"},
    }
    assert stdout.getvalue().count("\n") == 1


@pytest.mark.parametrize("terminal_code", [0, 5, 130])
def test_jsonl_command_preserves_frames_and_uses_generator_return_code(
    terminal_code: int,
) -> None:
    stdout = io.StringIO()

    def stream() -> Generator[dict[str, object], None, int]:
        yield {"type": "event", "data": {"sequence": 1}}
        yield {"type": "terminal", "data": {"state": "done"}}
        return terminal_code

    code = emit_command_result(_spec(output_mode="jsonl"), stream(), stdout)

    assert code == terminal_code
    assert [json.loads(line)["type"] for line in stdout.getvalue().splitlines()] == [
        "event",
        "terminal",
    ]


@pytest.mark.parametrize(
    ("output_mode", "result"),
    [
        ("json", iter([{"type": "event"}])),
        ("jsonl", {"value": 1}),
    ],
)
def test_runtime_fails_fast_when_handler_result_disagrees_with_metadata(
    output_mode: str,
    result: object,
) -> None:
    with pytest.raises(RuntimeContractError):
        emit_command_result(_spec(output_mode=output_mode), result, io.StringIO())


@pytest.mark.parametrize("terminal_value", [None, "5"])
def test_jsonl_command_requires_an_explicit_integer_return_code(
    terminal_value: object,
) -> None:
    def stream() -> Generator[dict[str, object], None, object]:
        yield {"type": "event"}
        return terminal_value

    with pytest.raises(RuntimeContractError):
        emit_command_result(_spec(output_mode="jsonl"), stream(), io.StringIO())


def test_jsonl_command_rejects_a_non_object_frame_after_preserving_prior_frames() -> None:
    stdout = io.StringIO()

    def stream() -> Generator[object, None, int]:
        yield {"type": "event"}
        yield ["invalid-frame"]
        return 0

    with pytest.raises(RuntimeContractError):
        emit_command_result(_spec(output_mode="jsonl"), stream(), stdout)

    assert json.loads(stdout.getvalue())["type"] == "event"


@pytest.mark.parametrize(
    ("error", "exit_code"),
    [
        (CliInputError("FIELD_REQUIRED", "字段缺失"), 2),
        (CliInputError("AUTH_REQUIRED", "缺少凭据", exit_code=3), 3),
        (CliInputError("IDENTITY_MISMATCH", "身份不匹配", exit_code=3), 3),
        (CoreApiError(422, code="INVALID", message="参数无效"), 2),
        (CoreApiError(401, code="UNAUTHORIZED", message="未登录"), 3),
        (CoreApiError(409, code="STALE_VERSION", message="版本冲突"), 4),
        (CoreApiError(403, code="FORBIDDEN", message="禁止访问"), 5),
        (CoreApiError(500, code="INTERNAL_ERROR", message="服务异常"), 5),
        (CoreTransportError(), 5),
        (LocalFileError("写入失败"), 6),
        (RuntimeError("未预期错误"), 1),
    ],
)
def test_long_command_uses_the_complete_exit_code_contract(
    error: Exception,
    exit_code: int,
) -> None:
    assert command_exit_code(
        _spec(output_mode="json", name="long.test"),
        error,
    ) == exit_code


def test_short_transport_error_keeps_the_legacy_exit_code() -> None:
    assert command_exit_code(
        _spec(output_mode="json", name="short.list"),
        CoreTransportError(),
    ) == 1
