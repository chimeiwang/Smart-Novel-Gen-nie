from __future__ import annotations

import argparse
import getpass
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Never, Protocol, TextIO
from urllib.parse import quote

from .api import CoreApiClient, CoreApiError, SseConnectionError
from .config import ConfigStore, JsonConfigStore, ProfileConfig
from .credentials import (
    CredentialStore,
    InsecureCredentialBackendError,
    KeyringCredentialStore,
    validate_core_origin,
)
from .files import (
    DirtySnapshotError,
    atomic_write_text,
    ensure_snapshot_clean,
    export_snapshot,
    load_snapshot_manifest,
    sha256_text,
    write_large_result,
)

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_MAX_SSE_RECONNECTS = 3
_SHORT_AGENT_START_FIELDS = (
    "clientRequestId",
    "novelId",
    "documentType",
    "chapterId",
    "baseVersionId",
    "sourceOutlineVersionId",
    "selectionStart",
    "selectionEnd",
    "selectedTextHash",
    "userInstruction",
)


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


class SilentArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise CliInputError("INVALID_ARGUMENTS", "auth.login 参数无效")


def _default_dependencies(stdin: TextIO) -> CliDependencies:
    def api_factory(origin: str, token: str | None = None) -> ApiClient:
        return CoreApiClient(origin, token)

    return CliDependencies(
        api_factory=api_factory,
        config_store=JsonConfigStore(),
        credential_store=KeyringCredentialStore(),
        getpass_fn=getpass.getpass,
        stdin_isatty=stdin.isatty,
    )


def _write_json(stream: TextIO, value: object) -> None:
    stream.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")
    stream.flush()


def _read_payload(stdin: TextIO) -> dict[str, Any]:
    raw = stdin.read().removeprefix("\ufeff")
    if not raw.strip():
        raise CliInputError("JSON_REQUIRED", "stdin 必须包含一个 UTF-8 JSON 对象")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CliInputError("INVALID_JSON", "stdin 不是有效的单个 JSON 对象") from exc
    if not isinstance(payload, dict):
        raise CliInputError("JSON_OBJECT_REQUIRED", "stdin 顶层必须是 JSON 对象")
    return payload


def _require_string(
    payload: dict[str, Any],
    name: str,
    *,
    allow_empty: bool = False,
) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or (not allow_empty and not value):
        raise CliInputError("FIELD_REQUIRED", f"缺少字符串字段 {name}")
    return value


def _require_client_request_id(payload: dict[str, Any]) -> str:
    value = payload.get("clientRequestId")
    if not isinstance(value, str) or len(value) < 16:
        raise CliInputError(
            "CLIENT_REQUEST_ID_REQUIRED",
            "写请求必须由调用方提供长度至少 16 的稳定 clientRequestId",
        )
    return value


def _require_confirmation_hash(payload: dict[str, Any]) -> str:
    value = payload.get("confirmationHash")
    if not isinstance(value, str) or not _SHA256_PATTERN.fullmatch(value):
        raise CliInputError(
            "INVALID_CONFIRMATION_HASH",
            "confirmationHash 必须是 64 位小写 SHA-256",
        )
    return value


def _ensure_clean_snapshot(
    payload: dict[str, Any],
    *,
    novel_id: str,
) -> None:
    manifest_path = payload.get("manifestPath")
    if not isinstance(manifest_path, str) or not manifest_path:
        raise CliInputError(
            "MANIFEST_REQUIRED",
            "写操作必须提供 short.pull 生成的 manifestPath",
        )
    ensure_snapshot_clean(manifest_path, novel_id=novel_id)


def _profile_from(payload: dict[str, Any]) -> str:
    value = payload.get("profile", "default")
    if not isinstance(value, str) or not value:
        raise CliInputError("INVALID_PROFILE", "profile 必须是非空字符串")
    return value


def _public_id(value: str) -> str:
    return quote(value, safe="")


def _without(payload: dict[str, Any], *names: str) -> dict[str, Any]:
    excluded = set(names)
    return {key: value for key, value in payload.items() if key not in excluded}


