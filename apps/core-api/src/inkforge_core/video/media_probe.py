"""上传音视频的受控 ffprobe 时长探测。"""

from __future__ import annotations

import asyncio
import json
import math
import shutil
from pathlib import Path


class VideoMediaProbeError(RuntimeError):
    """媒体元数据无法形成可信数据库事实。"""


class VideoMediaProbe:
    def __init__(
        self,
        *,
        ffprobe_executable: str = "ffprobe",
        timeout_seconds: float = 30,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("媒体探测超时必须为正数")
        self._ffprobe = shutil.which(ffprobe_executable)
        self._timeout_seconds = timeout_seconds

    @property
    def available(self) -> bool:
        return self._ffprobe is not None

    async def probe_duration_ms(self, path: Path) -> int:
        if self._ffprobe is None:
            raise VideoMediaProbeError("当前环境缺少 ffprobe")
        process = await asyncio.create_subprocess_exec(
            self._ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
            cwd=path.parent,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self._timeout_seconds,
            )
        except asyncio.CancelledError:
            process.kill()
            await process.wait()
            raise
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise VideoMediaProbeError("媒体时长探测超时") from exc
        if process.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace").strip()
            raise VideoMediaProbeError(detail or "ffprobe 无法读取媒体时长")
        return _duration_ms_from_probe(stdout)


def _duration_ms_from_probe(payload: bytes) -> int:
    try:
        document = json.loads(payload)
        duration = float(document["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise VideoMediaProbeError("ffprobe 没有返回有效媒体时长") from exc
    if not math.isfinite(duration) or duration <= 0:
        raise VideoMediaProbeError("媒体时长必须为正有限值")
    return max(1, round(duration * 1_000))
