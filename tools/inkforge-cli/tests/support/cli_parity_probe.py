from __future__ import annotations

import base64
import hashlib
import io
import json
import sys
import tempfile
import time
from collections import deque
from pathlib import Path
from typing import Any

from inkforge_cli.api import BinaryResponse, CoreApiError
from inkforge_cli.cli import run
from inkforge_cli.config import MemoryConfigStore, ProfileConfig
from inkforge_cli.credentials import MemoryCredentialStore
from inkforge_cli.runtime import CliDependencies


class ProbeApi:
    """记录规范化传输；错误模式和脚本模式都不会访问真实服务。"""

    def __init__(self, case: dict[str, Any]) -> None:
        self._fail_requests = case.get("mode", "core_error") == "core_error"
        self._responses = deque(case.get("responses", []))
        self._streams = deque(case.get("streams", []))
        self.calls: list[dict[str, Any]] = []

    @staticmethod
    def _fail() -> None:
        raise CoreApiError(
            503,
            code="PARITY_CORE_ERROR",
            message="差异测试远端错误",
            details={"source": "shared-fixture"},
            request_id="parity-request-1",
        )

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        files = kwargs.get("files")
        if isinstance(files, dict) and files:
            self._record_upload(method, path, files=files, kwargs=kwargs)
            return self._response()
        self.calls.append(
            {
                "kind": "request",
                "method": method,
                "path": path,
                "query": _normalize_query(kwargs.get("params")),
                "body": kwargs.get("json"),
            }
        )
        return self._response()

    def _record_upload(
        self,
        method: str,
        path: str,
        *,
        files: dict[str, Any],
        kwargs: dict[str, Any],
    ) -> None:
        upload = files.get("file")
        if not isinstance(upload, tuple) or len(upload) != 3:
            raise ValueError("差异探针只接受标准 file 三元组")
        filename, stream, media_type = upload
        if not hasattr(stream, "read"):
            raise ValueError("差异探针上传内容必须是可读流")
        content = stream.read()
        if not isinstance(content, bytes):
            raise ValueError("差异探针上传内容必须是原始字节")
        data = kwargs.get("data")
        fields = (
            {str(key): str(value) for key, value in data.items()}
            if isinstance(data, dict)
            else {}
        )
        self.calls.append(
            {
                "kind": "upload",
                "method": method,
                "path": path,
                "query": _normalize_query(kwargs.get("params")),
                "body": None,
                "fields": fields,
                "file": {
                    "name": str(filename),
                    "mediaType": str(media_type),
                    "bytes": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                },
            }
        )

    def request_bytes(
        self, method: str, path: str, **kwargs: Any
    ) -> BinaryResponse:
        self.calls.append(
            {
                "kind": "download",
                "method": method,
                "path": path,
                "query": _normalize_query(kwargs.get("params")),
                "body": None,
            }
        )
        if self._fail_requests:
            self._fail()
        return BinaryResponse(
            content="完整二进制😀".encode(),
            media_type="application/octet-stream",
        )

    def login(self, username: str, password: str) -> tuple[dict[str, Any], str]:
        self.calls.append(
            {
                "kind": "login",
                "method": "POST",
                "path": "/api/v1/auth/login",
                "query": {},
                "body": {"username": username},
            }
        )
        if self._fail_requests:
            self._fail()
        return {"id": "parity-user-id", "username": username}, "parity-session"

    def iter_sse(self, task_id: str, last_event_id: str | None = None):
        self.calls.append(
            {
                "kind": "sse",
                "taskId": task_id,
                "lastEventId": last_event_id,
            }
        )
        if self._fail_requests:
            self._fail()
        stream = self._streams.popleft() if self._streams else []
        yield from stream

    def _response(self) -> dict[str, Any]:
        if self._fail_requests:
            self._fail()
        if self._responses:
            value = self._responses.popleft()
            if not isinstance(value, dict):
                raise ValueError("脚本响应必须是 JSON 对象")
            return value
        return {"id": "ok", "nullable": None}


def _normalize_query(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, list[str]] = {}
    for key, item in value.items():
        items = item if isinstance(item, list | tuple) else [item]
        result[str(key)] = ["" if entry is None else str(entry) for entry in items]
    return result


