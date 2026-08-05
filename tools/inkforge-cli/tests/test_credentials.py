from __future__ import annotations

from dataclasses import dataclass

import pytest
from inkforge_cli.credentials import (
    InsecureCredentialBackendError,
    KeyringCredentialStore,
    validate_core_origin,
)


@dataclass
class WinVaultKeyring:
    values: dict[tuple[str, str], str]

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self.values.pop((service, username), None)


WinVaultKeyring.__module__ = "keyring.backends.Windows"


class NullBackend(WinVaultKeyring):
    pass


class AltFileBackend(WinVaultKeyring):
    pass


NullBackend.__module__ = "keyring.backends.null"
AltFileBackend.__module__ = "keyrings.alt.file"


@pytest.fixture(autouse=True)
def _clear_insecure_http_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INKFORGE_CLI_ALLOW_INSECURE_HTTP_ORIGIN", raising=False)


@pytest.mark.parametrize("backend", [NullBackend({}), AltFileBackend({}), object()])
def test_production_store_rejects_every_non_win_vault_backend(backend: object) -> None:
    with pytest.raises(InsecureCredentialBackendError):
        KeyringCredentialStore(backend=backend, platform="win32")


def test_win_vault_store_round_trips_only_the_cookie_value() -> None:
    backend = WinVaultKeyring({})
    store = KeyringCredentialStore(backend=backend, platform="win32")

    store.set("default", "http://127.0.0.1:8000", "secret-cookie")

    assert store.get("default", "http://127.0.0.1:8000") == "secret-cookie"
    assert "secret-cookie" not in repr(store)
    store.delete("default", "http://127.0.0.1:8000")
    assert store.get("default", "http://127.0.0.1:8000") is None


@pytest.mark.parametrize(
    ("origin", "expected"),
    [
        ("http://127.0.0.1:8000/", "http://127.0.0.1:8000"),
        ("http://localhost:8000", "http://localhost:8000"),
        ("http://[::1]:8000", "http://[::1]:8000"),
        ("https://inkforge.example.com/", "https://inkforge.example.com"),
    ],
)
def test_origin_accepts_only_loopback_http_or_https(origin: str, expected: str) -> None:
    assert validate_core_origin(origin) == expected


@pytest.mark.parametrize(
    "origin",
    [
        "http://192.168.1.10:8000",
        "http://inkforge.example.com",
        "https://user:password@inkforge.example.com",
        "https://inkforge.example.com/api",
        "ftp://127.0.0.1",
    ],
)
def test_origin_rejects_insecure_or_ambiguous_values(origin: str) -> None:
    with pytest.raises(ValueError):
        validate_core_origin(origin)


def test_origin_allows_only_the_explicit_remote_http_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "INKFORGE_CLI_ALLOW_INSECURE_HTTP_ORIGIN",
        "http://124.71.85.180",
    )

    assert validate_core_origin("http://124.71.85.180/") == "http://124.71.85.180"
    with pytest.raises(ValueError):
        validate_core_origin("http://124.71.85.181")


@pytest.mark.parametrize(
    "allowed_origin",
    [
        "http://124.71.85.180/api",
        "http://124.71.85.180?unsafe=1",
        "http://*.71.85.180",
        "https://124.71.85.180",
    ],
)
def test_origin_rejects_invalid_insecure_http_allowlist_values(
    monkeypatch: pytest.MonkeyPatch,
    allowed_origin: str,
) -> None:
    monkeypatch.setenv(
        "INKFORGE_CLI_ALLOW_INSECURE_HTTP_ORIGIN",
        allowed_origin,
    )

    with pytest.raises(ValueError):
        validate_core_origin("http://124.71.85.180")