def _write_response_file(
    response: Any,
    *,
    payload: dict[str, Any],
    field: str,
    default_name: str,
) -> Any:
    if not isinstance(response, dict) or field not in response:
        return response
    output_file = payload.get("outputFile")
    if output_file is None:
        output_directory = payload.get("outputDirectory")
        if isinstance(output_directory, str) and output_directory:
            output_file = str(Path(output_directory) / default_name)
    if not isinstance(output_file, str) or not output_file:
        raise CliInputError(
            "OUTPUT_FILE_REQUIRED",
            f"响应包含完整 {field}，必须提供 outputFile 或 outputDirectory",
        )

    raw_value = response[field]
    content = (
        raw_value
        if isinstance(raw_value, str)
        else json.dumps(raw_value, ensure_ascii=False, indent=2) + "\n"
    )
    result = dict(response)
    del result[field]
    result[f"{field}File"] = write_large_result(output_file, content)
    return result


def _login(
    argv: list[str],
    *,
    stdout: TextIO,
    dependencies: CliDependencies,
) -> int:
    parser = SilentArgumentParser(prog="inkforge auth.login", add_help=False)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--profile", default="default")
    arguments = parser.parse_args(argv)

    if not dependencies.stdin_isatty():
        raise CliInputError(
            "TTY_REQUIRED",
            "auth.login 必须由用户在真实终端中交互执行",
        )
    origin = validate_core_origin(arguments.origin)
    password = dependencies.getpass_fn("InkForge 密码：")
    client = dependencies.api_factory(origin, None)
    user, token = client.login(arguments.username, password)
    dependencies.credential_store.set(arguments.profile, origin, token)
    dependencies.config_store.save(
        arguments.profile,
        ProfileConfig(origin=origin, username=arguments.username),
    )
    _write_json(
        stdout,
        {"ok": True, "command": "auth.login", "data": user},
    )
    return 0


def _pull(api: ApiClient, payload: dict[str, Any]) -> dict[str, object]:
    novel_id = _require_string(payload, "novelId")
    target = Path(_require_string(payload, "outputDirectory"))
    encoded_novel_id = _public_id(novel_id)
    bootstrap = api.request(
        "GET",
        f"/api/v1/novels/{encoded_novel_id}/workspace/bootstrap",
    )
    if not isinstance(bootstrap, dict):
        raise CoreApiError(
            500,
            code="INVALID_BOOTSTRAP_RESPONSE",
            message="作品工作区响应格式无效",
        )
    current_chapter = bootstrap.get("currentChapter")
    if not isinstance(current_chapter, dict):
        chapters = bootstrap.get("chapters")
        first_chapter = chapters[0] if isinstance(chapters, list) and chapters else None
        chapter_id = first_chapter.get("id") if isinstance(first_chapter, dict) else None
        if isinstance(chapter_id, str):
            bootstrap = api.request(
                "GET",
                f"/api/v1/novels/{encoded_novel_id}/workspace/bootstrap",
                params={"chapterId": chapter_id},
            )
            current_chapter = (
                bootstrap.get("currentChapter")
                if isinstance(bootstrap, dict)
                else None
            )
    if not isinstance(current_chapter, dict):
        raise CoreApiError(
            500,
            code="MANUSCRIPT_CHAPTER_MISSING",
            message="中短篇作品缺少唯一全文章节",
        )

    planning = api.request(
        "GET",
        f"/api/v1/novels/{encoded_novel_id}/workspace/planning",
    )
    outline_record = planning.get("outline") if isinstance(planning, dict) else None
    outline = (
        outline_record.get("content", "")
        if isinstance(outline_record, dict)
        else ""
    )
    manuscript = current_chapter.get("content", "")
    if not isinstance(outline, str) or not isinstance(manuscript, str):
        raise CoreApiError(
            500,
            code="INVALID_DOCUMENT_CONTENT",
            message="服务端返回了无效的文档内容",
        )
    chapter_id = current_chapter.get("id")
    if not isinstance(chapter_id, str):
        raise CoreApiError(
            500,
            code="MANUSCRIPT_CHAPTER_MISSING",
            message="全文章节缺少 id",
        )
    outline_versions = api.request(
        "GET",
        f"/api/v1/novels/{encoded_novel_id}/versions",
        params={"documentType": "outline"},
    )
    manuscript_versions = api.request(
        "GET",
        f"/api/v1/novels/{encoded_novel_id}/versions",
        params={"documentType": "manuscript", "chapterId": chapter_id},
    )
    metadata = {
        "chapterId": chapter_id,
        "outlineUpdatedAt": (
            outline_record.get("updatedAt") if isinstance(outline_record, dict) else None
        ),
        "manuscriptUpdatedAt": current_chapter.get("updatedAt"),
        "outlineVersions": outline_versions,
        "manuscriptVersions": manuscript_versions,
    }
    return export_snapshot(
        target,
        novel_id=novel_id,
        outline=outline,
        manuscript=manuscript,
        metadata=metadata,
    )


