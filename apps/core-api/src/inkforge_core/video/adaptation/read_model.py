"""从章节改编关系事实重建前端嵌套读模型。"""

from __future__ import annotations

import json
from typing import Literal, cast

from inkforge_contracts.video import AspectRatio
from inkforge_contracts.video_adaptation import (
    ChapterAdaptationPlanCandidate,
    ChapterAdaptationSourceRange,
    ChapterAdaptationType,
    CinematicSceneCandidate,
    CinematicShotCandidate,
    DramaticBeatCandidate,
    FormalChapterAdaptationPlan,
    FormalCinematicScene,
    FormalCinematicShot,
    FormalDramaticBeat,
    ShotAudioMode,
    ShotCameraAngle,
    ShotCameraMovement,
    ShotNarrativePurpose,
    ShotPromptSpecBatch,
    ShotScale,
    compile_seedance_shot_prompt,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import (
    Novel,
    ReviewArtifact,
    VideoAdaptationTask,
    VideoChapterAdaptation,
    VideoChapterAdaptationHead,
    VideoCinematicScene,
    VideoDramaticBeat,
    VideoDramaticBeatSourceAnchor,
    VideoEpisodeBoundary,
    VideoEpisodePlanVersion,
    VideoProject,
    VideoShot,
    VideoShotPlanVersion,
    VideoShotPromptHead,
    VideoShotPromptVersion,
    VideoShotSourceAnchor,
)
from ...errors import ApiError
from .schemas import (
    ChapterAdaptationResponse,
    ChapterAdaptationReviewSummary,
    ChapterAdaptationTaskResponse,
    EpisodePlanResponse,
    ShotPromptCandidateResponse,
    ShotPromptVersionResponse,
)


async def load_adaptation_response(
    session: AsyncSession,
    *,
    user_id: str,
    adaptation_id: str,
) -> ChapterAdaptationResponse:
    """按小说归属读取一个章节改编及其当前正式、候选和任务状态。"""

    adaptation = await session.scalar(
        select(VideoChapterAdaptation)
        .join(VideoProject, VideoProject.id == VideoChapterAdaptation.projectId)
        .join(Novel, Novel.id == VideoProject.novelId)
        .where(
            VideoChapterAdaptation.id == adaptation_id,
            Novel.userId == user_id,
        )
    )
    if adaptation is None:
        raise ApiError(
            status_code=404,
            code="VIDEO_ADAPTATION_NOT_FOUND",
            message="章节影视化改编不存在",
        )
    head = await session.get(VideoChapterAdaptationHead, adaptation.id)
    if head is None:
        raise ApiError(
            status_code=409,
            code="VIDEO_ADAPTATION_HEAD_MISSING",
            message="章节影视化改编缺少正式版本指针",
        )
    project = await session.get(VideoProject, adaptation.projectId)
    if project is None:
        raise ApiError(
            status_code=409,
            code="VIDEO_ADAPTATION_PROJECT_MISSING",
            message="章节影视化项目不存在",
        )
    tasks = list(
        (
            await session.scalars(
                select(VideoAdaptationTask)
                .where(VideoAdaptationTask.adaptationId == adaptation.id)
                .order_by(
                    VideoAdaptationTask.createdAt.desc(),
                    VideoAdaptationTask.id.desc(),
                )
            )
        ).all()
    )
    latest_task = tasks[0] if tasks else None
    artifact = await session.scalar(
        select(ReviewArtifact)
        .where(ReviewArtifact.videoAdaptationId == adaptation.id)
        .order_by(ReviewArtifact.createdAt.desc(), ReviewArtifact.id.desc())
        .limit(1)
    )
    candidate_plan = _candidate_from_artifact(artifact, adaptation.id)
    current_plan, episode_plan, prompt_versions = await _load_formal_plan(
        session,
        adaptation=adaptation,
        head=head,
    )
    prompt_candidates = _prompt_candidates_from_tasks(
        tasks,
        current_plan=current_plan,
        prompt_versions=prompt_versions,
        ratio=project.targetAspectRatio,
    )
    state = _adaptation_state(
        latest_task=latest_task,
        artifact=artifact,
        has_plan=current_plan is not None,
    )
    return ChapterAdaptationResponse(
        id=adaptation.id,
        projectId=adaptation.projectId,
        novelId=adaptation.novelId,
        chapterId=adaptation.chapterId,
        chapterTitle=adaptation.chapterTitle,
        chapterUpdatedAt=adaptation.chapterUpdatedAt,
        sourceText=adaptation.sourceText,
        sourceHash=adaptation.sourceHash,
        lifecycleStatus=adaptation.lifecycleStatus,
        headRevision=head.revision,
        state=cast(
            Literal["empty", "generating", "awaiting_review", "approved", "failed"],
            state,
        ),
        currentPlan=current_plan,
        candidatePlan=candidate_plan,
        episodePlan=episode_plan,
        promptVersions=prompt_versions,
        promptCandidates=prompt_candidates,
        reviewArtifact=(
            ChapterAdaptationReviewSummary(
                id=artifact.id,
                status=artifact.status,
                revision=artifact.revision,
                title=artifact.title,
                summary=artifact.summary,
            )
            if artifact is not None
            else None
        ),
        latestTask=_task_response(latest_task) if latest_task is not None else None,
        createdAt=adaptation.createdAt,
    )


async def list_adaptation_responses(
    session: AsyncSession,
    *,
    user_id: str,
    project_id: str,
) -> list[ChapterAdaptationResponse]:
    """列出项目改编；当前开发预览规模有限，优先保证完整读模型一致性。"""

    ids = list(
        (
            await session.scalars(
                select(VideoChapterAdaptation.id)
                .join(VideoProject, VideoProject.id == VideoChapterAdaptation.projectId)
                .join(Novel, Novel.id == VideoProject.novelId)
                .where(
                    VideoChapterAdaptation.projectId == project_id,
                    Novel.userId == user_id,
                    VideoChapterAdaptation.lifecycleStatus == "active",
                )
                .order_by(VideoChapterAdaptation.createdAt.desc())
            )
        ).all()
    )
    return [
        await load_adaptation_response(
            session,
            user_id=user_id,
            adaptation_id=adaptation_id,
        )
        for adaptation_id in ids
    ]


async def _load_formal_plan(
    session: AsyncSession,
    *,
    adaptation: VideoChapterAdaptation,
    head: VideoChapterAdaptationHead,
) -> tuple[
    FormalChapterAdaptationPlan | None,
    EpisodePlanResponse | None,
    list[ShotPromptVersionResponse],
]:
    if head.currentShotPlanVersionId is None:
        return None, None, []
    version = await session.get(VideoShotPlanVersion, head.currentShotPlanVersionId)
    if version is None or version.adaptationId != adaptation.id:
        raise ApiError(
            status_code=409,
            code="VIDEO_ADAPTATION_PLAN_INVALID",
            message="章节影视化当前镜头方案指针无效",
        )
    scenes = list(
        (
            await session.scalars(
                select(VideoCinematicScene)
                .where(VideoCinematicScene.planVersionId == version.id)
                .order_by(VideoCinematicScene.ordinal)
            )
        ).all()
    )
    beats = list(
        (
            await session.scalars(
                select(VideoDramaticBeat)
                .where(VideoDramaticBeat.planVersionId == version.id)
                .order_by(VideoDramaticBeat.ordinal)
            )
        ).all()
    )
    shots = list(
        (
            await session.scalars(
                select(VideoShot)
                .where(VideoShot.planVersionId == version.id)
                .order_by(VideoShot.ordinal)
            )
        ).all()
    )
    beat_anchors = list(
        (
            await session.scalars(
                select(VideoDramaticBeatSourceAnchor)
                .where(VideoDramaticBeatSourceAnchor.planVersionId == version.id)
                .order_by(
                    VideoDramaticBeatSourceAnchor.beatId,
                    VideoDramaticBeatSourceAnchor.ordinal,
                )
            )
        ).all()
    )
    shot_anchors = list(
        (
            await session.scalars(
                select(VideoShotSourceAnchor)
                .where(VideoShotSourceAnchor.planVersionId == version.id)
                .order_by(
                    VideoShotSourceAnchor.shotId,
                    VideoShotSourceAnchor.ordinal,
                )
            )
        ).all()
    )
    beat_anchor_map: dict[str, list[ChapterAdaptationSourceRange]] = {}
    for beat_anchor in beat_anchors:
        beat_anchor_map.setdefault(beat_anchor.beatId, []).append(
            _source_range(
                adaptation.sourceText,
                beat_anchor.startCodePoint,
                beat_anchor.endCodePoint,
            )
        )
    shot_anchor_map: dict[str, list[ChapterAdaptationSourceRange]] = {}
    for shot_anchor in shot_anchors:
        shot_anchor_map.setdefault(shot_anchor.shotId, []).append(
            _source_range(
                adaptation.sourceText,
                shot_anchor.startCodePoint,
                shot_anchor.endCodePoint,
            )
        )
    shots_by_beat: dict[str, list[FormalCinematicShot]] = {}
    for shot in shots:
        shots_by_beat.setdefault(shot.beatId, []).append(
            FormalCinematicShot(
                id=shot.id,
                shotKey=shot.shotKey,
                title=shot.title,
                narrativePurpose=cast(ShotNarrativePurpose, shot.narrativePurpose),
                adaptationType=cast(ChapterAdaptationType, shot.adaptationType),
                shotScale=cast(ShotScale, shot.shotScale),
                cameraAngle=cast(ShotCameraAngle, shot.cameraAngle),
                cameraMovement=cast(ShotCameraMovement, shot.cameraMovement),
                visualIntent=shot.visualIntent,
                audioMode=cast(ShotAudioMode, shot.audioMode),
                audioIntent=shot.audioIntent,
                cutReason=shot.cutReason,
                timelineDurationMs=shot.timelineDurationMs,
                sourceRanges=shot_anchor_map.get(shot.id, []),
            )
        )
    beats_by_scene: dict[str, list[FormalDramaticBeat]] = {}
    for beat in beats:
        beats_by_scene.setdefault(beat.sceneId, []).append(
            FormalDramaticBeat(
                id=beat.id,
                beatKey=beat.beatKey,
                title=beat.title,
                dramaticTurn=beat.dramaticTurn,
                visualStrategy=beat.visualStrategy,
                sourceRanges=beat_anchor_map.get(beat.id, []),
                shots=shots_by_beat.get(beat.id, []),
            )
        )
    formal_scenes = [
        FormalCinematicScene(
            id=scene.id,
            sceneKey=scene.sceneKey,
            title=scene.title,
            locationLabel=scene.locationLabel,
            timeLabel=scene.timeLabel,
            objective=scene.objective,
            changeSummary=scene.changeSummary,
            beats=beats_by_scene.get(scene.id, []),
        )
        for scene in scenes
    ]
    episode_plan = await _load_episode_plan(session, head=head, shots=shots)
    episode_break_keys = (
        [
            next(shot.shotKey for shot in shots if shot.id == shot_id)
            for shot_id in episode_plan.breakAfterShotIds
        ]
        if episode_plan is not None
        else []
    )
    plan = FormalChapterAdaptationPlan(
        schemaVersion="chapter_adaptation_plan_v2",
        planVersionId=version.id,
        versionNo=version.versionNo,
        adaptationId=adaptation.id,
        sourceHash=adaptation.sourceHash,
        scenes=formal_scenes,
        episodeBreakAfterShotKeys=episode_break_keys,
    )
    prompt_versions = await _load_prompt_versions(session, shots=shots)
    return plan, episode_plan, prompt_versions


async def _load_episode_plan(
    session: AsyncSession,
    *,
    head: VideoChapterAdaptationHead,
    shots: list[VideoShot],
) -> EpisodePlanResponse | None:
    if head.currentEpisodePlanVersionId is None:
        return None
    version = await session.get(VideoEpisodePlanVersion, head.currentEpisodePlanVersionId)
    if version is None:
        raise ApiError(
            status_code=409,
            code="VIDEO_EPISODE_PLAN_INVALID",
            message="当前分集版本指针无效",
        )
    boundaries = list(
        (
            await session.scalars(
                select(VideoEpisodeBoundary)
                .where(VideoEpisodeBoundary.episodePlanVersionId == version.id)
                .order_by(VideoEpisodeBoundary.ordinal)
            )
        ).all()
    )
    shot_ids = {shot.id for shot in shots}
    if any(boundary.afterShotId not in shot_ids for boundary in boundaries):
        raise ApiError(
            status_code=409,
            code="VIDEO_EPISODE_PLAN_INVALID",
            message="当前分集版本引用了其他镜头方案",
        )
    return EpisodePlanResponse(
        id=version.id,
        versionNo=version.versionNo,
        shotPlanVersionId=version.shotPlanVersionId,
        breakAfterShotIds=[boundary.afterShotId for boundary in boundaries],
    )


async def _load_prompt_versions(
    session: AsyncSession,
    *,
    shots: list[VideoShot],
) -> list[ShotPromptVersionResponse]:
    if not shots:
        return []
    shot_map = {shot.id: shot for shot in shots}
    heads = list(
        (
            await session.scalars(
                select(VideoShotPromptHead).where(
                    VideoShotPromptHead.shotId.in_(shot_map)
                )
            )
        ).all()
    )
    version_ids = [head.currentVersionId for head in heads if head.currentVersionId]
    if not version_ids:
        return []
    versions = list(
        (
            await session.scalars(
                select(VideoShotPromptVersion).where(
                    VideoShotPromptVersion.id.in_(version_ids)
                )
            )
        ).all()
    )
    head_by_shot = {head.shotId: head for head in heads}
    return [
        ShotPromptVersionResponse(
            id=version.id,
            shotId=version.shotId,
            shotKey=shot_map[version.shotId].shotKey,
            versionNo=version.versionNo,
            generatedText=version.generatedText,
            currentText=version.currentText,
            promptEdited=(
                version.generatedText is None
                or version.currentText != version.generatedText
            ),
            headRevision=head_by_shot[version.shotId].revision,
            createdAt=version.createdAt,
        )
        for version in sorted(versions, key=lambda item: shot_map[item.shotId].ordinal)
    ]


def _candidate_from_artifact(
    artifact: ReviewArtifact | None,
    adaptation_id: str,
) -> ChapterAdaptationPlanCandidate | None:
    if artifact is None or artifact.status != "awaiting_user":
        return None
    try:
        payload = json.loads(artifact.payloadJson)
        if payload.get("applyTarget") != {
            "type": "video_adaptation_plan",
            "adaptationId": adaptation_id,
        }:
            return None
        return ChapterAdaptationPlanCandidate.model_validate(payload["candidate"])
    except (AttributeError, KeyError, TypeError, ValueError):
        return None


def _prompt_candidates_from_tasks(
    tasks: list[VideoAdaptationTask],
    *,
    current_plan: FormalChapterAdaptationPlan | None,
    prompt_versions: list[ShotPromptVersionResponse],
    ratio: str,
) -> list[ShotPromptCandidateResponse]:
    if current_plan is None:
        return []
    shot_by_key = {
        shot.shotKey: shot
        for scene in current_plan.scenes
        for beat in scene.beats
        for shot in beat.shots
    }
    # tasks 已由查询按创建时间倒序排列；每个镜头只取最新一份候选，但不能让一次
    # 单镜重生成遮掉其他镜头来自更早任务、仍未保存的候选。
    saved_generated_by_shot_id = {
        version.shotId: version.generatedText for version in prompt_versions
    }
    seen_shot_ids: set[str] = set()
    candidates: list[ShotPromptCandidateResponse] = []
    for task in tasks:
        if (
            task.kind != "shot_prompt"
            or task.status != "completed"
            or task.baseShotPlanVersionId != current_plan.planVersionId
            or task.resultJson is None
        ):
            continue
        try:
            result = json.loads(task.resultJson)
            batch = ShotPromptSpecBatch.model_validate(result["promptBatch"])
        except (KeyError, TypeError, ValueError):
            continue
        for item in batch.prompts:
            shot = shot_by_key.get(item.shotKey)
            if shot is None or shot.id in seen_shot_ids:
                continue
            # 先标记再判断是否已保存，避免回退展示同一镜头更旧的陈旧候选。
            seen_shot_ids.add(shot.id)
            try:
                compiled_prompt = compile_seedance_shot_prompt(
                    item.spec,
                    ratio=cast(AspectRatio, ratio),
                    timeline_duration_ms=shot.timelineDurationMs,
                )
            except ValueError:
                continue
            # 保存提示词时 generatedText 会保留候选编译结果。若两者一致，说明该候选
            # 已物化为正式版本；继续返回它会覆盖 currentText，让用户误以为手改内容丢失。
            if saved_generated_by_shot_id.get(shot.id) == compiled_prompt:
                continue
            candidates.append(
                ShotPromptCandidateResponse(
                    taskId=task.id,
                    shotId=shot.id,
                    shotKey=item.shotKey,
                    spec=item.spec,
                    compiledPrompt=compiled_prompt,
                )
            )
    shot_position = {shot.id: index for index, shot in enumerate(shot_by_key.values())}
    return sorted(candidates, key=lambda item: shot_position[item.shotId])


def _task_response(task: VideoAdaptationTask) -> ChapterAdaptationTaskResponse:
    return ChapterAdaptationTaskResponse(
        id=task.id,
        jobId=task.jobId,
        kind=cast(Literal["shot_plan", "shot_prompt"], task.kind),
        workflow=task.workflow,
        status=task.status,
        checkpointStage=task.checkpointStage,
        lastErrorCode=task.lastErrorCode,
        lastErrorMessage=task.lastErrorMessage,
        createdAt=task.createdAt,
        updatedAt=task.updatedAt,
    )


def _adaptation_state(
    *,
    latest_task: VideoAdaptationTask | None,
    artifact: ReviewArtifact | None,
    has_plan: bool,
) -> str:
    if latest_task is not None and latest_task.status in {
        "pending",
        "submitted",
        "processing",
    }:
        return "generating"
    if artifact is not None and artifact.status == "awaiting_user":
        return "awaiting_review"
    if has_plan:
        return "approved"
    if latest_task is not None and latest_task.status == "failed":
        return "failed"
    return "empty"


def _source_range(source_text: str, start: int, end: int) -> ChapterAdaptationSourceRange:
    return ChapterAdaptationSourceRange(
        start=start,
        end=end,
        sourceText=source_text[start:end],
    )


def candidate_from_formal_plan(
    plan: FormalChapterAdaptationPlan,
) -> ChapterAdaptationPlanCandidate:
    """移除数据库身份，只保留 Agent 需要的不可变镜头内容。"""

    return ChapterAdaptationPlanCandidate(
        schemaVersion="chapter_adaptation_plan_v2",
        adaptationId=plan.adaptationId,
        sourceHash=plan.sourceHash,
        scenes=[
            CinematicSceneCandidate(
                sceneKey=scene.sceneKey,
                title=scene.title,
                locationLabel=scene.locationLabel,
                timeLabel=scene.timeLabel,
                objective=scene.objective,
                changeSummary=scene.changeSummary,
                beats=[
                    DramaticBeatCandidate(
                        beatKey=beat.beatKey,
                        title=beat.title,
                        dramaticTurn=beat.dramaticTurn,
                        visualStrategy=beat.visualStrategy,
                        sourceRanges=beat.sourceRanges,
                        shots=[
                            CinematicShotCandidate.model_validate(
                                shot.model_dump(mode="python", exclude={"id"})
                            )
                            for shot in beat.shots
                        ],
                    )
                    for beat in scene.beats
                ],
            )
            for scene in plan.scenes
        ],
        suggestedEpisodeBreakAfterShotKeys=plan.episodeBreakAfterShotKeys,
    )
