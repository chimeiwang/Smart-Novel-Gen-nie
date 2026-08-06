from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict


class FileDescriptor(TypedDict):
    path: str
    bytes: int
    sha256: str
    mediaType: str


class LegacyFileDescriptor(TypedDict):
    path: str
    contentHash: str
    byteLength: int
    charCount: int


@dataclass(frozen=True, slots=True)
class _WrittenBytes:
    path: str
    bytes: int
    sha256: str


def read_utf8_text_exact(path: str | Path) -> str:
    return Path(path).read_bytes().decode("utf-8")


def atomic_write_bytes(target: Path, payload: bytes) -> None:
    resolved_target = target.expanduser().resolve()
    resolved_target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=resolved_target.parent,
            prefix=f".{resolved_target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, resolved_target)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def atomic_write_text(path: str | Path, content: str) -> None:
    atomic_write_bytes(Path(path), content.encode("utf-8"))


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def _write_payload(path: str | Path, payload: bytes) -> _WrittenBytes:
    target = Path(path).expanduser().resolve()
    atomic_write_bytes(target, payload)
    return _WrittenBytes(
        path=str(target),
        bytes=len(payload),
        sha256=sha256_bytes(payload),
    )


def write_bytes(
    output_file: str | Path,
    payload: bytes,
    media_type: str,
) -> FileDescriptor:
    written = _write_payload(output_file, payload)
    return {
        "path": written.path,
        "bytes": written.bytes,
        "sha256": written.sha256,
        "mediaType": media_type,
    }


def write_large_result(path: str | Path, content: str) -> LegacyFileDescriptor:
    payload = content.encode("utf-8")
    written = _write_payload(path, payload)
    return {
        "path": written.path,
        "contentHash": written.sha256,
        "byteLength": written.bytes,
        "charCount": len(content),
    }
