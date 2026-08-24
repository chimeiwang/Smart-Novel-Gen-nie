"""在包含 FFmpeg 的运行镜像内验收抽帧、剪辑、混音和字幕烧录。"""

from __future__ import annotations

import asyncio
import json
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

from inkforge_core.video.adaptation.post_production_manifest import (
    FrozenExportAsset,
    FrozenExportAudioClip,
    FrozenExportSubtitleCue,
    FrozenExportVideoClip,
    VideoEpisodeExportManifest,
)
from inkforge_core.video.adaptation.post_production_media import (
    VideoPostProductionMediaProcessor,
)
from inkforge_core.video.media_probe import VideoMediaProbe
from inkforge_core.video.storage import StoredVideoAsset, VideoAssetStorage


async def _chunks(path: Path) -> AsyncIterator[bytes]:
    with path.open("rb") as source:
        while chunk := await asyncio.to_thread(source.read, 1024 * 1024):
            yield chunk


def _frozen(asset_id: str, stored: StoredVideoAsset, duration_ms: int) -> FrozenExportAsset:
    return FrozenExportAsset(
        assetId=asset_id,
        storageKey=stored.storage_key,
        sha256=stored.sha256,
        mimeType=stored.mime_type,
        durationMs=duration_ms,
    )


async def _generate_fixture_media(
    processor: VideoPostProductionMediaProcessor,
    fixture_dir: Path,
) -> tuple[Path, Path, Path]:
    first = fixture_dir / "first.mp4"
    second = fixture_dir / "second.mp4"
    music = fixture_dir / "music.wav"
    await processor._run(  # noqa: SLF001 - 该脚本专门验收同一个受控执行器
        [
            processor._ffmpeg_path,  # noqa: SLF001
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=360x640:d=1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(first),
        ],
        cwd=fixture_dir,
        error_code="VIDEO_MEDIA_SMOKE_FIXTURE_FAILED",
    )
    await processor._run(  # noqa: SLF001
        [
            processor._ffmpeg_path,  # noqa: SLF001
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=360x640:d=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(second),
        ],
        cwd=fixture_dir,
        error_code="VIDEO_MEDIA_SMOKE_FIXTURE_FAILED",
    )
    await processor._run(  # noqa: SLF001
        [
            processor._ffmpeg_path,  # noqa: SLF001
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=220:duration=2",
            "-c:a",
            "pcm_s16le",
            str(music),
        ],
        cwd=fixture_dir,
        error_code="VIDEO_MEDIA_SMOKE_FIXTURE_FAILED",
    )
    return first, second, music


async def _main() -> None:
    processor = VideoPostProductionMediaProcessor(command_timeout_seconds=120)
    if not processor.readiness.ready:
        raise RuntimeError("运行媒体验收需要 ffmpeg 和 ffprobe")

    with tempfile.TemporaryDirectory(prefix="inkforge-media-smoke-") as temp_dir:
        root = Path(temp_dir)
        fixture_dir = root / "fixtures"
        fixture_dir.mkdir()
        storage = VideoAssetStorage(root / "storage")
        first_path, second_path, music_path = await _generate_fixture_media(
            processor,
            fixture_dir,
        )
        probed_audio_duration_ms = await VideoMediaProbe().probe_duration_ms(music_path)
        if not 1_950 <= probed_audio_duration_ms <= 2_050:
            raise AssertionError("上传音频时长探测结果异常")
        first = await storage.save_stream(
            "project-1", "video-1", "video", _chunks(first_path)
        )
        second = await storage.save_stream(
            "project-1", "video-2", "video", _chunks(second_path)
        )
        music = await storage.save_stream(
            "project-1", "audio-1", "audio", _chunks(music_path)
        )
        extracted = await processor.extract_frame(
            source_path=first.absolute_path,
            expected_sha256=first.sha256,
            timestamp_ms=500,
            storage=storage,
            project_id="project-1",
            asset_id="frame-1",
        )
        if extracted.mime_type != "image/png" or extracted.byte_size <= 0:
            raise AssertionError("抽帧结果不是有效 PNG")

        manifest = VideoEpisodeExportManifest(
            adaptationId="adaptation-1",
            projectId="project-1",
            novelId="novel-1",
            episodePlanVersionId="episode-plan-1",
            shotPlanVersionId="shot-plan-1",
            episodeNo=1,
            editVersionId="edit-1",
            editContentHash="b" * 64,
            mixVersionId="mix-1",
            mixContentHash="c" * 64,
            targetAspectRatio="9:16",
            resolution="720p",
            framesPerSecond=24,
            burnSubtitles=True,
            totalDurationMs=1_800,
            videoClips=[
                FrozenExportVideoClip(
                    ordinal=1,
                    shotId="shot-1",
                    takeId="take-1",
                    asset=_frozen("video-1", first, 1_000),
                    sourceInMs=0,
                    sourceOutMs=900,
                    outputDurationMs=900,
                    transitionAfter="fade_black",
                    transitionDurationMs=150,
                ),
                FrozenExportVideoClip(
                    ordinal=2,
                    shotId="shot-2",
                    takeId="take-2",
                    asset=_frozen("video-2", second, 1_000),
                    sourceInMs=0,
                    sourceOutMs=900,
                    outputDurationMs=900,
                    transitionAfter="cut",
                    transitionDurationMs=0,
                ),
            ],
            audioClips=[
                FrozenExportAudioClip(
                    ordinal=1,
                    trackKind="music",
                    asset=_frozen("audio-1", music, 2_000),
                    timelineStartMs=100,
                    sourceInMs=0,
                    sourceOutMs=1_600,
                    gainMillibels=-1_200,
                    fadeInMs=100,
                    fadeOutMs=100,
                )
            ],
            subtitleCues=[
                FrozenExportSubtitleCue(
                    ordinal=1,
                    shotId="shot-1",
                    startMs=100,
                    endMs=1_500,
                    speaker="林岚",
                    text="这句中文必须烧进最终视频。",
                )
            ],
        )
        rendered = await processor.render_episode(
            manifest=manifest,
            storage=storage,
            asset_id="episode-1",
        )
        probe_text = await processor._run(  # noqa: SLF001
            [
                processor._ffprobe_path,  # noqa: SLF001
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-show_entries",
                "stream=codec_type,width,height",
                "-of",
                "json",
                str(rendered.absolute_path),
            ],
            cwd=rendered.absolute_path.parent,
            error_code="VIDEO_MEDIA_SMOKE_PROBE_FAILED",
            return_stdout=True,
        )
        probe = json.loads(probe_text)
        streams = probe["streams"]
        video = next(stream for stream in streams if stream["codec_type"] == "video")
        if (video["width"], video["height"]) != (720, 1280):
            raise AssertionError("成片分辨率不是预期的 720×1280")
        if not any(stream["codec_type"] == "audio" for stream in streams):
            raise AssertionError("成片缺少音轨")
        duration = float(probe["format"]["duration"])
        if not 1.7 <= duration <= 1.95:
            raise AssertionError(f"成片时长异常：{duration}")
        print(
            json.dumps(
                {
                    "frameMimeType": extracted.mime_type,
                    "frameBytes": extracted.byte_size,
                    "episodeMimeType": rendered.mime_type,
                    "episodeBytes": rendered.byte_size,
                    "durationSeconds": duration,
                    "resolution": "720x1280",
                    "hasAudio": True,
                    "burnedSubtitle": True,
                    "probedAudioDurationMs": probed_audio_duration_ms,
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    asyncio.run(_main())
