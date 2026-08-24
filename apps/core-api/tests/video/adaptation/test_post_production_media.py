"""FFmpeg 图构建必须保留完整时间线、声音和字幕决定。"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest
from inkforge_core.video.adaptation.post_production_manifest import (
    FrozenExportAsset,
    FrozenExportAudioClip,
    FrozenExportSubtitleCue,
    FrozenExportVideoClip,
    VideoEpisodeExportManifest,
)
from inkforge_core.video.adaptation.post_production_media import (
    MediaProcessingError,
    VideoPostProductionMediaProcessor,
    _filter_graph,
    _output_dimensions,
    _srt_text,
)
from inkforge_core.video.storage import VideoAssetStorage


def _asset(asset_id: str, mime_type: str) -> FrozenExportAsset:
    return FrozenExportAsset(
        assetId=asset_id,
        storageKey=f"project-1/{asset_id}.mp4",
        sha256="a" * 64,
        mimeType=mime_type,
        durationMs=5_000,
    )


def _manifest() -> VideoEpisodeExportManifest:
    return VideoEpisodeExportManifest(
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
        totalDurationMs=5_000,
        videoClips=[
            FrozenExportVideoClip(
                ordinal=1,
                shotId="shot-1",
                takeId="take-1",
                asset=_asset("video-1", "video/mp4"),
                sourceInMs=500,
                sourceOutMs=3_000,
                outputDurationMs=2_500,
                transitionAfter="fade_black",
                transitionDurationMs=300,
            ),
            FrozenExportVideoClip(
                ordinal=2,
                shotId="shot-2",
                takeId="take-2",
                asset=_asset("video-2", "video/mp4"),
                sourceInMs=0,
                sourceOutMs=2_500,
                outputDurationMs=2_500,
                transitionAfter="cut",
                transitionDurationMs=0,
            ),
        ],
        audioClips=[
            FrozenExportAudioClip(
                ordinal=1,
                trackKind="music",
                asset=_asset("audio-1", "audio/mpeg"),
                timelineStartMs=500,
                sourceInMs=0,
                sourceOutMs=4_000,
                gainMillibels=-600,
                fadeInMs=200,
                fadeOutMs=300,
            )
        ],
        subtitleCues=[
            FrozenExportSubtitleCue(
                ordinal=1,
                shotId="shot-1",
                startMs=200,
                endMs=1_800,
                speaker="林岚",
                text="这句字幕必须完整保留，不能静默截断。",
            )
        ],
    )


def test_filter_graph_contains_trim_fade_concat_mix_and_burned_subtitles() -> None:
    graph = _filter_graph(
        _manifest(),
        audio_streams=[True, False],
        width=720,
        height=1280,
        include_subtitles=True,
    )

    assert "trim=start=0.500:end=3.000" in graph
    assert "fade=t=out" in graph
    assert "anullsrc=r=48000:cl=stereo" in graph
    assert "concat=n=2:v=1:a=1" in graph
    assert "adelay=500:all=1" in graph
    assert "amix=inputs=2" in graph
    assert "subtitles=subtitles.srt" in graph
    assert graph.endswith("[outv]")


def test_srt_and_dimensions_preserve_chinese_text_and_vertical_ratio() -> None:
    manifest = _manifest()
    subtitles = _srt_text(manifest)

    assert "00:00:00,200 --> 00:00:01,800" in subtitles
    assert "林岚：这句字幕必须完整保留，不能静默截断。" in subtitles
    assert _output_dimensions("9:16", "720p") == (720, 1280)
    assert _output_dimensions("21:9", "1080p") == (2520, 1080)


@pytest.mark.asyncio
async def test_extract_frame_rejects_tampered_take_before_ffmpeg(
    tmp_path: Path,
) -> None:
    source = tmp_path / "take.mp4"
    source.write_bytes(b"tampered-take")
    processor = VideoPostProductionMediaProcessor()
    processor._ffmpeg = "/bin/true"  # noqa: SLF001 - 故障注入，不执行外部命令
    processor._ffprobe = "/bin/true"  # noqa: SLF001

    with pytest.raises(MediaProcessingError) as caught:
        await processor.extract_frame(
            source_path=source,
            expected_sha256="a" * 64,
            timestamp_ms=0,
            storage=VideoAssetStorage(tmp_path / "storage"),
            project_id="project-1",
            asset_id="frame-1",
        )

    assert caught.value.code == "VIDEO_KEYFRAME_SOURCE_HASH_MISMATCH"


@pytest.mark.asyncio
async def test_media_command_cancellation_terminates_child_process(tmp_path: Path) -> None:
    processor = VideoPostProductionMediaProcessor()
    pid_path = tmp_path / "child.pid"
    task = asyncio.create_task(
        processor._run(  # noqa: SLF001 - 故障注入验证统一子进程回收
            [
                sys.executable,
                "-c",
                (
                    "import os,time,pathlib;"
                    "pathlib.Path('child.pid').write_text(str(os.getpid()));"
                    "time.sleep(30)"
                ),
            ],
            cwd=tmp_path,
            error_code="VIDEO_MEDIA_TEST_FAILED",
        )
    )
    for _ in range(100):
        if pid_path.exists():
            break
        await asyncio.sleep(0.01)
    assert pid_path.exists()
    child_pid = int(pid_path.read_text())

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)
