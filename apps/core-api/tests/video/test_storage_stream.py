from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from inkforge_core.errors import ApiError
from inkforge_core.video.storage import VideoAssetStorage


@pytest.mark.asyncio
async def test_provider_stream_uses_same_magic_hash_and_safe_path_guards(tmp_path) -> None:
    storage = VideoAssetStorage(tmp_path)

    async def chunks() -> AsyncIterator[bytes]:
        yield b"\x00\x00\x00\x18ftypmp42"
        yield "完整候选😀".encode()

    stored = await storage.save_stream("project-1", "task-1", "video", chunks())

    assert stored.mime_type == "video/mp4"
    assert stored.byte_size == len(b"\x00\x00\x00\x18ftypmp42") + len("完整候选😀".encode())
    assert storage.resolve(stored.storage_key).read_bytes().endswith("完整候选😀".encode())


@pytest.mark.asyncio
async def test_provider_stream_accumulates_fragmented_magic_header(tmp_path) -> None:
    storage = VideoAssetStorage(tmp_path)
    payloads = [b"\x00", b"\x00\x00", b"\x18f", b"typ", b"mp42", b"video-body"]

    async def chunks() -> AsyncIterator[bytes]:
        for payload in payloads:
            yield payload

    stored = await storage.save_stream("project-1", "task-2", "video", chunks())

    assert stored.mime_type == "video/mp4"
    assert storage.resolve(stored.storage_key).read_bytes() == b"".join(payloads)


@pytest.mark.asyncio
async def test_internal_stream_override_is_bounded_and_cleans_partial_file(tmp_path) -> None:
    storage = VideoAssetStorage(tmp_path)

    async def chunks() -> AsyncIterator[bytes]:
        yield b"\x00\x00\x00\x18ftypmp42"
        yield b"video-body-that-exceeds-the-test-limit"

    with pytest.raises(ApiError) as caught:
        await storage.save_stream(
            "project-1",
            "task-large",
            "video",
            chunks(),
            max_bytes=20,
        )

    assert caught.value.code == "VIDEO_ASSET_TOO_LARGE"
    assert not storage.resolve("project-1/task-large.mp4").exists()
