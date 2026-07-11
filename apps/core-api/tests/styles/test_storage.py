from __future__ import annotations

import asyncio
import os
import stat
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from inkforge_core.config import Settings
from inkforge_core.errors import ApiError
from inkforge_core.styles.storage import (
    MAX_STORAGE_BASENAME_BYTES,
    MAX_UPLOAD_BYTES,
    StyleStorage,
)
from pydantic import ValidationError
from starlette.datastructures import Headers, UploadFile


class RecordingUpload(UploadFile):
    def __init__(self, payload: bytes, filename: str) -> None:
        super().__init__(BytesIO(payload), filename=filename, headers=Headers())
        self.read_sizes: list[int] = []

    async def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        return await super().read(size)


@pytest.mark.parametrize("uploads_root", ["", "relative", "../data", "data/uploads"])
def test_upload_root_must_be_an_absolute_container_or_host_path(uploads_root: str) -> None:
    with pytest.raises(ValidationError):
        Settings(environment="test", uploads_root=uploads_root)


@pytest.mark.asyncio
async def test_upload_streams_utf8_and_counts_non_whitespace(tmp_path: Path) -> None:
    upload = RecordingUpload("甲 乙\n丙".encode(), " 章 节.TXT ")
    stored = await StyleStorage(tmp_path).save("style-1", "ref-1", upload)
    assert stored.filename == "章 节.TXT"
    assert stored.char_count == 3
    assert stored.database_path == "/app/uploads/styles/style-1/ref-1_章 节.TXT"
    assert stored.absolute_path.read_text(encoding="utf-8") == "甲 乙\n丙"
    assert upload.read_sizes and set(upload.read_sizes) == {1024 * 1024}


@pytest.mark.asyncio
async def test_upload_handles_operating_system_short_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_write = os.write

    def short_write(descriptor: int, payload: bytes) -> int:
        limited = payload[: max(1, len(payload) // 2)]
        return original_write(descriptor, limited)

    monkeypatch.setattr(os, "write", short_write)
    payload = ("甲乙丙丁" * 1000).encode()
    stored = await StyleStorage(tmp_path).save(
        "style-1", "ref-1", RecordingUpload(payload, "作品.txt")
    )
    assert stored.absolute_path.read_bytes() == payload


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "filename",
    [
        "作品.txt.exe",
        "作品.md",
        "作品",
        ".txt",
        " .txt ",
        "作品.TXT.bak",
        "作品txt",
        "作品.csv",
        "作品.txt/附件",
        "作品.txt\\附件",
    ],
)
async def test_upload_rejects_non_txt_and_double_extension(tmp_path: Path, filename: str) -> None:
    with pytest.raises(ApiError) as caught:
        await StyleStorage(tmp_path).save("style-1", "ref-1", RecordingUpload(b"text", filename))
    assert caught.value.code == "STYLE_REFERENCE_TYPE_INVALID"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [b"", b" ", b"\r\n\t", "\u3000\n\t".encode(), "\u00a0\r\n".encode()],
)
async def test_upload_rejects_empty_or_whitespace_only_content(
    tmp_path: Path, payload: bytes
) -> None:
    with pytest.raises(ApiError) as caught:
        await StyleStorage(tmp_path).save("style-1", "ref-1", RecordingUpload(payload, "作品.txt"))
    assert caught.value.code == "STYLE_REFERENCE_EMPTY"
    assert not await asyncio.to_thread(lambda: list(tmp_path.rglob("*.txt")))


@pytest.mark.asyncio
async def test_upload_rejects_invalid_utf8_and_removes_partial_file(tmp_path: Path) -> None:
    with pytest.raises(ApiError) as caught:
        await StyleStorage(tmp_path).save(
            "style-1", "ref-1", RecordingUpload(b"valid\xff", "作品.txt")
        )
    assert caught.value.code == "STYLE_REFERENCE_ENCODING_INVALID"
    assert not await asyncio.to_thread(lambda: list(tmp_path.rglob("*.txt")))


@pytest.mark.asyncio
async def test_upload_accepts_exact_limit_and_rejects_one_byte_over(tmp_path: Path) -> None:
    storage = StyleStorage(tmp_path)
    accepted = await storage.save(
        "style-1", "ref-ok", RecordingUpload(b"a" * MAX_UPLOAD_BYTES, "a.txt")
    )
    assert accepted.absolute_path.stat().st_size == MAX_UPLOAD_BYTES
    with pytest.raises(ApiError) as caught:
        await storage.save(
            "style-1", "ref-big", RecordingUpload(b"a" * (MAX_UPLOAD_BYTES + 1), "b.txt")
        )
    assert caught.value.code == "STYLE_REFERENCE_TOO_LARGE"
    assert not (tmp_path / "styles" / "style-1" / "ref-big_b.txt").exists()


@pytest.mark.asyncio
async def test_filename_is_normalized_without_path_or_control_characters(tmp_path: Path) -> None:
    decomposed = "e\u0301\x00/..\\章节.txt"
    stored = await StyleStorage(tmp_path).save(
        "style-1", "ref-1", RecordingUpload("正文".encode(), decomposed)
    )
    assert stored.filename == "é__.._章节.txt"
    assert stored.absolute_path.parent == tmp_path / "styles" / "style-1"
    assert "\x00" not in stored.absolute_path.name


