from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .files import atomic_write_text


@dataclass(frozen=True, slots=True)
class ProfileConfig:
    origin: str
    username: str


class ConfigStore(Protocol):
    def get(self, profile: str) -> ProfileConfig | None: ...

    def save(self, profile: str, config: ProfileConfig) -> None: ...

    def delete(self, profile: str) -> None: ...


class MemoryConfigStore:
    def __init__(self) -> None:
        self._profiles: dict[str, ProfileConfig] = {}

    def get(self, profile: str) -> ProfileConfig | None:
        return self._profiles.get(profile)

    def save(self, profile: str, config: ProfileConfig) -> None:
        self._profiles[profile] = config

    def delete(self, profile: str) -> None:
        self._profiles.pop(profile, None)


class JsonConfigStore:
    """只保存服务地址和用户名，凭据始终交给 Windows Credential Manager。"""

    def __init__(self, path: Path | None = None) -> None:
        self.path = (path or self.default_path()).resolve()

    @staticmethod
    def default_path() -> Path:
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "InkForge" / "cli" / "config.json"
        return Path.home() / ".config" / "inkforge" / "cli" / "config.json"

    def _read(self) -> dict[str, object]:
        if not self.path.exists():
            return {"schemaVersion": 1, "profiles": {}}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {"schemaVersion": 1, "profiles": {}}

    def get(self, profile: str) -> ProfileConfig | None:
        profiles = self._read().get("profiles")
        if not isinstance(profiles, dict):
            return None
        raw = profiles.get(profile)
        if not isinstance(raw, dict):
            return None
        origin = raw.get("origin")
        username = raw.get("username")
        if not isinstance(origin, str) or not isinstance(username, str):
            return None
        return ProfileConfig(origin=origin, username=username)

    def save(self, profile: str, config: ProfileConfig) -> None:
        data = self._read()
        profiles = data.get("profiles")
        if not isinstance(profiles, dict):
            profiles = {}
        profiles[profile] = {"origin": config.origin, "username": config.username}
        data = {"schemaVersion": 1, "profiles": profiles}
        atomic_write_text(
            self.path,
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        )

    def delete(self, profile: str) -> None:
        data = self._read()
        profiles = data.get("profiles")
        if not isinstance(profiles, dict) or profile not in profiles:
            return
        del profiles[profile]
        atomic_write_text(
            self.path,
            json.dumps(
                {"schemaVersion": 1, "profiles": profiles},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
        )
