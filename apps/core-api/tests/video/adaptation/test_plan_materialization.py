"""电影化候选批准后只物化新关系域，不写旧 VideoScene。"""

from __future__ import annotations

import hashlib
from datetime import datetime

import pytest
from inkforge_contracts.video_adaptation import (
    BeatCoverageGoal,
    ChapterAdaptationPlanCandidate,
    ChapterAdaptationSourceRange,
    CinematicSceneCandidate,
    CinematicShotCandidate,
    DramaticBeatCandidate,
)
from inkforge_core.db.models import (
    ReviewArtifact,
    VideoAdaptationTask,
    VideoChapterAdaptation,
    VideoChapterAdaptationHead,
    VideoCinematicScene,
    VideoDramaticBeat,
    VideoScene,
    VideoShot,
    VideoShotPromptHead,
)
from inkforge_core.video.adaptation.repository import _materialize_plan


class _Session:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.flush_count = 0

    async def scalar(self, statement: object) -> int:
        del statement
        return 0

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        """模拟真实会话的外键排序刷新；显式 ID 不需要额外回填。"""

        self.flush_count += 1


def _candidate(source: str) -> ChapterAdaptationPlanCandidate:
    source_range = ChapterAdaptationSourceRange(
        start=0,
        end=len(source),
        sourceText=source,
    )
    return ChapterAdaptationPlanCandidate(
        schemaVersion="chapter_adaptation_plan_v3",
        adaptationId="adaptation-1",
        sourceHash=hashlib.sha256(source.encode()).hexdigest(),
        scenes=[
            CinematicSceneCandidate(
                sceneKey="SC01",
                title="雨夜书房",
                locationLabel="书房",
                timeLabel="雨夜",
                objective="人物确认线索",
                changeSummary="平静等待转为危险预警",
                beats=[
                    DramaticBeatCandidate(
                        beatKey="B01",
                        title="钥匙揭示危险",
                        dramaticTurn="人物意识到危险",
                        visualStrategy="用建立镜头和钥匙特写完成揭示",
                        coverageGoals=[
                            BeatCoverageGoal(
                                goalKey="G01",
                                kind="story_information",
                                priority="essential",
                                description="观众看清染血钥匙并意识到危险",
                            )
                        ],
                        sourceRanges=[source_range],
                        shots=[
                            CinematicShotCandidate(
                                shotKey="S01",
                                title="建立书房",
                                narrativePurpose="establishing",
                                storyFunction="交代雨夜书房和人物空间",
                                audienceGain="观众获得人物与入口的空间关系",
                                coveredGoalKeys=["G01"],
                                sourceRelation="supplemental",
                                shotScale="long",
                                cameraAngle="eye_level",
                                cameraMovement="locked",
                                visualIntent="雨夜书房，门外冷光切入",
                                speechMode="none",
                                spokenText=None,
                                soundDesign="雨声",
                                cutReason="进入新场景先建立空间",
                                timelineDurationMs=2000,
                                sourceRanges=[],
                            ),
                            CinematicShotCandidate(
                                shotKey="S02",
                                title="钥匙落桌",
                                narrativePurpose="reveal",
                                storyFunction="用关键物件兑现危险信息",
                                audienceGain="观众看清钥匙带血",
                                coveredGoalKeys=["G01"],
                                sourceRelation="direct",
                                shotScale="close",
                                cameraAngle="eye_level",
                                cameraMovement="push_in",
                                visualIntent="染血钥匙落在桌面",
                                speechMode="none",
                                spokenText=None,
                                soundDesign="金属碰桌声",
                                cutReason="关键物件改变信息量，需要特写揭示",
                                timelineDurationMs=1500,
                                sourceRanges=[source_range],
                            ),
                        ],
                    )
                ],
            )
        ],
        suggestedEpisodeBreakAfterShotKeys=[],
    )


@pytest.mark.asyncio
async def test_materialization_creates_relational_scene_beat_shot_and_prompt_heads() -> None:
    source = "男人把染血的钥匙放在桌上。"
    session = _Session()
    adaptation = VideoChapterAdaptation(
        id="adaptation-1",
        projectId="project-1",
        novelId="novel-1",
        chapterId="chapter-1",
        chapterTitle="雨夜",
        chapterUpdatedAt=datetime(2026, 8, 18),
        sourceText=source,
        sourceHash=hashlib.sha256(source.encode()).hexdigest(),
    )
    head = VideoChapterAdaptationHead(
        adaptationId=adaptation.id,
        currentShotPlanVersionId="plan-v1",
        revision=1,
    )
    artifact = ReviewArtifact(id="artifact-1", videoAdaptationId=adaptation.id)
    task = VideoAdaptationTask(
        id="task-1",
        adaptationId=adaptation.id,
        baseShotPlanVersionId="plan-v1",
    )

    version = await _materialize_plan(  # type: ignore[arg-type]
        session,
        adaptation=adaptation,
        head=head,
        artifact=artifact,
        task=task,
        user_id="user-1",
        plan=_candidate(source),
    )

    assert version.adaptationId == adaptation.id
    assert version.basedOnVersionId == "plan-v1"
    assert sum(isinstance(item, VideoCinematicScene) for item in session.added) == 1
    assert sum(isinstance(item, VideoDramaticBeat) for item in session.added) == 1
    assert sum(isinstance(item, VideoShot) for item in session.added) == 2
    assert sum(isinstance(item, VideoShotPromptHead) for item in session.added) == 2
    assert not any(isinstance(item, VideoScene) for item in session.added)
    beat = next(item for item in session.added if isinstance(item, VideoDramaticBeat))
    shot = next(item for item in session.added if isinstance(item, VideoShot))
    assert beat.coverageGoalsJson is not None and '"G01"' in beat.coverageGoalsJson
    assert shot.sourceRelation == "supplemental"
    assert shot.storyFunction == "交代雨夜书房和人物空间"
    assert shot.speechMode == "none"
    assert session.flush_count == 4
