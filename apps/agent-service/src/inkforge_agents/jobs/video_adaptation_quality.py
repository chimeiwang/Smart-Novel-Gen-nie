"""章节镜头候选的确定性电影语法与短视频节奏门禁。"""

from __future__ import annotations

from dataclasses import dataclass

from inkforge_contracts.video_adaptation import (
    ChapterAdaptationPlanCandidate,
    ChapterPacingPreset,
    CinematicShotCandidate,
)


@dataclass(frozen=True, slots=True)
class _PacingLimits:
    minimum_average_ms: int
    maximum_average_ms: int
    slow_shot_threshold_ms: int
    maximum_slow_ratio: float


_PACING_LIMITS: dict[ChapterPacingPreset, _PacingLimits] = {
    "short_drama": _PacingLimits(1_200, 4_800, 6_000, 0.20),
    "cinematic": _PacingLimits(1_500, 7_000, 9_000, 0.35),
    "dialogue_driven": _PacingLimits(1_500, 6_000, 7_000, 0.30),
}
_ESTABLISHING_SCALES = {"extreme_long", "long", "medium", "two_shot"}
_SUPPLEMENTAL_PURPOSES = {
    "establishing",
    "reaction",
    "insert",
    "transition",
    "atmosphere",
}


def validate_cinematic_candidate(
    candidate: ChapterAdaptationPlanCandidate,
    *,
    pacing_preset: ChapterPacingPreset,
    target_episode_seconds: int,
) -> None:
    """拒绝结构合法但产品上仍退化成机械拆句或超长单集的候选。"""

    shots = [
        shot
        for scene in candidate.scenes
        for beat in scene.beats
        for shot in beat.shots
    ]
    if not shots:
        raise ValueError("电影化镜头方案不能为空")
    limits = _PACING_LIMITS[pacing_preset]
    average_ms = sum(shot.timelineDurationMs for shot in shots) / len(shots)
    if not limits.minimum_average_ms <= average_ms <= limits.maximum_average_ms:
        raise ValueError(
            f"{pacing_preset} 平均镜头时长 {average_ms / 1000:.1f}s 不在产品节奏范围内"
        )
    slow_count = sum(
        shot.timelineDurationMs > limits.slow_shot_threshold_ms for shot in shots
    )
    if slow_count / len(shots) > limits.maximum_slow_ratio:
        raise ValueError("慢镜比例过高，短视频节奏会失去推进力")

    for scene in candidate.scenes:
        first_shot = scene.beats[0].shots[0]
        if first_shot.narrativePurpose not in {"establishing", "atmosphere"}:
            raise ValueError(f"场景 {scene.sceneKey} 首镜没有承担空间建立")
        if first_shot.shotScale not in _ESTABLISHING_SCALES:
            raise ValueError(f"场景 {scene.sceneKey} 首镜景别不足以建立空间")
        for beat in scene.beats:
            _validate_beat_shots(beat.shots)

    episode_durations = _episode_durations(candidate, shots)
    maximum_episode_ms = int(target_episode_seconds * 1_500)
    if any(duration > maximum_episode_ms for duration in episode_durations):
        raise ValueError("建议分集后仍存在超过目标时长 150% 的单集")


def _validate_beat_shots(shots: list[CinematicShotCandidate]) -> None:
    for index, shot in enumerate(shots):
        if (
            shot.adaptationType == "supplemental"
            and shot.narrativePurpose not in _SUPPLEMENTAL_PURPOSES
        ):
            raise ValueError(f"补充镜头 {shot.shotKey} 的叙事目的不成立")
        if index == 0:
            continue
        previous = shots[index - 1]
        if (
            _normalized_copy(previous.visualIntent) == _normalized_copy(shot.visualIntent)
            and previous.shotScale == shot.shotScale
            and previous.cameraAngle == shot.cameraAngle
            and previous.cameraMovement == shot.cameraMovement
        ):
            raise ValueError(
                f"相邻镜头 {previous.shotKey}/{shot.shotKey} 的画面与机位重复，缺少切镜价值"
            )


def _episode_durations(
    candidate: ChapterAdaptationPlanCandidate,
    shots: list[CinematicShotCandidate],
) -> list[int]:
    breaks = set(candidate.suggestedEpisodeBreakAfterShotKeys)
    durations: list[int] = []
    current = 0
    for shot in shots:
        current += shot.timelineDurationMs
        if shot.shotKey in breaks:
            durations.append(current)
            current = 0
    if current:
        durations.append(current)
    return durations


def _normalized_copy(value: str) -> str:
    return "".join(value.casefold().split()).rstrip("。；;，,.！!？?")