def _draft_save(api: ApiClient, payload: dict[str, Any]) -> Any:
    novel_id = _require_string(payload, "novelId")
    document_type = _require_string(payload, "documentType")
    if document_type not in {"outline", "manuscript"}:
        raise CliInputError(
            "INVALID_DOCUMENT_TYPE",
            "documentType 只能是 outline 或 manuscript",
        )
    file_path = Path(_require_string(payload, "filePath")).resolve()
    manifest_path = Path(_require_string(payload, "manifestPath")).resolve()
    manifest = load_snapshot_manifest(manifest_path, novel_id=novel_id)
    documents = manifest["documents"]
    descriptor = documents[document_type]
    if descriptor["path"] != str(file_path):
        raise CliInputError(
            "INVALID_MANIFEST",
            "filePath 与 manifest 中的文档路径不一致",
        )
    content = file_path.read_text(encoding="utf-8")
    updated_at_field = (
        "outlineUpdatedAt" if document_type == "outline" else "manuscriptUpdatedAt"
    )
    expected_updated_at = manifest.get(updated_at_field)
    if not isinstance(expected_updated_at, str) or not expected_updated_at:
        raise CliInputError(
            "INVALID_MANIFEST",
            f"manifest 缺少 {updated_at_field}",
        )
    if document_type == "outline":
        response = api.request(
            "PUT",
            f"/api/v1/novels/{_public_id(novel_id)}/outline",
            json={"content": content, "expectedUpdatedAt": expected_updated_at},
        )
    elif document_type == "manuscript":
        chapter_id = manifest.get("chapterId")
        if not isinstance(chapter_id, str) or not chapter_id:
            raise CliInputError("INVALID_MANIFEST", "manifest 缺少 chapterId")
        title = payload.get("title", "全文")
        if not isinstance(title, str) or not title:
            raise CliInputError("INVALID_TITLE", "title 必须是非空字符串")
        response = api.request(
            "PATCH",
            f"/api/v1/chapters/{_public_id(chapter_id)}",
            json={
                "title": title,
                "content": content,
                "expectedUpdatedAt": expected_updated_at,
            },
        )

    next_updated_at = response.get("updatedAt") if isinstance(response, dict) else None
    if not isinstance(next_updated_at, str) or not next_updated_at:
        raise CoreApiError(
            500,
            code="INVALID_DRAFT_SAVE_RESPONSE",
            message="工作稿保存响应缺少 updatedAt，未推进本地 manifest",
        )
    content_hash = sha256_text(content)
    manifest[updated_at_field] = next_updated_at
    descriptor["contentHash"] = content_hash
    atomic_write_text(
        manifest_path,
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )
    result = dict(response)
    result["manifestPath"] = str(manifest_path)
    result["contentHash"] = content_hash
    return result


