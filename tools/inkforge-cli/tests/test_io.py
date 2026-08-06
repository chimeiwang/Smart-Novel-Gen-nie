from __future__ import annotations

import hashlib
import importlib
import os
from pathlib import Path
from types import ModuleType

import pytest


def _io_module() -> ModuleType:
    return importlib.import_module("inkforge_cli.io")


def test_read_utf8_text_exact_preserves_large_crlf_and_unicode_tail(
    tmp_path: Path,
) -> None:
    payload = ("甲" * 80_000 + "\r\n中文😀e\u0301尾部\r\n").encode("utf-8")
    source = tmp_path / "chapter.txt"
    source.write_bytes(payload)

    value = _io_module().read_utf8_text_exact(source)

    assert value.encode("utf-8") == payload
    assert value.endswith("中文😀e\u0301尾部\r\n")


def test_atomic_write_bytes_fsyncs_then_replaces_in_target_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    io_module = _io_module()
    target = tmp_path / "nested" / "result.bin"
    payload = b"old\r\nnew\x00tail"
    calls: list[tuple[str, object, object | None]] = []
    real_fsync = os.fsync
    real_replace = os.replace

    def recording_fsync(descriptor: int) -> None:
        calls.append(("fsync", descriptor, None))
        real_fsync(descriptor)

    def recording_replace(source: str | bytes, destination: str | bytes) -> None:
        calls.append(("replace", source, destination))
        assert Path(source).parent == target.parent
        real_replace(source, destination)

    monkeypatch.setattr(io_module.os, "fsync", recording_fsync)
    monkeypatch.setattr(io_module.os, "replace", recording_replace)

    io_module.atomic_write_bytes(target, payload)

    assert target.read_bytes() == payload
    assert [name for name, _, _ in calls] == ["fsync", "replace"]
    assert not list(target.parent.glob(f".{target.name}.*.tmp"))


def test_atomic_write_bytes_cleans_temporary_file_when_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    io_module = _io_module()
    target = tmp_path / "result.bin"

    def fail_replace(source: str | bytes, destination: str | bytes) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(io_module.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        io_module.atomic_write_bytes(target, b"payload")

    assert not target.exists()
    assert not list(tmp_path.glob(f".{target.name}.*.tmp"))


def test_write_bytes_returns_long_file_descriptor_for_exact_payload(
    tmp_path: Path,
) -> None:
    payload = ("正文\r\n" + "乙" * 80_000 + "😀e\u0301").encode("utf-8")
    target = tmp_path / "chapter.txt"

    descriptor = _io_module().write_bytes(
        target,
        payload,
        "text/plain; charset=utf-8",
    )

    assert target.read_bytes() == payload
    assert descriptor == {
        "path": str(target.resolve()),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "mediaType": "text/plain; charset=utf-8",
    }
