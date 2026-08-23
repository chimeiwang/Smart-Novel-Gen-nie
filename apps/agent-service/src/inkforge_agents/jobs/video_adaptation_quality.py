"""章节分镜的非阻断审镜发现。

结构、来源和时长合法性由共享 Pydantic 契约负责。这里的电影语法与节奏经验只能形成
给作者和 Reviewer 的证据，不能替作者改写镜头或拒绝完整候选。
"""

from __future__ import annotations

from dataclasses import dataclass

from inkforge_contracts.video_adaptation import (
    ChapterAdaptationPlanCandidate,
    ChapterPacingPreset,
    CinematicReviewFinding,
    CinematicShotCandidate,
)


@dataclass(frozen=True, slots=True)
class _PacingReference:
    minimum_average_ms: int
    maximum_average_ms: int
    slow_shot_threshold_ms: int
    expected_maximum_slow_ratio: float


# 这些值只用于提示经验偏差，绝不作为候选通过条件。
_PACING_REFERENCES: dict[ChapterPacingPreset, _PacingReference] = {
    "short_drama": _PacingReference(1_200, 4_800, 6_000, 0.20),
    "cinematic": _PacingReference(1_500, 7_000, 9_000, 0.35),
    "dialogue_driven": _PacingReference(1_500, 6_000, 7_000, 0.30),
}


def collect_cinematic_findings(
    candidate: ChapterAdaptationPlanCandidate,
    *,
    pacing_preset: ChapterPacingPreset,
    target_episode_seconds: int,
) -> list[CinematicReviewFinding]:
    """按候选实际证据返回建议，不把经验规则升级为硬门禁。"""

    shots = [shot for scene in candidate.scenes for beat in scene.beats for shot in beat.shots]
    findings: list[CinematicReviewFinding] = []
    reference = _PACING_REFERENCES[pacing_preset]
    average_ms = sum(shot.timelineDurationMs for shot in shots) / len(shots)
    if not reference.minimum_average_ms <= average_ms <= reference.maximum_average_ms:
        findings.append(
            CinematicReviewFinding(
                severity="notice",
                scope="plan",
                message="平均镜头时长偏离当前节奏经验区间",
                evidence=(
                    f"当前平均 {average_ms / 1000:.1f} 秒/镜；"
                    f"{pacing_preset} 经验区间约为 "
                    f"{reference.minimum_average_ms / 1000:.1f}～"
                    f"{reference.maximum_average_ms / 1000:.1f} 秒。"
                ),
                suggestion="结合动作复杂度和情绪停顿逐镜判断，不要为了平均值机械改时长。",
            )
        )
    slow_count = sum(shot.timelineDurationMs > reference.slow_shot_threshold_ms for shot in shots)
    if slow_count / len(shots) > reference.expected_maximum_slow_ratio:
        findings.append(
            CinematicReviewFinding(
                severity="notice",
                scope="plan",
                message="长镜占比较高",
                evidence=f"{len(shots)} 个镜头中有 {slow_count} 个超过当前节奏的长镜参考值。",
                suggestion="逐个核对长镜是否同时完成多个叙事目标；成立则可以保留。",
            )
        )

    for scene in candidate.scenes:
        for beat in scene.beats:
            covered = {goal_key for shot in beat.shots for goal_key in shot.coveredGoalKeys}
            missing_essential = [
                goal
                for goal in beat.coverageGoals
                if goal.priority == "essential" and goal.goalKey not in covered
            ]
            missing_supporting = [
                goal
                for goal in beat.coverageGoals
                if goal.priority == "supporting" and goal.goalKey not in covered
            ]
            if missing_essential:
                findings.append(
                    CinematicReviewFinding(
                        severity="warning",
                        scope="beat",
                        scopeKey=beat.beatKey,
                        message="必要叙事目标尚未被镜头承担",
                        evidence="；".join(
                            f"{goal.goalKey} {goal.description}" for goal in missing_essential
                        ),
                        suggestion="让现有镜头补足这些内容，或在作者确认不需要后调整目标。",
                    )
                )
            if missing_supporting:
                findings.append(
                    CinematicReviewFinding(
                        severity="notice",
                        scope="beat",
                        scopeKey=beat.beatKey,
                        message="辅助叙事目标尚未被镜头承担",
                        evidence="；".join(
                            f"{goal.goalKey} {goal.description}" for goal in missing_supporting
                        ),
                        suggestion="按节奏取舍；辅助目标不是必须新增镜头的配额。",
                    )
                )
            for shot in beat.shots:
                if not shot.coveredGoalKeys:
                    findings.append(
                        CinematicReviewFinding(
                            severity="notice",
                            scope="shot",
                            scopeKey=shot.shotKey,
                            message="镜头尚未关联叙事目标",
                            evidence=f"本镜作用：{shot.storyFunction}",
                            suggestion="确认它是否带来独立信息、情绪或空间认知；否则考虑合并或删除。",
                        )
                    )
            findings.extend(_adjacent_repetition_findings(beat.shots))

    episode_durations = _episode_durations(candidate, shots)
    oversized = [
        (index, duration)
        for index, duration in enumerate(episode_durations, start=1)
        if duration > target_episode_seconds * 1_500
    ]
    if oversized:
        findings.append(
            CinematicReviewFinding(
                severity="warning",
                scope="plan",
                message="建议分集存在明显超出目标的单集",
                evidence="；".join(
                    f"第 {index} 集约 {duration / 1000:.1f} 秒" for index, duration in oversized
                ),
                suggestion="优先在戏剧节拍结束处调整分集，也可以保留有充分叙事理由的长集。",
            )
        )
    return findings


def validate_cinematic_candidate(
    candidate: ChapterAdaptationPlanCandidate,
    *,
    pacing_preset: ChapterPacingPreset,
    target_episode_seconds: int,
) -> None:
    """兼容旧调用；电影语法经验不再拒绝已经满足严格契约的候选。"""

    collect_cinematic_findings(
        candidate,
        pacing_preset=pacing_preset,
        target_episode_seconds=target_episode_seconds,
    )


def _adjacent_repetition_findings(
    shots: list[CinematicShotCandidate],
) -> list[CinematicReviewFinding]:
    findings: list[CinematicReviewFinding] = []
    for index, shot in enumerate(shots[1:], start=1):
        previous = shots[index - 1]
        same_camera = (
            previous.shotScale == shot.shotScale
            and previous.cameraAngle == shot.cameraAngle
            and previous.cameraMovement == shot.cameraMovement
        )
        same_visual = _normalized_copy(previous.visualIntent) == _normalized_copy(shot.visualIntent)
        same_function = _normalized_copy(previous.storyFunction) == _normalized_copy(
            shot.storyFunction
        )
        if same_camera and (same_visual or same_function):
            findings.append(
                CinematicReviewFinding(
                    severity="notice",
                    scope="shot",
                    scopeKey=shot.shotKey,
                    message=f"与 {previous.shotKey} 的画面职责可能重复",
                    evidence=(
                        "相邻镜头使用相同景别、机位和运动，且"
                        f"{'可见动作' if same_visual else '本镜作用'}基本一致。"
                    ),
                    suggestion="确认第二次切镜是否带来新信息；成立可保留，否则合并或重新分配职责。",
                )
            )
    return findings


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
