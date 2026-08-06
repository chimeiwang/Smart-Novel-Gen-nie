from __future__ import annotations

import json
import sys
from typing import Any, TextIO, cast

from .api import CoreApiError, CoreTransportError
from .commands.short.snapshots import DirtySnapshotError
from .credentials import InsecureCredentialBackendError
from .json_types import JsonObject, JsonValue
from .runtime import (
    CliDependencies,
    CliInputError,
    command_exit_code,
    default_dependencies,
    emit_command_result,
    prepare_runtime,
    write_json_line,
)


def _error_payload(
    command: str,
    code: str,
    message: str,
    *,
    details: Any | None = None,
    request_id: str | None = None,
) -> JsonObject:
    error: JsonObject = {"code": code, "message": message}
    if details is not None:
        error["details"] = cast(JsonValue, details)
    if request_id is not None:
        error["requestId"] = request_id
    result: JsonObject = {
        "ok": False,
        "command": command,
        "error": error,
    }
    return result


def run(
    argv: list[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    dependencies: CliDependencies | None = None,
) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    input_stream = stdin or sys.stdin
    output_stream = stdout or sys.stdout
    error_stream = stderr or sys.stderr
    command = arguments[0] if arguments else ""
    spec = None
    try:
        if not command:
            raise CliInputError("COMMAND_REQUIRED", "必须提供命令")
        from .registry import get_command_registry

        spec = get_command_registry().get(command)
        if spec is None:
            raise CliInputError("UNKNOWN_COMMAND", f"未知命令 {command}")
        deps = dependencies or default_dependencies(input_stream)
        runtime, payload = prepare_runtime(
            spec,
            arguments[1:],
            stdin=input_stream,
            dependencies=deps,
        )
        result = spec.handler(runtime, payload)
        return emit_command_result(
            spec,
            result,
            output_stream,
            payload=payload,
        )
    except CliInputError as exc:
        write_json_line(output_stream, _error_payload(command, exc.code, exc.message))
        return command_exit_code(spec, exc)
    except CoreApiError as exc:
        write_json_line(
            output_stream,
            _error_payload(
                command,
                exc.code,
                exc.message,
                details=exc.details,
                request_id=exc.request_id,
            ),
        )
        return command_exit_code(spec, exc)
    except CoreTransportError as exc:
        exit_code = command_exit_code(spec, exc)
        if exit_code == 5:
            write_json_line(
                output_stream,
                _error_payload(command, exc.code, exc.message),
            )
        else:
            error_stream.write("InkForge CLI 遇到未预期错误。\n")
            write_json_line(
                output_stream,
                _error_payload(command, "UNEXPECTED_ERROR", "CLI 遇到未预期错误"),
            )
        return exit_code
    except (DirtySnapshotError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        write_json_line(
            output_stream,
            _error_payload(command, "LOCAL_FILE_ERROR", str(exc)),
        )
        return 6
    except InsecureCredentialBackendError as exc:
        write_json_line(
            output_stream,
            _error_payload(command, "SECURE_CREDENTIAL_BACKEND_REQUIRED", str(exc)),
        )
        return 3
    except Exception:
        # 不把异常对象写入输出，避免第三方库把请求头或凭据带入错误文本。
        error_stream.write("InkForge CLI 遇到未预期错误。\n")
        write_json_line(
            output_stream,
            _error_payload(command, "UNEXPECTED_ERROR", "CLI 遇到未预期错误"),
        )
        return 1


def main() -> int:
    return run()