def _version_command(api: ApiClient, command: str, payload: dict[str, Any]) -> Any:
    novel_id = _require_string(payload, "novelId")
    root = f"/api/v1/novels/{_public_id(novel_id)}"
    local_fields = (
        "profile",
        "novelId",
        "versionId",
        "outputFile",
        "outputDirectory",
        "manifestPath",
    )
    if command == "short.version.preview":
        body = _without(payload, *local_fields)
        response = api.request("POST", f"{root}/versions/preview", json=body)
        return _write_response_file(
            response,
            payload=payload,
            field="diff",
            default_name="version-preview-diff.json",
        )
    if command == "short.version.submit":
        _require_client_request_id(payload)
        _require_confirmation_hash(payload)
        _ensure_clean_snapshot(payload, novel_id=novel_id)
        return api.request(
            "POST",
            f"{root}/versions",
            json=_without(payload, *local_fields),
        )
    if command == "short.version.list":
        return api.request(
            "GET",
            f"{root}/versions",
            params=_without(payload, *local_fields),
        )
    if command == "short.version.diff":
        response = api.request(
            "GET",
            f"{root}/version-diff",
            params=_without(payload, *local_fields),
        )
        if not response:
            return response
        output_file = payload.get("outputFile")
        if output_file is None:
            output_directory = payload.get("outputDirectory")
            if isinstance(output_directory, str) and output_directory:
                output_file = str(Path(output_directory) / "version-diff.json")
        if not isinstance(output_file, str) or not output_file:
            raise CliInputError(
                "OUTPUT_FILE_REQUIRED",
                "完整 Diff 必须提供 outputFile 或 outputDirectory",
            )
        serialized = json.dumps(response, ensure_ascii=False, indent=2) + "\n"
        return {"diffFile": write_large_result(output_file, serialized)}
    version_id = _require_string(payload, "versionId")
    encoded_version_id = _public_id(version_id)
    if command == "short.version.get":
        response = api.request("GET", f"{root}/versions/{encoded_version_id}")
        return _write_response_file(
            response,
            payload=payload,
            field="content",
            default_name=f"version-{version_id}.txt",
        )
    if command in {"short.version.adopt", "short.version.restore"}:
        _require_client_request_id(payload)
        _require_confirmation_hash(payload)
        _ensure_clean_snapshot(payload, novel_id=novel_id)
        action = "adopt" if command.endswith("adopt") else "restore"
        return api.request(
            "POST",
            f"{root}/versions/{encoded_version_id}/{action}",
            json=_without(payload, *local_fields),
        )
    raise CliInputError("UNKNOWN_COMMAND", f"未知命令 {command}")


def _dispatch(api: ApiClient, command: str, payload: dict[str, Any]) -> Any:
    if command == "auth.whoami":
        response = api.request("GET", "/api/v1/auth/me")
        expected_username = payload.get("expectedUsername")
        if expected_username is not None:
            if not isinstance(expected_username, str) or not expected_username:
                raise CliInputError(
                    "INVALID_EXPECTED_USERNAME",
                    "expectedUsername 必须是非空字符串",
                )
            actual_username = (
                response.get("username") if isinstance(response, dict) else None
            )
            if actual_username != expected_username:
                raise CliInputError(
                    "IDENTITY_MISMATCH",
                    "当前登录身份与 expectedUsername 不一致",
                    exit_code=3,
                )
        return response
    if command == "short.list":
        response = api.request(
            "GET",
            "/api/v1/novels",
            params={"storyLengthProfile": "short_medium"},
        )
        if isinstance(response, dict) and isinstance(response.get("novels"), list):
            return response
        return {"novels": response}
    if command == "short.create":
        _require_client_request_id(payload)
        return api.request(
            "POST",
            "/api/v1/novels",
            json=_without(payload, "profile"),
        )
    if command == "short.pull":
        return _pull(api, payload)
    if command == "short.draft.save":
        return _draft_save(api, payload)
    if command.startswith("short.version."):
        return _version_command(api, command, payload)
    if command == "short.agent.start":
        _require_client_request_id(payload)
        novel_id = _require_string(payload, "novelId")
        _ensure_clean_snapshot(payload, novel_id=novel_id)
        operation = payload.get("operation")
        operation_mapping = {
            "outline": "generate_outline",
            "manuscript": "generate_manuscript",
            "selection": "replace_selection",
            "full_check": "full_check",
        }
        if not isinstance(operation, str) or operation not in operation_mapping:
            raise CliInputError(
                "INVALID_AGENT_OPERATION",
                "operation 只能是 outline、manuscript、selection 或 full_check",
            )
        if operation == "selection":
            instruction = payload.get("userInstruction")
            if not isinstance(instruction, str) or not instruction.strip():
                raise CliInputError(
                    "FIELD_REQUIRED",
                    "selection 操作必须提供非空 userInstruction",
                )
        body = {
            field: payload[field]
            for field in _SHORT_AGENT_START_FIELDS
            if field in payload
        }
        body["workflow"] = "short_medium"
        body["operation"] = operation_mapping[operation]
        return api.request(
            "POST",
            "/api/v1/writing/runs",
            json=body,
        )
    raise CliInputError("UNKNOWN_COMMAND", f"未知命令 {command}")


