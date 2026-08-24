"""后期制作服务对本地抽帧副作用的幂等与提交不确定性保护。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from inkforge_core.video.adaptation.post_production_media import MediaToolReadiness
from inkforge_core.video.adaptation.post_production_repository import TakeFrameSource
from inkforge_core.video.adaptation.post_production_schemas import (
    ExtractTakeFrameRequest,
    PostProductionAssetResponse,
)
from inkforge_core.video.adaptation.post_production_service import (
    VideoPostProductionService,
)
from inkforge_core.video.storage import StoredVideoAsset


def _asset() -> PostProductionAssetResponse:
    return PostProductionAssetResponse(
        id="frame-1",
        name="抽帧",
        modality="image",
        duty="keyframe",
        mimeType="image/png",
        durationMs=None,
        sha256="a" * 64,
        contentUrl="/api/v1/video/assets/frame-1/content",
    )


class _Storage:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def resolve(self, _storage_key: str) -> Path:
        return Path("source.mp4")

    def delete(self, storage_key: str) -> bool:
        self.deleted.append(storage_key)
        return True


class _Media:
    def __init__(self) -> None:
        self.calls = 0

    @property
    def readiness(self) -> MediaToolReadiness:
        return MediaToolReadiness(ffmpeg_available=True, ffprobe_available=True)

    async def extract_frame(self, **_kwargs: object) -> StoredVideoAsset:
        self.calls += 1
        await asyncio.sleep(0)
        return StoredVideoAsset(
            storage_key="project-1/frame-1.png",
            absolute_path=Path("frame-1.png"),
            mime_type="image/png",
            byte_size=10,
            sha256="a" * 64,
        )


class _Repository:
    def __init__(self, *, lose_completion_response: bool = False) -> None:
        self.asset: PostProductionAssetResponse | None = None
        self.completions = 0
        self.lose_completion_response = lose_completion_response

    async def get_extraction_replay(
        self,
        _user_id: str,
        _client_request_id: str,
        _request_hash: str,
    ) -> PostProductionAssetResponse | None:
        return self.asset

    async def get_take_frame_source(
        self,
        _user_id: str,
        _take_id: str,
        _timestamp_ms: int,
    ) -> TakeFrameSource:
        return TakeFrameSource(
            take_id="take-1",
            shot_id="shot-1",
            adaptation_id="adaptation-1",
            project_id="project-1",
            novel_id="novel-1",
            storage_key="project-1/take-1.mp4",
            sha256="b" * 64,
            duration_ms=1_000,
        )

    async def complete_extracted_frame(self, **_kwargs: object) -> PostProductionAssetResponse:
        self.completions += 1
        self.asset = _asset()
        if self.lose_completion_response:
            raise ConnectionError("提交响应丢失")
        return self.asset


def _request() -> ExtractTakeFrameRequest:
    return ExtractTakeFrameRequest(
        clientRequestId="frame-request-0001",
        timestampMs=500,
        name="第一个抽帧",
    )


@pytest.mark.asyncio
async def test_concurrent_identical_extractions_execute_ffmpeg_once() -> None:
    repository = _Repository()
    storage = _Storage()
    media = _Media()
    service = VideoPostProductionService(
        repository,  # type: ignore[arg-type]
        storage,  # type: ignore[arg-type]
        media,  # type: ignore[arg-type]
    )

    first, second = await asyncio.gather(
        service.extract_take_frame("user-1", "take-1", _request()),
        service.extract_take_frame("user-1", "take-1", _request()),
    )

    assert first.id == second.id == "frame-1"
    assert media.calls == 1
    assert repository.completions == 1


@pytest.mark.asyncio
async def test_frame_commit_response_loss_replays_and_preserves_registered_file() -> None:
    repository = _Repository(lose_completion_response=True)
    storage = _Storage()
    media = _Media()
    service = VideoPostProductionService(
        repository,  # type: ignore[arg-type]
        storage,  # type: ignore[arg-type]
        media,  # type: ignore[arg-type]
    )

    result = await service.extract_take_frame("user-1", "take-1", _request())

    assert result.id == "frame-1"
    assert repository.completions == 1
    assert storage.deleted == ["project-1/frame_" + _request_hash_prefix() + ".png"]


def _request_hash_prefix() -> str:
    import hashlib

    request = _request()
    return hashlib.sha256(
        "\x00".join(
            (
                "user-1",
                "take-1",
                request.clientRequestId,
                str(request.timestampMs),
                request.name,
            )
        ).encode()
    ).hexdigest()[:40]
