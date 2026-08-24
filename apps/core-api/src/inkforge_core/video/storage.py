"""视频素材的独立流式文件存储与媒体魔数校验。"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import stat
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from fastapi import UploadFile

from ..errors import ApiError

_CHUNK_BYTES = 1024 * 1024
_MEDIA_SNIFF_BYTES = 12
_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_MAX_BYTES = {
    "image": 30 * 1024 * 1024,
    "video": 200 * 1024 * 1024,
    # 两到三分钟的无损 WAV 会明显超过 15 MiB；后期音轨保留 100 MiB 上限。
    "audio": 100 * 1024 * 1024,
}
_MAX_INTERNAL_STREAM_BYTES = 2 * 1024 * 1024 * 1024
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StoredVideoAsset:
    """数据库持久化所需的文件事实。"""

    storage_key: str
    absolute_path: Path
    mime_type: str
    byte_size: int
    sha256: str


class VideoAssetStorage:
    """以项目和素材 ID 定位文件，拒绝路径穿越和符号链接。"""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).absolute() / "video-assets"

    async def save(
        self,
        project_id: str,
        asset_id: str,
        modality: str,
        upload: UploadFile,
    ) -> StoredVideoAsset:
        """流式保存文件，并在写入过程中计算完整哈希和大小。"""

        self._validate_id(project_id)
        self._validate_id(asset_id)
        if modality not in _MAX_BYTES:
            raise self._error(422, "VIDEO_ASSET_MODALITY_INVALID", "素材模态无效")
        first_chunk = await upload.read(_CHUNK_BYTES)
        if not first_chunk:
            raise self._error(422, "VIDEO_ASSET_EMPTY", "素材文件不能为空")
        detected_modality, mime_type, suffix = self._detect_media(first_chunk)
        if detected_modality != modality:
            raise self._error(
                422,
                "VIDEO_ASSET_TYPE_MISMATCH",
                "素材文件内容与声明模态不一致",
            )

        parent = self._root / project_id
        self._secure_mkdir(parent)
        target = parent / f"{asset_id}{suffix}"
        descriptor: int | None = None
        created = False
        digest = hashlib.sha256()
        byte_size = 0
        try:
            descriptor = self._open_exclusive(target)
            created = True
            chunk = first_chunk
            while chunk:
                byte_size += len(chunk)
                if byte_size > _MAX_BYTES[modality]:
                    raise self._error(
                        413,
                        "VIDEO_ASSET_TOO_LARGE",
                        f"{modality} 素材超过允许大小",
                    )
                digest.update(chunk)
                await asyncio.to_thread(self._write_all, descriptor, chunk)
                chunk = await upload.read(_CHUNK_BYTES)
        except Exception:
            if descriptor is not None:
                os.close(descriptor)
                descriptor = None
            if created:
                self.delete(PurePosixPath(project_id, target.name).as_posix())
            raise
        finally:
            if descriptor is not None:
                os.close(descriptor)
        return StoredVideoAsset(
            storage_key=PurePosixPath(project_id, target.name).as_posix(),
            absolute_path=target,
            mime_type=mime_type,
            byte_size=byte_size,
            sha256=digest.hexdigest(),
        )

    async def save_stream(
        self,
        project_id: str,
        asset_id: str,
        modality: str,
        chunks: AsyncIterator[bytes],
        *,
        max_bytes: int | None = None,
    ) -> StoredVideoAsset:
        """流式归档供应商结果；与用户上传使用相同魔数、大小和路径护栏。"""

        self._validate_id(project_id)
        self._validate_id(asset_id)
        if modality not in _MAX_BYTES:
            raise self._error(422, "VIDEO_ASSET_MODALITY_INVALID", "素材模态无效")
        byte_limit = _MAX_BYTES[modality] if max_bytes is None else max_bytes
        if byte_limit < _MEDIA_SNIFF_BYTES or byte_limit > _MAX_INTERNAL_STREAM_BYTES:
            raise ValueError("内部媒体流大小上限无效")
        iterator = chunks.__aiter__()
        initial = bytearray()
        while len(initial) < _MEDIA_SNIFF_BYTES:
            try:
                payload = await anext(iterator)
            except StopAsyncIteration:
                break
            if payload:
                initial.extend(payload)
        first_chunk = bytes(initial)
        if not first_chunk:
            raise self._error(422, "VIDEO_ASSET_EMPTY", "素材文件不能为空")
        detected_modality, mime_type, suffix = self._detect_media(first_chunk)
        if detected_modality != modality:
            raise self._error(
                422,
                "VIDEO_ASSET_TYPE_MISMATCH",
                "供应商结果内容与声明模态不一致",
            )

        parent = self._root / project_id
        self._secure_mkdir(parent)
        target = parent / f"{asset_id}{suffix}"
        descriptor: int | None = None
        created = False
        digest = hashlib.sha256()
        byte_size = 0
        try:
            descriptor = self._open_exclusive(target)
            created = True
            async for payload in _with_first(first_chunk, iterator):
                if not payload:
                    continue
                byte_size += len(payload)
                if byte_size > byte_limit:
                    raise self._error(
                        413,
                        "VIDEO_ASSET_TOO_LARGE",
                        f"{modality} 素材超过允许大小",
                    )
                digest.update(payload)
                await asyncio.to_thread(self._write_all, descriptor, payload)
        except Exception:
            if descriptor is not None:
                os.close(descriptor)
                descriptor = None
            if created:
                self.delete(PurePosixPath(project_id, target.name).as_posix())
            raise
        finally:
            if descriptor is not None:
                os.close(descriptor)
        return StoredVideoAsset(
            storage_key=PurePosixPath(project_id, target.name).as_posix(),
            absolute_path=target,
            mime_type=mime_type,
            byte_size=byte_size,
            sha256=digest.hexdigest(),
        )

    def resolve(self, storage_key: str) -> Path:
        """把数据库对象键安全解析为本地绝对路径。"""

        if "\x00" in storage_key or "\\" in storage_key:
            raise self._path_error()
        path = PurePosixPath(storage_key)
        if len(path.parts) != 2 or any(part in {"", ".", ".."} for part in path.parts):
            raise self._path_error()
        self._validate_id(path.parts[0])
        candidate = self._root.joinpath(*path.parts)
        self._assert_root_containment(candidate)
        self._reject_symlinks(candidate)
        return candidate

    def delete(self, storage_key: str) -> bool:
        """只删除解析后仍位于视频素材根目录内的精确文件。"""

        try:
            target = self.resolve(storage_key)
            target.unlink(missing_ok=True)
            return True
        except (ApiError, OSError):
            logger.warning("视频素材安全清理未执行", extra={"code": "VIDEO_FILE_DELETE_SKIPPED"})
            return False

    @staticmethod
    def _detect_media(payload: bytes) -> tuple[str, str, str]:
        """只依据文件魔数识别首版支持的媒体格式。"""

        if payload.startswith(b"\xff\xd8\xff"):
            return "image", "image/jpeg", ".jpg"
        if payload.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image", "image/png", ".png"
        if len(payload) >= 12 and payload[:4] == b"RIFF" and payload[8:12] == b"WEBP":
            return "image", "image/webp", ".webp"
        if len(payload) >= 12 and payload[4:8] == b"ftyp":
            return "video", "video/mp4", ".mp4"
        if len(payload) >= 12 and payload[:4] == b"RIFF" and payload[8:12] == b"WAVE":
            return "audio", "audio/wav", ".wav"
        if payload.startswith(b"ID3") or (
            len(payload) >= 2 and payload[0] == 0xFF and payload[1] & 0xE0 == 0xE0
        ):
            return "audio", "audio/mpeg", ".mp3"
        raise VideoAssetStorage._error(
            422,
            "VIDEO_ASSET_FORMAT_UNSUPPORTED",
            "只支持 JPEG、PNG、WebP、MP4/MOV、WAV 和 MP3",
        )

    def _secure_mkdir(self, target: Path) -> None:
        """逐层建立目录，并拒绝任何已有符号链接。"""

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
        """使用排他创建和 O_NOFOLLOW 防止覆盖及链接攻击。"""

        self._assert_root_containment(target)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            return os.open(target, flags, 0o600)
        except FileExistsError as exc:
            raise self._error(
                409,
                "VIDEO_ASSET_FILE_CONFLICT",
                "素材文件标识冲突",
            ) from exc

    @staticmethod
    def _write_all(descriptor: int, payload: bytes) -> None:
        """处理 os.write 可能发生的部分写入。"""

        view = memoryview(payload)
        offset = 0
        while offset < len(view):
            written = os.write(descriptor, view[offset:])
            if written <= 0:
                raise OSError("视频素材写入未取得进展")
            offset += written

    def _reject_symlinks(self, target: Path) -> None:
        """检查从存储根到目标的每一层路径。"""

        self._assert_root_containment(target)
        current = self._root
        if current.exists() and stat.S_ISLNK(current.lstat().st_mode):
            raise self._path_error()
        for part in target.relative_to(self._root).parts:
            current /= part
            if current.exists() or current.is_symlink():
                if stat.S_ISLNK(current.lstat().st_mode):
                    raise self._path_error()

    def _assert_root_containment(self, target: Path) -> None:
        """目标必须位于视频素材专用目录内。"""

        try:
            target.absolute().relative_to(self._root)
        except ValueError as exc:
            raise self._path_error() from exc

    @staticmethod
    def _validate_id(value: str) -> None:
        """路径片段只能使用系统生成的安全标识。"""

        if _ID_PATTERN.fullmatch(value) is None:
            raise VideoAssetStorage._path_error()

    @staticmethod
    def _path_error() -> ApiError:
        return VideoAssetStorage._error(
            422,
            "VIDEO_STORAGE_PATH_INVALID",
            "视频素材路径无效",
        )

    @staticmethod
    def _error(status_code: int, code: str, message: str) -> ApiError:
        return ApiError(status_code=status_code, code=code, message=message)


async def _with_first(
    first: bytes,
    remaining: AsyncIterator[bytes],
) -> AsyncIterator[bytes]:
    yield first
    async for chunk in remaining:
        yield chunk