@pytest.mark.asyncio
async def test_long_unicode_filename_is_bounded_and_keeps_txt_extension(tmp_path: Path) -> None:
    stored = await StyleStorage(tmp_path).save(
        "style-1",
        "ref-1",
        RecordingUpload("正文".encode(), f"{'章' * 300}.txt"),
    )
    assert len(stored.absolute_path.name.encode()) <= MAX_STORAGE_BASENAME_BYTES
    assert stored.filename.endswith(".txt")


@pytest.mark.asyncio
async def test_exclusive_create_rejects_collision_without_overwriting(tmp_path: Path) -> None:
    storage = StyleStorage(tmp_path)
    first = await storage.save(
        "style-1", "ref-1", RecordingUpload("原文".encode(), "作品.txt")
    )
    with pytest.raises(ApiError) as caught:
        await storage.save(
            "style-1", "ref-1", RecordingUpload("篡改".encode(), "作品.txt")
        )
    assert caught.value.code == "STYLE_REFERENCE_FILE_CONFLICT"
    assert first.absolute_path.read_text(encoding="utf-8") == "原文"


@pytest.mark.parametrize(
    "database_path",
    [
        "C:\\repo\\uploads\\styles\\style-1\\ref-1_作品.txt",
        "D:/inkForge/uploads/styles/style-1/ref-1_作品.txt",
        "/app/uploads/styles/style-1/ref-1_作品.txt",
        "/data/uploads/styles/style-1/ref-1_作品.txt",
        "uploads/styles/style-1/ref-1_作品.txt",
    ],
)
def test_resolve_maps_valid_legacy_upload_suffix(tmp_path: Path, database_path: str) -> None:
    expected = tmp_path / "styles" / "style-1" / "ref-1_作品.txt"
    assert StyleStorage(tmp_path).resolve(database_path) == expected


@pytest.mark.parametrize(
    "database_path",
    [
        "../uploads/styles/style-1/../../secret.txt",
        "/etc/passwd",
        "C:\\secret.txt",
        "uploads\\styles\\style-1\\..\\secret.txt",
        "uploads/styles/style-1/a\x00.txt",
        "uploads/styles/../style-1/secret.txt",
        "uploads/styles/style-1/sub/secret.txt",
        "uploads/styles//secret.txt",
        "uploads/styles/style 1/secret.txt",
        "uploads/styles/style-1/../ref.txt",
        "notuploads/styles/style-1/ref.txt",
        "uploads/styles/style-1",
    ],
)
def test_resolve_rejects_invalid_or_deceptive_path(tmp_path: Path, database_path: str) -> None:
    with pytest.raises(ApiError):
        StyleStorage(tmp_path).resolve(database_path)


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="当前平台不支持符号链接")
def test_resolve_and_delete_reject_parent_or_file_symlink(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    styles = tmp_path / "styles"
    styles.mkdir()
    try:
        (styles / "style-1").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("当前权限不允许创建符号链接")
    storage = StyleStorage(tmp_path)
    with pytest.raises(ApiError):
        storage.resolve("/app/uploads/styles/style-1/secret.txt")
    assert storage.delete("/app/uploads/styles/style-1/secret.txt") is False
    assert (outside / "secret.txt").exists()


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="当前平台不支持符号链接")
def test_resolve_and_delete_reject_file_symlink(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside-file.txt"
    outside.write_text("secret", encoding="utf-8")
    target = tmp_path / "styles" / "style-1" / "ref-1_a.txt"
    target.parent.mkdir(parents=True)
    try:
        target.symlink_to(outside)
    except OSError:
        pytest.skip("当前权限不允许创建符号链接")
    storage = StyleStorage(tmp_path)
    with pytest.raises(ApiError):
        storage.resolve("/app/uploads/styles/style-1/ref-1_a.txt")
    assert storage.delete("/app/uploads/styles/style-1/ref-1_a.txt") is False
    assert outside.exists()


@pytest.mark.parametrize("symlink_part", ["parent", "file"])
def test_symlink_metadata_is_rejected_without_platform_symlink_permission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    symlink_part: str,
) -> None:
    target = tmp_path / "styles" / "style-1" / "ref-1_a.txt"
    target.parent.mkdir(parents=True)
    target.write_text("keep", encoding="utf-8")
    simulated = target.parent if symlink_part == "parent" else target
    path_type = type(target)
    original_lstat = path_type.lstat

    def fake_lstat(self):
        if self == simulated:
            return SimpleNamespace(st_mode=stat.S_IFLNK)
        return original_lstat(self)

    monkeypatch.setattr(path_type, "lstat", fake_lstat)
    storage = StyleStorage(tmp_path)
    with pytest.raises(ApiError):
        storage.resolve("/app/uploads/styles/style-1/ref-1_a.txt")
    assert storage.delete("/app/uploads/styles/style-1/ref-1_a.txt") is False
    assert target.exists()


def test_delete_is_best_effort_but_never_unlinks_outside_root(tmp_path: Path) -> None:
    storage = StyleStorage(tmp_path)
    target = tmp_path / "styles" / "style-1" / "ref-1_a.txt"
    target.parent.mkdir(parents=True)
    target.write_text("a", encoding="utf-8")
    assert storage.delete("/app/uploads/styles/style-1/ref-1_a.txt") is True
    assert not target.exists()
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("keep", encoding="utf-8")
    assert storage.delete(str(outside)) is False
    assert outside.exists()
