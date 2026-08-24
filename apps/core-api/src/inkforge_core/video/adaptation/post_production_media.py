"""受控 FFmpeg 媒体执行器：抽帧与整集 H.264/AAC 导出。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import tempfile
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

from ..storage import StoredVideoAsset, VideoAssetStorage
from .post_production_manifest import VideoEpisodeExportManifest

_FILE_CHUNK_BYTES = 1024 * 1024
_MAX_EPISODE_EXPORT_BYTES = 1024 * 1024 * 1024


class MediaProcessingError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class MediaToolReadiness:
    ffmpeg_available: bool
    ffprobe_available: bool

    @property
    def ready(self) -> bool:
        return self.ffmpeg_available and self.ffprobe_available


class VideoPostProductionMediaProcessor:
    """只接受数据库冻结的 storageKey，不接受请求提供的服务器路径。"""

    def __init__(
        self,
        *,
        ffmpeg_executable: str = "ffmpeg",
        ffprobe_executable: str = "ffprobe",
        command_timeout_seconds: float = 1_800,
    ) -> None:
        if command_timeout_seconds <= 0:
            raise ValueError("媒体命令超时必须为正数")
        self._ffmpeg = shutil.which(ffmpeg_executable)
        self._ffprobe = shutil.which(ffprobe_executable)
        self._command_timeout_seconds = command_timeout_seconds

    @property
    def readiness(self) -> MediaToolReadiness:
        return MediaToolReadiness(
            ffmpeg_available=self._ffmpeg is not None,
            ffprobe_available=self._ffprobe is not None,
        )

    async def extract_frame(
        self,
        *,
        source_path: Path,
        expected_sha256: str,
        timestamp_ms: int,
        storage: VideoAssetStorage,
        project_id: str,
        asset_id: str,
    ) -> StoredVideoAsset:
        self._require_ready()
        actual_sha256 = await asyncio.to_thread(_sha256_file, source_path)
        if actual_sha256 != expected_sha256:
            raise MediaProcessingError(
                "VIDEO_KEYFRAME_SOURCE_HASH_MISMATCH",
                "来源 Take 文件与数据库冻结哈希不一致",
            )
        with tempfile.TemporaryDirectory(prefix="inkforge-frame-") as temp_dir:
            output = Path(temp_dir) / "frame.png"
            await self._run(
                [
                    self._ffmpeg_path,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-ss",
                    _seconds(timestamp_ms),
                    "-i",
                    str(source_path),
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale=w='min(2048,iw)':h=-2:flags=lanczos",
                    str(output),
                ],
                cwd=Path(temp_dir),
                error_code="VIDEO_KEYFRAME_EXTRACTION_FAILED",
            )
            if not output.is_file() or output.stat().st_size == 0:
                raise MediaProcessingError(
                    "VIDEO_KEYFRAME_EXTRACTION_FAILED",
                    "FFmpeg 未生成关键帧图片",
                )
            return await storage.save_stream(
                project_id,
                asset_id,
                "image",
                _stream_file(output),
            )

    async def render_episode(
        self,
        *,
        manifest: VideoEpisodeExportManifest,
        storage: VideoAssetStorage,
        asset_id: str,
    ) -> StoredVideoAsset:
        self._require_ready()
        video_paths = [
            await self._resolve_and_verify(storage, clip.asset.storageKey, clip.asset.sha256)
            for clip in manifest.videoClips
            if clip.asset is not None
        ]
        audio_paths = [
            await self._resolve_and_verify(storage, clip.asset.storageKey, clip.asset.sha256)
            for clip in manifest.audioClips
        ]
        if len(video_paths) != len(manifest.videoClips):
            raise MediaProcessingError(
                "VIDEO_EXPORT_PLACEHOLDER_REMAINING",
                "导出清单仍包含占位镜头",
            )
        audio_streams = [await self._has_audio_stream(path) for path in video_paths]
        width, height = _output_dimensions(
            manifest.targetAspectRatio,
            manifest.resolution,
        )
        with tempfile.TemporaryDirectory(prefix="inkforge-export-") as temp_dir:
            temp = Path(temp_dir)
            subtitle_path = temp / "subtitles.srt"
            if manifest.burnSubtitles and manifest.subtitleCues:
                subtitle_path.write_text(_srt_text(manifest), encoding="utf-8")
            filter_path = temp / "filters.txt"
            output = temp / "episode.mp4"
            filter_path.write_text(
                _filter_graph(
                    manifest,
                    audio_streams=audio_streams,
                    width=width,
                    height=height,
                    include_subtitles=subtitle_path.exists(),
                ),
                encoding="utf-8",
            )
            command = [
                self._ffmpeg_path,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
            ]
            for path in video_paths:
                command.extend(["-i", str(path)])
            for path in audio_paths:
                command.extend(["-i", str(path)])
            command.extend(
                [
                    "-filter_complex_script",
                    str(filter_path),
                    "-map",
                    "[outv]",
                    "-map",
                    "[outa]",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "medium",
                    "-crf",
                    "20",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-movflags",
                    "+faststart",
                    "-t",
                    _seconds(manifest.totalDurationMs),
                    str(output),
                ]
            )
            await self._run(
                command,
                cwd=temp,
                error_code="VIDEO_EPISODE_EXPORT_FAILED",
            )
            if not output.is_file() or output.stat().st_size == 0:
                raise MediaProcessingError(
                    "VIDEO_EPISODE_EXPORT_FAILED",
                    "FFmpeg 未生成整集视频",
                )
            return await storage.save_stream(
                manifest.projectId,
                asset_id,
                "video",
                _stream_file(output),
                max_bytes=_MAX_EPISODE_EXPORT_BYTES,
            )

    async def _resolve_and_verify(
        self,
        storage: VideoAssetStorage,
        storage_key: str,
        expected_sha256: str,
    ) -> Path:
        path = storage.resolve(storage_key)
        if not path.is_file():
            raise MediaProcessingError(
                "VIDEO_EXPORT_ASSET_MISSING",
                "导出清单引用的受控素材文件不存在",
            )
        actual = await asyncio.to_thread(_sha256_file, path)
        if actual != expected_sha256:
            raise MediaProcessingError(
                "VIDEO_EXPORT_ASSET_HASH_MISMATCH",
                "导出清单引用的素材文件哈希已经变化",
            )
        return path

    async def _has_audio_stream(self, path: Path) -> bool:
        process = await self._run(
            [
                self._ffprobe_path,
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=index",
                "-of",
                "json",
                str(path),
            ],
            cwd=path.parent,
            error_code="VIDEO_EXPORT_PROBE_FAILED",
            return_stdout=True,
        )
        try:
            payload = json.loads(process)
        except json.JSONDecodeError as exc:
            raise MediaProcessingError(
                "VIDEO_EXPORT_PROBE_FAILED",
                "ffprobe 返回了无效结果",
            ) from exc
        streams = payload.get("streams") if isinstance(payload, dict) else None
        return isinstance(streams, list) and bool(streams)

    async def _run(
        self,
        command: list[str],
        *,
        cwd: Path,
        error_code: str,
        return_stdout: bool = False,
    ) -> str:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=cwd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self._command_timeout_seconds,
            )
        except asyncio.CancelledError:
            # Core 退出会取消 worker；必须同步终止 FFmpeg，不能让子进程继续写已无人接管的文件。
            process.kill()
            await process.wait()
            raise
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise MediaProcessingError(error_code, "媒体处理超时，进程已终止") from exc
        if process.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace").strip()
            raise MediaProcessingError(
                error_code,
                detail or f"媒体进程退出码为 {process.returncode}",
            )
        return stdout.decode("utf-8", errors="replace") if return_stdout else ""

    def _require_ready(self) -> None:
        if not self.readiness.ready:
            raise MediaProcessingError(
                "VIDEO_MEDIA_TOOLS_UNAVAILABLE",
                "当前环境缺少 ffmpeg 或 ffprobe",
            )

    @property
    def _ffmpeg_path(self) -> str:
        if self._ffmpeg is None:
            raise MediaProcessingError("VIDEO_MEDIA_TOOLS_UNAVAILABLE", "缺少 ffmpeg")
        return self._ffmpeg

    @property
    def _ffprobe_path(self) -> str:
        if self._ffprobe is None:
            raise MediaProcessingError("VIDEO_MEDIA_TOOLS_UNAVAILABLE", "缺少 ffprobe")
        return self._ffprobe


def _filter_graph(
    manifest: VideoEpisodeExportManifest,
    *,
    audio_streams: list[bool],
    width: int,
    height: int,
    include_subtitles: bool,
) -> str:
    filters: list[str] = []
    concat_inputs: list[str] = []
    for index, (clip, has_audio) in enumerate(
        zip(manifest.videoClips, audio_streams, strict=True)
    ):
        if clip.sourceInMs is None or clip.sourceOutMs is None:
            raise MediaProcessingError(
                "VIDEO_EXPORT_PLACEHOLDER_REMAINING",
                "导出清单包含没有源入出点的镜头",
            )
        duration_seconds = clip.outputDurationMs / 1_000
        video_filters = [
            f"trim=start={_seconds(clip.sourceInMs)}:end={_seconds(clip.sourceOutMs)}",
            "setpts=PTS-STARTPTS",
            f"scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos",
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black",
            f"fps={manifest.framesPerSecond}",
            "setsar=1",
            "format=yuv420p",
        ]
        if index > 0:
            previous = manifest.videoClips[index - 1]
            if previous.transitionAfter == "fade_black":
                video_filters.append(
                    f"fade=t=in:st=0:d={previous.transitionDurationMs / 1_000:.3f}"
                )
        if clip.transitionAfter == "fade_black":
            video_filters.append(
                "fade=t=out:"
                f"st={max(duration_seconds - clip.transitionDurationMs / 1_000, 0):.3f}:"
                f"d={clip.transitionDurationMs / 1_000:.3f}"
            )
        filters.append(f"[{index}:v:0]{','.join(video_filters)}[v{index}]")

        audio_filters = [
            f"atrim=start={_seconds(clip.sourceInMs)}:end={_seconds(clip.sourceOutMs)}",
            "asetpts=PTS-STARTPTS",
            "aresample=48000",
            "aformat=sample_fmts=fltp:channel_layouts=stereo",
        ]
        if index > 0:
            previous = manifest.videoClips[index - 1]
            if previous.transitionAfter == "fade_black":
                audio_filters.append(
                    f"afade=t=in:st=0:d={previous.transitionDurationMs / 1_000:.3f}"
                )
        if clip.transitionAfter == "fade_black":
            audio_filters.append(
                "afade=t=out:"
                f"st={max(duration_seconds - clip.transitionDurationMs / 1_000, 0):.3f}:"
                f"d={clip.transitionDurationMs / 1_000:.3f}"
            )
        if has_audio:
            filters.append(f"[{index}:a:0]{','.join(audio_filters)}[a{index}]")
        else:
            silent_filters = [
                "anullsrc=r=48000:cl=stereo",
                f"atrim=duration={duration_seconds:.3f}",
                "asetpts=PTS-STARTPTS",
            ]
            if index > 0 and manifest.videoClips[index - 1].transitionAfter == "fade_black":
                silent_filters.append(
                    "afade=t=in:st=0:"
                    f"d={manifest.videoClips[index - 1].transitionDurationMs / 1_000:.3f}"
                )
            filters.append(f"{','.join(silent_filters)}[a{index}]")
        concat_inputs.extend([f"[v{index}]", f"[a{index}]"])

    filters.append(
        f"{''.join(concat_inputs)}concat=n={len(manifest.videoClips)}:v=1:a=1[basev][basea]"
    )
    total_seconds = manifest.totalDurationMs / 1_000
    mix_inputs = ["[baseaudio]"]
    filters.append(
        f"[basea]apad,atrim=duration={total_seconds:.3f},asetpts=PTS-STARTPTS[baseaudio]"
    )
    input_offset = len(manifest.videoClips)
    for index, audio_clip in enumerate(manifest.audioClips):
        duration = (audio_clip.sourceOutMs - audio_clip.sourceInMs) / 1_000
        chain = [
            "atrim="
            f"start={_seconds(audio_clip.sourceInMs)}:"
            f"end={_seconds(audio_clip.sourceOutMs)}",
            "asetpts=PTS-STARTPTS",
            "aresample=48000",
            "aformat=sample_fmts=fltp:channel_layouts=stereo",
            f"volume={audio_clip.gainMillibels / 100:.2f}dB",
        ]
        if audio_clip.fadeInMs:
            chain.append(f"afade=t=in:st=0:d={audio_clip.fadeInMs / 1_000:.3f}")
        if audio_clip.fadeOutMs:
            chain.append(
                "afade=t=out:"
                f"st={max(duration - audio_clip.fadeOutMs / 1_000, 0):.3f}:"
                f"d={audio_clip.fadeOutMs / 1_000:.3f}"
            )
        chain.extend(
            [
                f"adelay={audio_clip.timelineStartMs}:all=1",
                "apad",
                f"atrim=duration={total_seconds:.3f}",
            ]
        )
        label = f"extra{index}"
        filters.append(f"[{input_offset + index}:a:0]{','.join(chain)}[{label}]")
        mix_inputs.append(f"[{label}]")
    if len(mix_inputs) == 1:
        filters.append("[baseaudio]anull[outa]")
    else:
        filters.append(
            f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=longest:"
            "dropout_transition=0:normalize=0,alimiter=limit=0.95[outa]"
        )
    if include_subtitles:
        filters.append(
            "[basev]subtitles=subtitles.srt:charenc=UTF-8:"
            "force_style='FontName=Noto Sans CJK SC,FontSize=22,"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H80000000,BorderStyle=1,Outline=2,"
            "Shadow=0,Alignment=2,MarginV=42'[outv]"
        )
    else:
        filters.append("[basev]null[outv]")
    return ";\n".join(filters)


def _srt_text(manifest: VideoEpisodeExportManifest) -> str:
    blocks: list[str] = []
    for index, cue in enumerate(manifest.subtitleCues, start=1):
        text = f"{cue.speaker}：{cue.text}" if cue.speaker else cue.text
        blocks.append(
            f"{index}\n{_srt_time(cue.startMs)} --> {_srt_time(cue.endMs)}\n{text}\n"
        )
    return "\n".join(blocks)


def _srt_time(milliseconds: int) -> str:
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _seconds(milliseconds: int) -> str:
    return f"{milliseconds / 1_000:.3f}"


def _output_dimensions(ratio: str, resolution: str) -> tuple[int, int]:
    left, right = (int(value) for value in ratio.split(":"))
    base = 720 if resolution == "720p" else 1080
    if left >= right:
        height = base
        width = _even(round(base * left / right))
    else:
        width = base
        height = _even(round(base * right / left))
    return width, height


def _even(value: int) -> int:
    return value if value % 2 == 0 else value + 1


async def _stream_file(path: Path) -> AsyncIterator[bytes]:
    with path.open("rb") as source:
        while True:
            chunk = await asyncio.to_thread(source.read, _FILE_CHUNK_BYTES)
            if not chunk:
                return
            yield chunk


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(_FILE_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()