def _dependencies(case: dict[str, Any], api: ProbeApi) -> CliDependencies:
    config = MemoryConfigStore()
    config.save(
        "default",
        ProfileConfig(origin="http://127.0.0.1:8000", username="parity-user"),
    )
    credentials = MemoryCredentialStore()
    credentials.set("default", "http://127.0.0.1:8000", "parity-token")
    now = [0.0]

    def monotonic() -> float:
        return now[0]

    def sleep(seconds: float) -> None:
        now[0] += seconds

    return CliDependencies(
        api_factory=lambda origin, token=None: api,
        config_store=config,
        credential_store=credentials,
        getpass_fn=lambda prompt: "parity-password",
        stdin_isatty=lambda: bool(case.get("tty", False)),
        monotonic_fn=monotonic if case.get("fakeClock") is True else time.monotonic,
        sleep_fn=sleep if case.get("fakeClock") is True else time.sleep,
    )


def _replace_token(value: Any, token: str, replacement: str) -> Any:
    if isinstance(value, str):
        return value.replace(token, replacement)
    if isinstance(value, list):
        return [_replace_token(item, token, replacement) for item in value]
    if isinstance(value, dict):
        return {
            key: _replace_token(item, token, replacement)
            for key, item in value.items()
        }
    return value


def _file_content(specification: Any) -> bytes:
    if not isinstance(specification, dict):
        raise ValueError("差异 fixture 文件定义必须是 JSON 对象")
    content = specification.get("content")
    if not isinstance(content, str):
        raise ValueError("差异 fixture 文件内容必须是字符串")
    encoding = specification.get("encoding")
    if encoding == "utf8":
        return content.encode("utf-8")
    if encoding == "base64":
        return base64.b64decode(content, validate=True)
    raise ValueError("差异 fixture 文件编码只允许 utf8 或 base64")


def _materialize_files(case: dict[str, Any], temporary: Path) -> None:
    files = case.get("files", {})
    if not isinstance(files, dict):
        raise ValueError("差异 fixture files 必须是 JSON 对象")
    for name, specification in files.items():
        if not isinstance(name, str):
            raise ValueError("差异 fixture 文件名必须是字符串")
        target = (temporary / name).resolve()
        if temporary not in target.parents:
            raise ValueError("差异 fixture 文件不能逃逸临时目录")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_file_content(specification))


def _capture_files(case: dict[str, Any], temporary: Path) -> dict[str, Any]:
    names = case.get("captureFiles", [])
    if not isinstance(names, list):
        raise ValueError("差异 fixture captureFiles 必须是数组")
    result: dict[str, Any] = {}
    for name in names:
        if not isinstance(name, str):
            raise ValueError("差异 fixture 捕获文件名必须是字符串")
        target = (temporary / name).resolve()
        if temporary not in target.parents or not target.is_file():
            raise ValueError(f"差异 fixture 预期输出文件不存在：{name}")
        content = target.read_bytes()
        result[name] = {
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
    return result


def _run_case(case: dict[str, Any]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="inkforge-cli-parity-") as directory:
        temporary = Path(directory).resolve()
        expanded = _replace_token(case, "${TMP}", str(temporary))
        if not isinstance(expanded, dict):
            raise ValueError("差异 fixture case 必须是 JSON 对象")
        _materialize_files(expanded, temporary)
        command = expanded["command"]
        arguments = expanded.get("arguments", [])
        payload = expanded.get("payload", {})
        stdout = io.StringIO()
        stderr = io.StringIO()
        api = ProbeApi(expanded)
        exit_code = run(
            [command, *arguments],
            stdin=io.StringIO(json.dumps(payload, ensure_ascii=False)),
            stdout=stdout,
            stderr=stderr,
            dependencies=_dependencies(expanded, api),
        )
        frames = [json.loads(line) for line in stdout.getvalue().splitlines()]
        result = {
            "command": command,
            "exitCode": exit_code,
            "frames": frames,
            "stderr": stderr.getvalue(),
        }
        if expanded.get("captureCalls") is True:
            result["calls"] = api.calls
        if expanded.get("captureFiles") is not None:
            result["files"] = _capture_files(expanded, temporary)
        normalized = _replace_token(result, str(temporary), "${TMP}")
        if not isinstance(normalized, dict):
            raise AssertionError("差异探针结果必须是 JSON 对象")
        return normalized


def main() -> int:
    cases = json.load(sys.stdin)
    if not isinstance(cases, list):
        raise ValueError("差异探针输入必须是数组")
    json.dump(
        [_run_case(case) for case in cases],
        sys.stdout,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
