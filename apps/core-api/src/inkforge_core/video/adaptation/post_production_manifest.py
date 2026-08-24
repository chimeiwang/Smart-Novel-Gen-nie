"""整集导出的不可变内部清单；只保存受控素材键，不保存服务器绝对路径。"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class ExportManifestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FrozenExportAsset(ExportManifestModel):
    assetId: str = Field(min_length=1)
    storageKey: str = Field(min_length=1)
    sha256: Sha256
    mimeType: str = Field(min_length=1, max_length=160)
    durationMs: int | None = Field(default=None, gt=0)


class FrozenExportVideoClip(ExportManifestModel):
    ordinal: int = Field(ge=1)
    shotId: str = Field(min_length=1)
    takeId: str | None = Field(default=None, min_length=1)
    asset: FrozenExportAsset | None = None
    sourceInMs: int | None = Field(default=None, ge=0)
    sourceOutMs: int | None = Field(default=None, gt=0)
    outputDurationMs: int = Field(ge=500, le=120_000)
    transitionAfter: Literal["cut", "fade_black"]
    transitionDurationMs: int = Field(ge=0, le=2_000)


class FrozenExportAudioClip(ExportManifestModel):
    ordinal: int = Field(ge=1)
    trackKind: Literal["dialogue", "narration", "ambience", "sfx", "music"]
    shotId: str | None = Field(default=None, min_length=1)
    asset: FrozenExportAsset
    timelineStartMs: int = Field(ge=0)
    sourceInMs: int = Field(ge=0)
    sourceOutMs: int = Field(gt=0)
    gainMillibels: int = Field(ge=-6_000, le=1_200)
    fadeInMs: int = Field(ge=0, le=10_000)
    fadeOutMs: int = Field(ge=0, le=10_000)


class FrozenExportSubtitleCue(ExportManifestModel):
    ordinal: int = Field(ge=1)
    shotId: str | None = Field(default=None, min_length=1)
    startMs: int = Field(ge=0)
    endMs: int = Field(gt=0)
    speaker: str | None = Field(default=None, max_length=120)
    text: str = Field(min_length=1, max_length=2_000)


class VideoEpisodeExportManifest(ExportManifestModel):
    schemaVersion: Literal["video-episode-export-manifest/1.0"] = (
        "video-episode-export-manifest/1.0"
    )
    adaptationId: str = Field(min_length=1)
    projectId: str = Field(min_length=1)
    novelId: str = Field(min_length=1)
    episodePlanVersionId: str = Field(min_length=1)
    shotPlanVersionId: str = Field(min_length=1)
    episodeNo: int = Field(ge=1)
    editVersionId: str = Field(min_length=1)
    editContentHash: Sha256
    mixVersionId: str = Field(min_length=1)
    mixContentHash: Sha256
    targetAspectRatio: Literal["16:9", "4:3", "1:1", "3:4", "9:16", "21:9"]
    resolution: Literal["720p", "1080p"]
    framesPerSecond: Literal[24, 25, 30]
    burnSubtitles: bool
    totalDurationMs: int = Field(gt=0)
    videoClips: list[FrozenExportVideoClip] = Field(min_length=1, max_length=500)
    audioClips: list[FrozenExportAudioClip] = Field(default_factory=list, max_length=1_000)
    subtitleCues: list[FrozenExportSubtitleCue] = Field(
        default_factory=list,
        max_length=2_000,
    )
