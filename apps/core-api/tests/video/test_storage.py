"""视频素材存储的格式、哈希和路径安全测试。"""

from __future__ import annotations

import hashlib
from io import BytesIO

import pytest
from fastapi import UploadFile
from inkforge_core.errors import ApiError
from inkforge_core.video.storage import VideoAssetStorage
from starlette.datastructures import Headers


@pytest.mark.asyncio
async def test_saves_png_by_magic_and_returns_full_hash(tmp_path) -> None:
    """文件事实来自内容而不是浏览器声明的 MIME 或扩展名。"""

    payload = b"\x89PNG\r\n\x1a\n" + b"fixture-image-body"
    upload = UploadFile(
        BytesIO(payload),
        filename="伪装成文本.txt",
        headers=Headers({"content-type": "text/plain"}),
    )
    storage = VideoAssetStorage(tmp_path)

    result = await storage.save("project-1", "asset-1", "image", upload)

    assert result.mime_type == "image/png"
    assert result.byte_size == len(payload)
    assert result.sha256 == hashlib.sha256(payload).hexdigest()
    assert result.absolute_path.read_bytes() == payload
    assert storage.resolve(result.storage_key) == result.absolute_path


@pytest.mark.asyncio
async def test_rejects_declared_modality_mismatch(tmp_path) -> None:
    """图片内容不能伪装成视频素材。"""

    upload = UploadFile(BytesIO(b"\xff\xd8\xfffixture"), filename="fake.mp4")
    storage = VideoAssetStorage(tmp_path)

    with pytest.raises(ApiError) as caught:
        await storage.save("project-1", "asset-1", "video", upload)

    assert caught.value.code == "VIDEO_ASSET_TYPE_MISMATCH"


def test_rejects_path_traversal(tmp_path) -> None:
    """数据库对象键也必须经过独立路径校验。"""

    storage = VideoAssetStorage(tmp_path)

    with pytest.raises(ApiError) as caught:
        storage.resolve("../production-secret")

    assert caught.value.code == "VIDEO_STORAGE_PATH_INVALID"
