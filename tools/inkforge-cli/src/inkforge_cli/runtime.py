from __future__ import annotations

import getpass
import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, TextIO, cast

from .api import CoreApiClient, CoreApiError, CoreTransportError
from .config import ConfigStore, JsonConfigStore
from .credentials import CredentialStore, KeyringCredentialStore
from .io import write_bytes
from .json_types import JsonObject, JsonValue

if TYPE_CHECKING:
    from .registry import CommandResult, CommandSpec


class ApiClient(Protocol):
    def request(self, method: str, path: str, **kwargs: Any) -> Any: ...

    def login(self, username: str, password: str) -> tuple[dict[str, Any], str]: ...

    def iter_sse(
        self,
        task_id: str,
        last_event_id: str | None = None,
    ) -> Any: ...


@dataclass(frozen=True, slots=True)
class CliDependencies:
    api_factory: Callable[[str, str | None], ApiClient]
    config_store: ConfigStore
    credential_store: CredentialStore
    getpass_fn: Callable[[str], str]
    stdin_isatty: Callable[[], bool]


class CliInputError(RuntimeError):
    def __init__(self, code: str, message: str, *, exit_code: int = 2) -> None:
        self.code = code
        self.message = message
        self.exit_code = exit_code
        super().__init__(message)


class RuntimeContractError(RuntimeError):
    pass


class CoreResponseContractError(CoreApiError):
    def __init__(self, message: str) -> None:
        super().__init__(
            502,
            code="CORE_RESPONSE_CONTRACT_ERROR",
            message=message,
        )


class LocalFileError(OSError):
    pass


class _RawJsonResult(dict[str, JsonValue]):
    """保留历史命令返回 JSON 数组或标量时的外部 data 形状。"""

    def __init__(self, data: JsonValue) -> None:
        super().__init__()
        self.data = data


@dataclass(frozen=True, slots=True)
class CliRuntime:
    spec: CommandSpec
    argv: tuple[str, ...]
    dependencies: CliDependencies
    api: ApiClient | None = None
    profile: str | None = None
    origin: str | None = None

    def require_api(self) -> ApiClient:
        if self.api is None:
            raise RuntimeContractError(f"命令 {self.spec.name} 缺少已认证 API 客户端")
        return self.api

    def require_identity(self) -> tuple[str, str]:
        if self.profile is None or self.origin is None:
            raise RuntimeContractError(f"命令 {self.spec.name} 缺少已认证身份")
        return self.profile, self.origin


def default_dependencies(stdin: TextIO) -> CliDependencies:
    def api_factory(origin: str, token: str | None = None) -> ApiClient:
        return CoreApiClient(origin, token)

    return CliDependencies(
        api_factory=api_factory,
        config_store=JsonConfigStore(),
        credential_store=KeyringCredentialStore(),
        getpass_fn=getpass.getpass,
        stdin_isatty=stdin.isatty,
    )


def read_json_payload(stdin: TextIO) -> JsonObject:
    raw = stdin.read().removeprefix("\ufeff")
    if not raw.strip():
        raise CliInputError("JSON_REQUIRED", "stdin 必须包含一个 UTF-8 JSON 对象")
    try:
        payload: object = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CliInputError("INVALID_JSON", "stdin 不是有效的单个 JSON 对象") from exc
    if not isinstance(payload, dict):
        raise CliInputError("JSON_OBJECT_REQUIRED", "stdin 顶层必须是 JSON 对象")
    if not _is_json_object(payload):
        raise CliInputError("INVALID_JSON", "stdin 包含无法表示为 JSON 的值")
    return cast(JsonObject, payload)


def prepare_runtime(
    spec: CommandSpec,
    command_argv: list[str],
    *,
    stdin: TextIO,
    dependencies: CliDependencies,
) -> tuple[CliRuntime, JsonObject]:
    if spec.inputMode == "argv_tty":
        return (
            CliRuntime(
                spec=spec,
                argv=tuple(command_argv),
                dependencies=dependencies,
            ),
            {},
        )
    if command_argv:
        raise CliInputError("INVALID_ARGUMENTS", "非登录命令不接受命令行参数")

    payload = read_json_payload(stdin)
    if not spec.requiresIdentity:
        runtime = CliRuntime(
            spec=spec,
            argv=(),
            dependencies=dependencies,
        )
    else:
        profile = _profile_from(payload)
        config = dependencies.config_store.get(profile)
        if config is None:
            raise CliInputError(
                "AUTH_REQUIRED",
                "尚未登录，请在真实终端执行 auth.login",
                exit_code=3,
            )
        token = dependencies.credential_store.get(profile, config.origin)
        if token is None:
            raise CliInputError(
                "AUTH_REQUIRED",
                "安全凭据中没有有效会话，请在真实终端重新登录",
                exit_code=3,
            )
        runtime = CliRuntime(
            spec=spec,
            argv=(),
            dependencies=dependencies,
            api=dependencies.api_factory(config.origin, token),
            profile=profile,
            origin=config.origin,
        )

    if spec.requiresClientRequestId:
        require_client_request_id(payload)
    return runtime, payload


def _profile_from(payload: JsonObject) -> str:
    value = payload.get("profile", "default")
    if not isinstance(value, str) or not value:
        raise CliInputError("INVALID_PROFILE", "profile 必须是非空字符串")
    return value