def _watch(
    api: ApiClient,
    payload: dict[str, Any],
    *,
    stdout: TextIO,
) -> int:
    task_id = _require_string(payload, "taskId")
    last_event_id = payload.get("lastEventId")
    if last_event_id is not None and not isinstance(last_event_id, str):
        raise CliInputError("INVALID_LAST_EVENT_ID", "lastEventId 必须是字符串")
    reconnects = 0
    while True:
        disconnected = False
        try:
            for event in api.iter_sse(task_id, last_event_id):
                event_id = event.get("id") if isinstance(event, dict) else None
                if isinstance(event_id, str) and event_id:
                    last_event_id = event_id
                _write_json(stdout, {"type": "event", **event})
        except SseConnectionError:
            disconnected = True

        state: Any | None = None
        if not disconnected or reconnects >= _MAX_SSE_RECONNECTS:
            state = api.request(
                "GET",
                f"/api/v1/writing/runs/{_public_id(task_id)}",
            )
            if _is_terminal_run_state(state):
                _write_json(stdout, {"type": "terminal", "data": state})
                return 0
        if reconnects >= _MAX_SSE_RECONNECTS:
            _write_json(stdout, {"type": "state", "data": state})
            _write_json(
                stdout,
                {
                    "type": "error",
                    "error": {
                        "code": "SSE_RECONNECT_EXHAUSTED",
                        "message": "SSE 重连次数已达上限，任务仍未进入终态",
                    },
                },
            )
            return 5
        reconnects += 1


def _is_terminal_run_state(state: Any) -> bool:
    if not isinstance(state, dict):
        return False
    phase = state.get("phase")
    command_status = state.get("commandStatus")
    return (
        phase in {"completed", "error", "cancelled", "canceled"}
        or command_status in {"succeeded", "failed"}
    )


def _error_payload(
    command: str,
    code: str,
    message: str,
    *,
    details: Any | None = None,
    request_id: str | None = None,
) -> dict[str, object]:
    error: dict[str, object] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    if request_id is not None:
        error["requestId"] = request_id
    return {
        "ok": False,
        "command": command,
        "error": error,
    }


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
    try:
        if not command:
            raise CliInputError("COMMAND_REQUIRED", "必须提供命令")
        deps = dependencies or _default_dependencies(input_stream)
        if command == "auth.login":
            return _login(arguments[1:], stdout=output_stream, dependencies=deps)
        if len(arguments) != 1:
            raise CliInputError("INVALID_ARGUMENTS", "非登录命令不接受命令行参数")

        payload = _read_payload(input_stream)
        profile = _profile_from(payload)
        config = deps.config_store.get(profile)
        if config is None:
            raise CliInputError(
                "AUTH_REQUIRED",
                "尚未登录，请在真实终端执行 auth.login",
                exit_code=3,
            )
        token = deps.credential_store.get(profile, config.origin)
        if token is None:
            raise CliInputError(
                "AUTH_REQUIRED",
                "安全凭据中没有有效会话，请在真实终端重新登录",
                exit_code=3,
            )
        api = deps.api_factory(config.origin, token)

        if command == "auth.logout":
            try:
                result = api.request("POST", "/api/v1/auth/logout")
            finally:
                deps.credential_store.delete(profile, config.origin)
            _write_json(
                output_stream,
                {"ok": True, "command": command, "data": result},
            )
            return 0
        if command == "short.agent.watch":
            return _watch(api, payload, stdout=output_stream)

        result = _dispatch(api, command, payload)
        _write_json(
            output_stream,
            {"ok": True, "command": command, "data": result},
        )
        return 0
    except CliInputError as exc:
        _write_json(output_stream, _error_payload(command, exc.code, exc.message))
        return exc.exit_code
    except CoreApiError as exc:
        _write_json(
            output_stream,
            _error_payload(
                command,
                exc.code,
                exc.message,
                details=exc.details,
                request_id=exc.request_id,
            ),
        )
        return exc.exit_code
    except (DirtySnapshotError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        _write_json(
            output_stream,
            _error_payload(command, "LOCAL_FILE_ERROR", str(exc)),
        )
        return 6
    except InsecureCredentialBackendError as exc:
        _write_json(
            output_stream,
            _error_payload(command, "SECURE_CREDENTIAL_BACKEND_REQUIRED", str(exc)),
        )
        return 3
    except Exception:
        # 不把异常对象写入输出，避免第三方库把请求头或凭据带入错误文本。
        error_stream.write("InkForge CLI 遇到未预期错误。\n")
        _write_json(
            output_stream,
            _error_payload(command, "UNEXPECTED_ERROR", "CLI 遇到未预期错误"),
        )
        return 1


def main() -> int:
    return run()
