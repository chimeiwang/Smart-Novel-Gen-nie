from __future__ import annotations

import hashlib
import sys
from typing import Any, Protocol
from urllib.parse import urlsplit


class CredentialStore(Protocol):
    def get(self, profile: str, origin: str) -> str | None: ...

    def set(self, profile: str, origin: str, token: str) -> None: ...

    def delete(self, profile: str, origin: str) -> None: ...


class InsecureCredentialBackendError(RuntimeError):
    pass


class KeyringCredentialStore:
    """只允许 Windows 凭据管理器，绝不回退到明文或第三方文件后端。"""

    def __init__(
        self,
        *,
        backend: Any | None = None,
        platform: str | None = None,
    ) -> None:
        actual_platform = platform or sys.platform
        if backend is None:
            import keyring

            backend = keyring.get_keyring()

        backend_type = type(backend)
        if (
            actual_platform != "win32"
            or backend_type.__module__ != "keyring.backends.Windows"
            or backend_type.__name__ != "WinVaultKeyring"
        ):
            raise InsecureCredentialBackendError(
                "生产 CLI 仅允许使用 Windows Credential Manager 的 WinVaultKeyring"
            )
        self._backend = backend

    @staticmethod
    def _key(profile: str, origin: str) -> tuple[str, str]:
        normalized = validate_core_origin(origin)
        origin_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        return f"InkForge CLI/{origin_hash}", f"inkforge-token:{profile}"

    def get(self, profile: str, origin: str) -> str | None:
        service, username = self._key(profile, origin)
        value = self._backend.get_password(service, username)
        return value if isinstance(value, str) else None

    def set(self, profile: str, origin: str, token: str) -> None:
        service, username = self._key(profile, origin)
        self._backend.set_password(service, username, token)

    def delete(self, profile: str, origin: str) -> None:
        service, username = self._key(profile, origin)
        self._backend.delete_password(service, username)


class MemoryCredentialStore:
    def __init__(self) -> None:
        self._values: dict[tuple[str, str], str] = {}

    def get(self, profile: str, origin: str) -> str | None:
        return self._values.get((profile, validate_core_origin(origin)))

    def set(self, profile: str, origin: str, token: str) -> None:
        self._values[(profile, validate_core_origin(origin))] = token

    def delete(self, profile: str, origin: str) -> None:
        self._values.pop((profile, validate_core_origin(origin)), None)


def validate_core_origin(origin: str) -> str:
    if not origin or origin != origin.strip():
        raise ValueError("Core API 地址不能为空或包含首尾空白")

    parsed = urlsplit(origin)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Core API 仅支持 HTTP 或 HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Core API 地址不得包含用户信息")
    if not parsed.hostname:
        raise ValueError("Core API 地址缺少主机名")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("Core API 地址只能包含 origin，不得包含路径、查询或片段")

    hostname = parsed.hostname.lower()
    if parsed.scheme == "http" and hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("HTTP 仅允许连接本机回环地址，远程地址必须使用 HTTPS")

    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Core API 端口无效") from exc
    rendered_host = f"[{hostname}]" if ":" in hostname else hostname
    rendered_port = f":{port}" if port is not None else ""
    return f"{parsed.scheme}://{rendered_host}{rendered_port}"