def require_client_request_id(payload: JsonObject) -> str:
    value = payload.get("clientRequestId")
    if not isinstance(value, str) or len(value) < 16:
        raise CliInputError(
            "CLIENT_REQUEST_ID_REQUIRED",
            "写请求必须由调用方提供长度至少 16 的稳定 clientRequestId",
        )
    return value


def command_exit_code(spec: CommandSpec | None, error: Exception) -> int:
    if not _is_long_command(spec):
        if isinstance(error, CliInputError | CoreApiError):
            return error.exit_code
        if isinstance(
            error,
            LocalFileError | OSError | UnicodeError | json.JSONDecodeError,
        ):
            return 6
        return 1

    if isinstance(error, CliInputError):
        return 3 if error.exit_code == 3 else 2
    if isinstance(error, CoreApiError):
        if error.status_code == 422:
            return 2
        if error.status_code == 401:
            return 3
        if error.status_code == 409:
            return 4
        return 5
    if isinstance(error, CoreTransportError):
        return 5
    if isinstance(
        error,
        LocalFileError | OSError | UnicodeError | json.JSONDecodeError,
    ):
        return 6
    return 1


def ensure_command_json_result(value: object) -> JsonObject:
    if isinstance(value, dict):
        if not _is_json_object(value):
            raise RuntimeContractError("命令处理器返回了无效 JSON 对象")
        return cast(JsonObject, value)
    if _is_json_value(value):
        return _RawJsonResult(cast(JsonValue, value))
    raise RuntimeContractError("命令处理器返回了无法序列化的结果")


def write_json_line(stream: TextIO, value: JsonValue) -> None:
    stream.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")
    stream.flush()


def emit_command_result(
    spec: CommandSpec,
    result: CommandResult,
    stdout: TextIO,
    *,
    payload: JsonObject | None = None,
) -> int:
    if spec.outputMode == "json":
        if not isinstance(result, dict) or not _is_json_object(result):
            raise RuntimeContractError(
                f"命令 {spec.name} 声明 JSON 输出，但处理器未返回 JSON 对象"
            )
        data: JsonValue = result.data if isinstance(result, _RawJsonResult) else result
        output_file = _output_file(spec, payload)
        if output_file is not None:
            data = _apply_file_output(spec, data, output_file)
        write_json_line(
            stdout,
            {
                "ok": True,
                "command": spec.name,
                "data": data,
            },
        )
        return 0

    if isinstance(result, dict) or not isinstance(result, Iterator):
        raise RuntimeContractError(
            f"命令 {spec.name} 声明 JSONL 输出，但处理器未返回生成器"
        )
    while True:
        try:
            frame = next(result)
        except StopIteration as terminal:
            exit_code = terminal.value
            if type(exit_code) is not int:
                raise RuntimeContractError(
                    f"命令 {spec.name} 的 JSONL 生成器必须显式返回整数退出码"
                ) from terminal
            return exit_code
        if not isinstance(frame, dict) or not _is_json_object(frame):
            raise RuntimeContractError(f"命令 {spec.name} 输出了非 JSON 对象帧")
        write_json_line(stdout, frame)


def _is_long_command(spec: CommandSpec | None) -> bool:
    return spec is not None and spec.name.startswith("long.")


def _output_file(spec: CommandSpec, payload: JsonObject | None) -> str | None:
    if (
        not _is_long_command(spec)
        or spec.fileOutput.kind == "none"
        or payload is None
    ):
        return None
    value = payload.get("outputFile")
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise CliInputError("INVALID_OUTPUT_FILE", "outputFile 必须是非空字符串")
    return value


def _apply_file_output(
    spec: CommandSpec,
    data: JsonValue,
    output_file: str,
) -> JsonValue:
    if spec.fileOutput.kind == "data_json":
        try:
            payload = (
                json.dumps(data, ensure_ascii=False, indent=2) + "\n"
            ).encode("utf-8")
            descriptor = write_bytes(
                output_file,
                payload,
                "application/json; charset=utf-8",
            )
        except (OSError, UnicodeError) as exc:
            raise LocalFileError("输出文件写入失败") from exc
        return {"resultFile": cast(JsonObject, dict(descriptor))}

    field = spec.fileOutput.field
    media_type = spec.fileOutput.media_type
    if not isinstance(data, dict) or field is None or media_type is None:
        raise CoreResponseContractError("远端响应不是可提取主文本的 JSON 对象")
    value = data.get(field)
    if not isinstance(value, str):
        raise CoreResponseContractError(f"响应缺少文本字段：{field}")
    try:
        descriptor = write_bytes(output_file, value.encode("utf-8"), media_type)
    except (OSError, UnicodeError) as exc:
        raise LocalFileError("输出文件写入失败") from exc
    transformed = dict(data)
    del transformed[field]
    transformed[f"{field}File"] = cast(JsonObject, dict(descriptor))
    return transformed


def _is_json_object(value: object) -> bool:
    return isinstance(value, dict) and all(
        isinstance(key, str) and _is_json_value(item) for key, item in value.items()
    )


def _is_json_value(value: object) -> bool:
    if value is None or isinstance(value, str | int | float | bool):
        return True
    if isinstance(value, list):
        return all(_is_json_value(item) for item in value)
    return _is_json_object(value)
