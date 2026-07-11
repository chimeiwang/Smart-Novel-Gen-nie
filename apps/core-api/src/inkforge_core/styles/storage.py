from __future__ import annotations

import asyncio
import codecs
import logging
import os
import re
import stat
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from fastapi import UploadFile

from ..errors import ApiError

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024
MAX_STORAGE_BASENAME_BYTES = 240
_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_LEGACY_SUFFIX = re.compile(r"(?:^|/)uploads/styles/(.+)$", re.IGNORECASE)
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StoredStyleReference:
    filename: str
    absolute_path: Path
    database_path: str
    char_count: int


class StyleStorage:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).absolute()

    async def save(
        self,
        style_id: str,
        reference_id: str,
        upload: UploadFile,
    ) -> StoredStyleReference:
        self._validate_id(style_id)
        self._validate_id(reference_id)
        filename_budget = MAX_STORAGE_BASENAME_BYTES - len(reference_id.encode("utf-8")) - 1
        filename = self._sanitize_filename(upload.filename or "", filename_budget)
        parent = self._root / "styles" / style_id
        self._secure_mkdir(parent)
        target = parent / f"{reference_id}_{filename}"
        descriptor: int | None = None
        created = False
        try:
            descriptor = self._open_exclusive(target)
            created = True
            decoder = codecs.getincrementaldecoder("utf-8")("strict")
            size = 0
            char_count = 0
            while True:
                chunk = await upload.read(UPLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise self._error(413, "STYLE_REFERENCE_TOO_LARGE", "文件不能超过 50 MiB")
                try:
                    decoded = decoder.decode(chunk, final=False)
                except UnicodeDecodeError as exc:
                    raise self._error(
                        422,
                        "STYLE_REFERENCE_ENCODING_INVALID",
                        "文件必须使用严格 UTF-8 编码",
                    ) from exc
                char_count += sum(not character.isspace() for character in decoded)
                await asyncio.to_thread(self._write_all, descriptor, chunk)
            try:
                tail = decoder.decode(b"", final=True)
            except UnicodeDecodeError as exc:
                raise self._error(
                    422,
                    "STYLE_REFERENCE_ENCODING_INVALID",
                    "文件必须使用严格 UTF-8 编码",
                ) from exc
            char_count += sum(not character.isspace() for character in tail)
            if char_count == 0:
                raise self._error(422, "STYLE_REFERENCE_EMPTY", "文件内容不能为空")
        except Exception:
            if descriptor is not None:
                os.close(descriptor)
                descriptor = None
            if created:
                try:
                    self._safe_unlink(target)
                except OSError:
                    logger.warning(
                        "清理未完成的文风文件失败",
                        extra={"code": "STYLE_FILE_CLEANUP_FAILED"},
                    )
            raise
        finally:
            if descriptor is not None:
                os.close(descriptor)
        relative = PurePosixPath("styles", style_id, target.name)
        return StoredStyleReference(
            filename=filename,
            absolute_path=target,
            database_path=f"/app/uploads/{relative.as_posix()}",
            char_count=char_count,
        )

    def resolve(self, database_path: str) -> Path:
        if "\x00" in database_path:
            raise self._path_error()
        normalized = database_path.replace("\\", "/")
        match = _LEGACY_SUFFIX.search(normalized)
        if match is None:
            raise self._path_error()
        suffix = PurePosixPath(match.group(1))
        parts = suffix.parts
        if len(parts) != 2 or any(part in {"", ".", ".."} for part in parts):
            raise self._path_error()
        self._validate_id(parts[0])
        if "/" in parts[1] or "\\" in parts[1]:
            raise self._path_error()
        candidate = self._root / "styles" / parts[0] / parts[1]
        self._assert_root_containment(candidate)
        self._reject_symlinks(candidate)
        return candidate

    def delete(self, database_path: str) -> bool:
        try:
            target = self.resolve(database_path)
            if not target.exists():
                return False
            self._safe_unlink(target)
            return True
        except (ApiError, OSError):
            logger.warning("文风文件安全清理未执行", extra={"code": "STYLE_FILE_DELETE_SKIPPED"})
            return False

    def _secure_mkdir(self, target: Path) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        self._reject_symlinks(self._root)
        current = self._root
        for part in target.relative_to(self._root).parts:
            current /= part
            try:
                current.mkdir()
            except FileExistsError:
                pass
            info = current.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise self._path_error()

    def _open_exclusive(self, target: Path) -> int:
        self._assert_root_containment(target)
        self._reject_symlinks(target.parent)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            return os.open(target, flags, 0o600)
        except FileExistsError as exc:
            raise self._error(409, "STYLE_REFERENCE_FILE_CONFLICT", "参考资料文件名冲突") from exc

    @staticmethod
    def _write_all(descriptor: int, payload: bytes) -> None:
        view = memoryview(payload)
        offset = 0
        while offset < len(view):
            written = os.write(descriptor, view[offset:])
            if written <= 0:
                raise OSError("文风文件写入未取得进展")
            offset += written

    def _safe_unlink(self, target: Path) -> None:
        self._assert_root_containment(target)
        self._reject_symlinks(target)
        target.unlink(missing_ok=True)

    def _reject_symlinks(self, target: Path) -> None:
        self._assert_root_containment(target)
        current = self._root
        if current.exists() and stat.S_ISLNK(current.lstat().st_mode):
            raise self._path_error()
        try:
            relative_parts = target.relative_to(self._root).parts
        except ValueError as exc:
            raise self._path_error() from exc
        for part in relative_parts:
            current /= part
            if not current.exists() and not current.is_symlink():
                continue
            if stat.S_ISLNK(current.lstat().st_mode):
                raise self._path_error()

    def _assert_root_containment(self, target: Path) -> None:
        try:
            target.absolute().relative_to(self._root)
        except ValueError as exc:
            raise self._path_error() from exc

    @staticmethod
    def _validate_id(value: str) -> None:
        if _ID_PATTERN.fullmatch(value) is None:
            raise StyleStorage._path_error()

    @staticmethod
    def _sanitize_filename(value: str, max_bytes: int) -> str:
        normalized = unicodedata.normalize("NFC", value.strip())
        path_name = normalized.replace("/", "_").replace("\\", "_")
        cleaned = "".join(
            "_" if unicodedata.category(character).startswith("C") else character
            for character in path_name
        )
        name = PurePosixPath(cleaned).name
        if not name.casefold().endswith(".txt") or not name[:-4].strip(" ._"):
            raise StyleStorage._error(
                422,
                "STYLE_REFERENCE_TYPE_INVALID",
                "只允许上传扩展名为 .txt 的文件",
            )
        suffix = name[-4:]
        stem = name[:-4]
        byte_budget = max_bytes - len(suffix.encode("utf-8"))
        kept: list[str] = []
        used_bytes = 0
        for character in stem:
            character_bytes = len(character.encode("utf-8"))
            if used_bytes + character_bytes > byte_budget:
                break
            kept.append(character)
            used_bytes += character_bytes
        bounded_stem = "".join(kept)
        if not bounded_stem.strip(" ._"):
            raise StyleStorage._error(
                422,
                "STYLE_REFERENCE_NAME_TOO_LONG",
                "参考资料文件名过长",
            )
        return f"{bounded_stem}{suffix}"

    @staticmethod
    def _path_error() -> ApiError:
        return StyleStorage._error(422, "STYLE_STORAGE_PATH_INVALID", "文风文件路径无效")

    @staticmethod
    def _error(status_code: int, code: str, message: str) -> ApiError:
        return ApiError(status_code=status_code, code=code, message=message)
