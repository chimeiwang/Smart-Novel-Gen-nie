#!/usr/bin/env python3
"""以稳定文件描述符读取 GitHub API 信任证据。"""

from __future__ import annotations

import os
import stat
from pathlib import Path

MAX_GITHUB_API_EVIDENCE_BYTES = 1_048_576


def _fingerprint(value: os.stat_result) -> tuple[int, int, int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_uid,
        value.st_size,
        value.st_mode,
        value.st_mtime_ns,
        value.st_ctime_ns,
        value.st_nlink,
    )


def read_regular(
    path: Path,
    label: str,
    *,
    error_type: type[Exception],
    private: bool = False,
    max_bytes: int = MAX_GITHUB_API_EVIDENCE_BYTES,
) -> bytes:
    """拒绝链接、权限漂移和读取期间替换，只返回同一 inode 的完整字节。"""

    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise error_type("当前平台缺少 O_NOFOLLOW，拒绝读取 GitHub API 证据")
    flags = os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise error_type(f"无法安全打开 {label}") from error
    try:
        before = os.fstat(descriptor)
        mode = stat.S_IMODE(before.st_mode)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise error_type(f"{label} 必须是单链接普通文件")
        if before.st_uid != os.geteuid():
            raise error_type(f"{label} owner 必须是当前 runner")
        if before.st_size < 0 or before.st_size > max_bytes:
            raise error_type(f"{label} 超出大小上限")
        if mode & (stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX) or not mode & stat.S_IRUSR:
            raise error_type(f"{label} mode 无效")
        if private and mode & 0o077:
            raise error_type(f"{label} 权限必须禁止 group/other")
        if not private and mode & 0o022:
            raise error_type(f"{label} 不得由 group/other 写入")
        try:
            path_before = os.stat(path, follow_symlinks=False)
        except OSError as error:
            raise error_type(f"{label} 路径在读取前漂移") from error
        if _fingerprint(path_before) != _fingerprint(before):
            raise error_type(f"{label} 路径与已打开文件不一致")

        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise error_type(f"{label} 超出大小上限")
        payload = b"".join(chunks)

        after = os.fstat(descriptor)
        try:
            path_after = os.stat(path, follow_symlinks=False)
        except OSError as error:
            raise error_type(f"{label} 路径在读取后漂移") from error
        if (
            len(
                {
                    _fingerprint(before),
                    _fingerprint(path_before),
                    _fingerprint(after),
                    _fingerprint(path_after),
                }
            )
            != 1
            or len(payload) != before.st_size
        ):
            raise error_type(f"{label} 在读取期间漂移")
        return payload
    except OSError as error:
        raise error_type(f"无法稳定读取 {label}") from error
    finally:
        os.close(descriptor)
