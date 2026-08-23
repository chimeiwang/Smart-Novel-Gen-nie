"""章节影视化视觉设定版本、逐镜参考集合及其读模型。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import cast

from inkforge_contracts.video import AssetDuty, AssetModality
from inkforge_contracts.video_adaptation import (
    ShotVisualReferenceBundle,
    ShotVisualReferenceSnapshot,
    VisualCanonDuty,
    VisualSettingKind,
)
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ...db.base import generate_id, utc_now
from ...db.models import (
    Character,
    Item,
    Location,
    Novel,
    VideoAsset,
    VideoChapterAdaptation,
    VideoChapterAdaptationHead,
    VideoProject,
    VideoShot,
    VideoShotPromptVersion,
    VideoShotPromptVisualReference,
    VideoShotVisualReferenceBinding,
    VideoShotVisualReferenceSet,
    VideoVisualCanon,
    VideoVisualCanonVersion,
    WritingBible,
)
from ...errors import ApiError
from ..schemas import VideoAssetResponse
from .schemas import (
    ApproveVisualCanonRequest,
    CreateVisualCanonCandidateRequest,
    SaveShotVisualReferencesRequest,
    ShotVisualReferenceSelectionRequest,
    ShotVisualReferenceSetResponse,
    VisualCanonLibraryResponse,
    VisualCanonResponse,
    VisualCanonVersionResponse,
)


class VideoVisualCanonRepository:
    """视觉设定写模型与镜头参考 CAS，不操作旧 VideoScene 绑定。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list_canons(
        self,
        user_id: str,
        project_id: str,
    ) -> VisualCanonLibraryResponse:
        async with self._session_factory() as session:
            await _require_owned_project(session, user_id=user_id, project_id=project_id)
            return await load_visual_canon_library(session, project_id=project_id)

    async def set_candidate(
        self,
        user_id: str,
        project_id: str,
        request: CreateVisualCanonCandidateRequest,
    ) -> VisualCanonResponse:
        """设置候选图片；当前批准版本在用户确认前保持不变。"""

        async with self._session_factory() as session:
            async with session.begin():
                project = await _require_owned_project(
                    session,
                    user_id=user_id,
                    project_id=project_id,
                    lock=True,
                )
                await _require_long_serial(session, project.novelId)
                setting_name = await _require_setting(
                    session,
                    novel_id=project.novelId,
                    setting_kind=request.settingKind,
                    setting_id=request.settingId,
                )
                asset = await _require_candidate_asset(
                    session,
                    project_id=project.id,
                    asset_id=request.candidateAssetId,
                    duty=request.duty,
                )
                canon = await session.scalar(
                    select(VideoVisualCanon)
                    .where(
                        VideoVisualCanon.projectId == project.id,
                        VideoVisualCanon.settingKind == request.settingKind,
                        VideoVisualCanon.settingId == request.settingId,
                        VideoVisualCanon.duty == request.duty,
                        VideoVisualCanon.variantKey == request.variantKey,
                    )
                    .with_for_update()
                )
                include_json = _json_list(request.includeFeatures)
                exclude_json = _json_list(request.excludeFeatures)
                if canon is None:
                    canon = VideoVisualCanon(
                        id=generate_id(),
                        projectId=project.id,
                        novelId=project.novelId,
                        settingKind=request.settingKind,
                        settingId=request.settingId,
                        settingName=setting_name,
                        duty=request.duty,
                        variantKey=request.variantKey,
                        label=request.label,
                        candidateAssetId=asset.id,
                        candidateIncludeFeaturesJson=include_json,
                        candidateExcludeFeaturesJson=exclude_json,
                        candidateDefaultStrength=request.defaultStrength,
                        currentVersionId=None,
                        revision=1,
                        updatedAt=utc_now(),
                    )
                    session.add(canon)
                else:
                    unchanged = (
                        canon.settingName == setting_name
                        and canon.label == request.label
                        and canon.candidateAssetId == asset.id
                        and canon.candidateIncludeFeaturesJson == include_json
                        and canon.candidateExcludeFeaturesJson == exclude_json
                        and canon.candidateDefaultStrength == request.defaultStrength
                    )
                    if not unchanged:
                        canon.settingName = setting_name
                        canon.label = request.label
                        canon.candidateAssetId = asset.id
                        canon.candidateIncludeFeaturesJson = include_json
                        canon.candidateExcludeFeaturesJson = exclude_json
                        canon.candidateDefaultStrength = request.defaultStrength
                        canon.revision += 1
                        canon.updatedAt = utc_now()
                await session.flush()
                canon_id = canon.id
            library = await load_visual_canon_library(session, project_id=project_id)
        return _canon_by_id(library, canon_id)

    async def approve(
        self,
        user_id: str,
        canon_id: str,
        request: ApproveVisualCanonRequest,
    ) -> VisualCanonResponse:
        """把候选图片物化为新的不可变版本并切换当前 Head。"""

        async with self._session_factory() as session:
            async with session.begin():
                canon = await _require_owned_canon(
                    session,
                    user_id=user_id,
                    canon_id=canon_id,
                    lock=True,
                )
                current = (
                    await session.get(VideoVisualCanonVersion, canon.currentVersionId)
                    if canon.currentVersionId
                    else None
                )
                # 网络重试可能在第一次成功后重放；同一候选已经成为当前版本时无副作用返回。
                if (
                    canon.candidateAssetId is None
                    and current is not None
                    and current.assetId == request.candidateAssetId
                ):
                    project_id = canon.projectId
                    approved_id = canon.id
                else:
                    if canon.revision != request.expectedRevision:
                        raise _canon_revision_conflict(canon.revision)
                    if canon.candidateAssetId != request.candidateAssetId:
                        raise ApiError(
                            status_code=409,
                            code="VIDEO_VISUAL_CANON_CANDIDATE_CHANGED",
                            message="视觉设定候选已经变化，请刷新后重试",
                        )
                    if (
                        canon.candidateIncludeFeaturesJson is None
                        or canon.candidateExcludeFeaturesJson is None
                        or canon.candidateDefaultStrength is None
                    ):
                        raise ApiError(
                            status_code=409,
                            code="VIDEO_VISUAL_CANON_CANDIDATE_INVALID",
                            message="视觉设定候选元数据不完整",
                        )
                    asset = await _require_candidate_asset(
                        session,
                        project_id=canon.projectId,
                        asset_id=request.candidateAssetId,
                        duty=cast(VisualCanonDuty, canon.duty),
                    )
                    version_no = (
                        int(
                            await session.scalar(
                                select(
                                    func.coalesce(func.max(VideoVisualCanonVersion.versionNo), 0)
                                ).where(VideoVisualCanonVersion.canonId == canon.id)
                            )
                            or 0
                        )
                        + 1
                    )
                    version_id = generate_id()
                    content_hash = _canon_version_hash(
                        canon=canon,
                        asset=asset,
                        version_no=version_no,
                    )
                    version = VideoVisualCanonVersion(
                        id=version_id,
                        canonId=canon.id,
                        projectId=canon.projectId,
                        novelId=canon.novelId,
                        versionNo=version_no,
                        assetId=asset.id,
                        settingName=canon.settingName,
                        label=canon.label,
                        includeFeaturesJson=canon.candidateIncludeFeaturesJson,
                        excludeFeaturesJson=canon.candidateExcludeFeaturesJson,
                        defaultStrength=canon.candidateDefaultStrength,
                        approvedByUserId=user_id,
                        contentHash=content_hash,
                    )
                    session.add(version)
                    await session.flush()
                    canon.currentVersionId = version.id
                    canon.candidateAssetId = None
                    canon.candidateIncludeFeaturesJson = None
                    canon.candidateExcludeFeaturesJson = None
                    canon.candidateDefaultStrength = None
                    canon.revision += 1
                    canon.updatedAt = utc_now()
                    await session.flush()
                    project_id = canon.projectId
                    approved_id = canon.id
            library = await load_visual_canon_library(session, project_id=project_id)
        return _canon_by_id(library, approved_id)

    async def save_shot_references(
        self,
        user_id: str,
        adaptation_id: str,
        shot_id: str,
        request: SaveShotVisualReferencesRequest,
    ) -> ShotVisualReferenceSetResponse:
        """用完整集合替换一个正式镜头的视觉参考，并通过 revision 防止覆盖。"""

        async with self._session_factory() as session:
            async with session.begin():
                adaptation, head = await _require_owned_adaptation(
                    session,
                    user_id=user_id,
                    adaptation_id=adaptation_id,
                    lock=True,
                )
                if head.currentShotPlanVersionId is None:
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_SHOT_PLAN_REQUIRED",
                        message="请先确认正式镜头方案",
                    )
                shot = await session.scalar(
                    select(VideoShot)
                    .where(
                        VideoShot.id == shot_id,
                        VideoShot.planVersionId == head.currentShotPlanVersionId,
                    )
                    .with_for_update()
                )
                if shot is None:
                    raise ApiError(
                        status_code=404,
                        code="VIDEO_SHOT_NOT_FOUND",
                        message="正式镜头不存在或不属于当前方案",
                    )
                await _require_reference_versions(
                    session,
                    project_id=adaptation.projectId,
                    novel_id=adaptation.novelId,
                    version_ids=[item.canonVersionId for item in request.references],
                )
                reference_set = await session.get(
                    VideoShotVisualReferenceSet,
                    shot.id,
                    with_for_update=True,
                )
                existing = await _binding_signature(session, shot.id)
                requested = [(item.canonVersionId, item.strength) for item in request.references]
                current_revision = reference_set.revision if reference_set is not None else 0
                if current_revision != request.expectedRevision:
                    if existing != requested:
                        raise _shot_reference_revision_conflict(current_revision)
                elif existing != requested:
                    reference_set_is_new = reference_set is None
                    if reference_set is None:
                        reference_set = VideoShotVisualReferenceSet(
                            shotId=shot.id,
                            planVersionId=shot.planVersionId,
                            adaptationId=adaptation.id,
                            projectId=adaptation.projectId,
                            novelId=adaptation.novelId,
                            revision=1,
                            updatedAt=utc_now(),
                        )
                    else:
                        reference_set.revision += 1
                        reference_set.updatedAt = utc_now()
                    await _replace_shot_reference_bindings(
                        session,
                        reference_set=reference_set,
                        reference_set_is_new=reference_set_is_new,
                        adaptation=adaptation,
                        shot=shot,
                        references=request.references,
                    )
                response = (await load_shot_visual_reference_sets(session, shots=[shot]))[0]
        return response


async def load_visual_canon_library(
    session: AsyncSession,
    *,
    project_id: str,
) -> VisualCanonLibraryResponse:
    """一次读取项目内全部视觉槽、候选素材和不可变版本。"""

    canons = list(
        (
            await session.scalars(
                select(VideoVisualCanon)
                .where(VideoVisualCanon.projectId == project_id)
                .order_by(
                    VideoVisualCanon.settingKind,
                    VideoVisualCanon.settingName,
                    VideoVisualCanon.duty,
                    VideoVisualCanon.variantKey,
                )
            )
        ).all()
    )
    if not canons:
        return VisualCanonLibraryResponse(canons=[])
    canon_ids = [item.id for item in canons]
    versions = list(
        (
            await session.scalars(
                select(VideoVisualCanonVersion)
                .where(VideoVisualCanonVersion.canonId.in_(canon_ids))
                .order_by(VideoVisualCanonVersion.canonId, VideoVisualCanonVersion.versionNo.desc())
            )
        ).all()
    )
    asset_ids = {
        *[item.candidateAssetId for item in canons if item.candidateAssetId],
        *[item.assetId for item in versions],
    }
    assets = list(
        (await session.scalars(select(VideoAsset).where(VideoAsset.id.in_(asset_ids)))).all()
    )
    asset_by_id = {item.id: item for item in assets}
    versions_by_canon: dict[str, list[VisualCanonVersionResponse]] = {}
    for version in versions:
        asset = asset_by_id.get(version.assetId)
        if asset is None:
            raise _visual_canon_corrupt("正式视觉版本引用的素材不存在")
        versions_by_canon.setdefault(version.canonId, []).append(
            VisualCanonVersionResponse(
                id=version.id,
                canonId=version.canonId,
                versionNo=version.versionNo,
                asset=_asset_response(asset),
                settingName=version.settingName,
                label=version.label,
                includeFeatures=_parse_json_list(version.includeFeaturesJson),
                excludeFeatures=_parse_json_list(version.excludeFeaturesJson),
                defaultStrength=version.defaultStrength,
                contentHash=version.contentHash,
                createdAt=version.createdAt,
            )
        )
    responses: list[VisualCanonResponse] = []
    for canon in canons:
        candidate = asset_by_id.get(canon.candidateAssetId) if canon.candidateAssetId else None
        if canon.candidateAssetId and candidate is None:
            raise _visual_canon_corrupt("视觉设定候选引用的素材不存在")
        responses.append(
            VisualCanonResponse(
                id=canon.id,
                projectId=canon.projectId,
                novelId=canon.novelId,
                settingKind=cast(VisualSettingKind, canon.settingKind),
                settingId=canon.settingId,
                settingName=canon.settingName,
                duty=cast(VisualCanonDuty, canon.duty),
                variantKey=canon.variantKey,
                label=canon.label,
                candidateAsset=_asset_response(candidate) if candidate else None,
                candidateIncludeFeatures=(
                    _parse_json_list(canon.candidateIncludeFeaturesJson)
                    if canon.candidateIncludeFeaturesJson is not None
                    else []
                ),
                candidateExcludeFeatures=(
                    _parse_json_list(canon.candidateExcludeFeaturesJson)
                    if canon.candidateExcludeFeaturesJson is not None
                    else []
                ),
                candidateDefaultStrength=canon.candidateDefaultStrength,
                currentVersionId=canon.currentVersionId,
                versions=versions_by_canon.get(canon.id, []),
                revision=canon.revision,
                createdAt=canon.createdAt,
                updatedAt=canon.updatedAt,
            )
        )
    return VisualCanonLibraryResponse(canons=responses)


async def load_shot_visual_reference_sets(
    session: AsyncSession,
    *,
    shots: Sequence[VideoShot],
) -> list[ShotVisualReferenceSetResponse]:
    """按正式镜头顺序返回真实或 revision=0 的空参考集合。"""

    if not shots:
        return []
    shot_ids = [shot.id for shot in shots]
    sets = list(
        (
            await session.scalars(
                select(VideoShotVisualReferenceSet).where(
                    VideoShotVisualReferenceSet.shotId.in_(shot_ids)
                )
            )
        ).all()
    )
    set_by_shot = {item.shotId: item for item in sets}
    bindings = list(
        (
            await session.scalars(
                select(VideoShotVisualReferenceBinding)
                .where(VideoShotVisualReferenceBinding.shotId.in_(shot_ids))
                .order_by(
                    VideoShotVisualReferenceBinding.shotId,
                    VideoShotVisualReferenceBinding.ordinal,
                )
            )
        ).all()
    )
    references_by_shot = await _reference_snapshots_by_owner(
        session,
        owners=[(item.shotId, item.canonVersionId, item.strength) for item in bindings],
    )
    return [
        ShotVisualReferenceSetResponse(
            shotId=shot.id,
            shotKey=shot.shotKey,
            revision=set_by_shot[shot.id].revision if shot.id in set_by_shot else 0,
            references=references_by_shot.get(shot.id, []),
        )
        for shot in shots
    ]


async def freeze_visual_reference_bundles(
    session: AsyncSession,
    *,
    shots: Sequence[VideoShot],
    target_shot_keys: Sequence[str],
) -> list[ShotVisualReferenceBundle]:
    """创建 Prompt 任务时按目标顺序冻结视觉版本，不读取可变 Head。"""

    sets = await load_shot_visual_reference_sets(session, shots=shots)
    by_key = {item.shotKey: item for item in sets}
    return [
        ShotVisualReferenceBundle(
            shotKey=shot_key,
            references=by_key[shot_key].references,
        )
        for shot_key in target_shot_keys
    ]


async def load_prompt_visual_reference_map(
    session: AsyncSession,
    *,
    prompt_version_ids: Sequence[str],
) -> dict[str, list[ShotVisualReferenceSnapshot]]:
    """读取正式 PromptVersion 自己冻结的视觉参考。"""

    if not prompt_version_ids:
        return {}
    rows = list(
        (
            await session.scalars(
                select(VideoShotPromptVisualReference)
                .where(VideoShotPromptVisualReference.promptVersionId.in_(prompt_version_ids))
                .order_by(
                    VideoShotPromptVisualReference.promptVersionId,
                    VideoShotPromptVisualReference.ordinal,
                )
            )
        ).all()
    )
    return await _reference_snapshots_by_owner(
        session,
        owners=[(item.promptVersionId, item.canonVersionId, item.strength) for item in rows],
    )


async def add_prompt_visual_references(
    session: AsyncSession,
    *,
    prompt_version: VideoShotPromptVersion,
    adaptation: VideoChapterAdaptation,
    references: Sequence[ShotVisualReferenceSnapshot],
) -> None:
    """把候选任务或当前镜头集合的精确版本复制到正式 PromptVersion。"""

    await _require_reference_versions(
        session,
        project_id=adaptation.projectId,
        novel_id=adaptation.novelId,
        version_ids=[item.canonVersionId for item in references],
    )
    for ordinal, reference in enumerate(references, start=1):
        session.add(
            VideoShotPromptVisualReference(
                promptVersionId=prompt_version.id,
                shotId=prompt_version.shotId,
                shotPlanVersionId=prompt_version.shotPlanVersionId,
                adaptationId=adaptation.id,
                projectId=adaptation.projectId,
                novelId=adaptation.novelId,
                ordinal=ordinal,
                canonVersionId=reference.canonVersionId,
                strength=reference.strength,
            )
        )


async def current_shot_reference_snapshots(
    session: AsyncSession,
    *,
    shot: VideoShot,
) -> list[ShotVisualReferenceSnapshot]:
    return (await load_shot_visual_reference_sets(session, shots=[shot]))[0].references


async def _reference_snapshots_by_owner(
    session: AsyncSession,
    *,
    owners: Sequence[tuple[str, str, int]],
) -> dict[str, list[ShotVisualReferenceSnapshot]]:
    if not owners:
        return {}
    version_ids = list(dict.fromkeys(version_id for _owner, version_id, _strength in owners))
    versions = list(
        (
            await session.scalars(
                select(VideoVisualCanonVersion).where(VideoVisualCanonVersion.id.in_(version_ids))
            )
        ).all()
    )
    canon_ids = {item.canonId for item in versions}
    canons = list(
        (
            await session.scalars(
                select(VideoVisualCanon).where(VideoVisualCanon.id.in_(canon_ids))
            )
        ).all()
    )
    assets = list(
        (
            await session.scalars(
                select(VideoAsset).where(VideoAsset.id.in_({item.assetId for item in versions}))
            )
        ).all()
    )
    version_by_id = {item.id: item for item in versions}
    canon_by_id = {item.id: item for item in canons}
    asset_by_id = {item.id: item for item in assets}
    if set(version_ids) != set(version_by_id):
        raise _visual_canon_corrupt("镜头参考引用的视觉版本不存在")
    result: dict[str, list[ShotVisualReferenceSnapshot]] = {}
    for owner_id, version_id, strength in owners:
        version = version_by_id[version_id]
        canon = canon_by_id.get(version.canonId)
        asset = asset_by_id.get(version.assetId)
        if canon is None or asset is None:
            raise _visual_canon_corrupt("镜头参考的视觉设定关系不完整")
        result.setdefault(owner_id, []).append(
            ShotVisualReferenceSnapshot(
                canonVersionId=version.id,
                assetId=asset.id,
                assetSha256=asset.sha256,
                settingKind=cast(VisualSettingKind, canon.settingKind),
                settingId=canon.settingId,
                settingName=version.settingName,
                duty=cast(VisualCanonDuty, canon.duty),
                variantKey=canon.variantKey,
                label=version.label,
                includeFeatures=_parse_json_list(version.includeFeaturesJson),
                excludeFeatures=_parse_json_list(version.excludeFeaturesJson),
                strength=strength,
            )
        )
    return result


async def _require_owned_project(
    session: AsyncSession,
    *,
    user_id: str,
    project_id: str,
    lock: bool = False,
) -> VideoProject:
    statement = (
        select(VideoProject)
        .join(Novel, Novel.id == VideoProject.novelId)
        .where(
            VideoProject.id == project_id,
            VideoProject.deletedAt.is_(None),
            Novel.userId == user_id,
        )
    )
    if lock:
        statement = statement.with_for_update(of=VideoProject)
    project = await session.scalar(statement)
    if project is None:
        raise ApiError(status_code=404, code="VIDEO_PROJECT_NOT_FOUND", message="视频项目不存在")
    return project


async def _require_owned_canon(
    session: AsyncSession,
    *,
    user_id: str,
    canon_id: str,
    lock: bool,
) -> VideoVisualCanon:
    statement = (
        select(VideoVisualCanon)
        .join(VideoProject, VideoProject.id == VideoVisualCanon.projectId)
        .join(Novel, Novel.id == VideoVisualCanon.novelId)
        .where(
            VideoVisualCanon.id == canon_id,
            VideoProject.deletedAt.is_(None),
            Novel.userId == user_id,
        )
    )
    if lock:
        statement = statement.with_for_update(of=VideoVisualCanon)
    canon = await session.scalar(statement)
    if canon is None:
        raise ApiError(
            status_code=404,
            code="VIDEO_VISUAL_CANON_NOT_FOUND",
            message="视觉设定不存在",
        )
    return canon


async def _require_owned_adaptation(
    session: AsyncSession,
    *,
    user_id: str,
    adaptation_id: str,
    lock: bool,
) -> tuple[VideoChapterAdaptation, VideoChapterAdaptationHead]:
    statement = (
        select(VideoChapterAdaptation)
        .join(VideoProject, VideoProject.id == VideoChapterAdaptation.projectId)
        .join(Novel, Novel.id == VideoChapterAdaptation.novelId)
        .where(
            VideoChapterAdaptation.id == adaptation_id,
            VideoChapterAdaptation.lifecycleStatus == "active",
            VideoProject.deletedAt.is_(None),
            Novel.userId == user_id,
        )
    )
    if lock:
        statement = statement.with_for_update(of=VideoChapterAdaptation)
    adaptation = await session.scalar(statement)
    if adaptation is None:
        raise ApiError(
            status_code=404,
            code="VIDEO_ADAPTATION_NOT_FOUND",
            message="章节影视化改编不存在",
        )
    head = await session.get(VideoChapterAdaptationHead, adaptation.id, with_for_update=lock)
    if head is None:
        raise ApiError(
            status_code=409,
            code="VIDEO_ADAPTATION_HEAD_MISSING",
            message="章节影视化改编缺少正式版本指针",
        )
    return adaptation, head


async def _require_long_serial(session: AsyncSession, novel_id: str) -> None:
    bible = await session.scalar(
        select(WritingBible).where(WritingBible.novelId == novel_id).with_for_update()
    )
    if bible is None or bible.storyLengthProfile != "long_serial":
        raise ApiError(
            status_code=409,
            code="VIDEO_LONG_SERIAL_REQUIRED",
            message="视频制作只支持长篇小说",
        )


async def _require_setting(
    session: AsyncSession,
    *,
    novel_id: str,
    setting_kind: VisualSettingKind,
    setting_id: str,
) -> str:
    if setting_kind == "character":
        setting_name = await session.scalar(
            select(Character.name)
            .where(Character.id == setting_id, Character.novelId == novel_id)
            .with_for_update()
        )
    elif setting_kind == "location":
        setting_name = await session.scalar(
            select(Location.name)
            .where(Location.id == setting_id, Location.novelId == novel_id)
            .with_for_update()
        )
    else:
        setting_name = await session.scalar(
            select(Item.name)
            .where(Item.id == setting_id, Item.novelId == novel_id)
            .with_for_update()
        )
    if setting_name is None:
        raise ApiError(
            status_code=404,
            code="VIDEO_VISUAL_SETTING_NOT_FOUND",
            message="文字设定不存在或不属于当前小说",
        )
    return setting_name


async def _require_candidate_asset(
    session: AsyncSession,
    *,
    project_id: str,
    asset_id: str,
    duty: VisualCanonDuty,
) -> VideoAsset:
    asset = await session.scalar(
        select(VideoAsset)
        .where(VideoAsset.id == asset_id, VideoAsset.projectId == project_id)
        .with_for_update()
    )
    if asset is None:
        raise ApiError(
            status_code=404,
            code="VIDEO_ASSET_NOT_FOUND",
            message="视觉设定图片不存在",
        )
    if asset.modality != "image" or asset.duty != duty:
        raise ApiError(
            status_code=422,
            code="VIDEO_VISUAL_CANON_ASSET_INVALID",
            message="视觉设定只能使用职责匹配的图片素材",
        )
    if asset.rightsStatus != "confirmed" or asset.lockedAt is None:
        raise ApiError(
            status_code=409,
            code="VIDEO_VISUAL_CANON_ASSET_UNCONFIRMED",
            message="请先确认图片使用权再设置视觉设定",
        )
    return asset


async def _require_reference_versions(
    session: AsyncSession,
    *,
    project_id: str,
    novel_id: str,
    version_ids: Sequence[str],
) -> list[VideoVisualCanonVersion]:
    if not version_ids:
        return []
    versions = list(
        (
            await session.scalars(
                select(VideoVisualCanonVersion).where(
                    VideoVisualCanonVersion.id.in_(version_ids),
                    VideoVisualCanonVersion.projectId == project_id,
                    VideoVisualCanonVersion.novelId == novel_id,
                )
            )
        ).all()
    )
    if {item.id for item in versions} != set(version_ids):
        raise ApiError(
            status_code=422,
            code="VIDEO_VISUAL_REFERENCE_INVALID",
            message="镜头引用了未批准或其他项目的视觉设定版本",
        )
    return versions


async def _binding_signature(session: AsyncSession, shot_id: str) -> list[tuple[str, int]]:
    rows = list(
        (
            await session.scalars(
                select(VideoShotVisualReferenceBinding)
                .where(VideoShotVisualReferenceBinding.shotId == shot_id)
                .order_by(VideoShotVisualReferenceBinding.ordinal)
            )
        ).all()
    )
    return [(item.canonVersionId, item.strength) for item in rows]


async def _replace_shot_reference_bindings(
    session: AsyncSession,
    *,
    reference_set: VideoShotVisualReferenceSet,
    reference_set_is_new: bool,
    adaptation: VideoChapterAdaptation,
    shot: VideoShot,
    references: Sequence[ShotVisualReferenceSelectionRequest],
) -> None:
    """按复合外键要求先落集合 Head，再替换有序子项。"""

    if reference_set_is_new:
        session.add(reference_set)
        # 两张表没有 ORM relationship；显式 flush，避免子项在 Head 之前写入。
        await session.flush()
    await session.execute(
        delete(VideoShotVisualReferenceBinding).where(
            VideoShotVisualReferenceBinding.shotId == shot.id
        )
    )
    for ordinal, reference in enumerate(references, start=1):
        session.add(
            VideoShotVisualReferenceBinding(
                shotId=shot.id,
                ordinal=ordinal,
                planVersionId=shot.planVersionId,
                adaptationId=adaptation.id,
                projectId=adaptation.projectId,
                novelId=adaptation.novelId,
                canonVersionId=reference.canonVersionId,
                strength=reference.strength,
            )
        )
    await session.flush()


def _canon_version_hash(
    *,
    canon: VideoVisualCanon,
    asset: VideoAsset,
    version_no: int,
) -> str:
    value = {
        "canonId": canon.id,
        "versionNo": version_no,
        "assetId": asset.id,
        "assetSha256": asset.sha256,
        "settingKind": canon.settingKind,
        "settingId": canon.settingId,
        "duty": canon.duty,
        "variantKey": canon.variantKey,
        "label": canon.label,
        "includeFeatures": _parse_json_list(canon.candidateIncludeFeaturesJson or "[]"),
        "excludeFeatures": _parse_json_list(canon.candidateExcludeFeaturesJson or "[]"),
        "defaultStrength": canon.candidateDefaultStrength,
    }
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _asset_response(asset: VideoAsset) -> VideoAssetResponse:
    return VideoAssetResponse(
        id=asset.id,
        projectId=asset.projectId,
        name=asset.name,
        modality=cast(AssetModality, asset.modality),
        duty=cast(AssetDuty, asset.duty),
        mimeType=asset.mimeType,
        byteSize=asset.byteSize,
        durationMs=asset.durationMs,
        sha256=asset.sha256,
        sourceKind=asset.sourceKind,
        rightsStatus=asset.rightsStatus,
        lockedAt=asset.lockedAt,
        createdAt=asset.createdAt,
        updatedAt=asset.updatedAt,
    )


def _json_list(values: Sequence[str]) -> str:
    return json.dumps(list(values), ensure_ascii=False, separators=(",", ":"))


def _parse_json_list(value: str) -> list[str]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise _visual_canon_corrupt("视觉设定特征不是合法 JSON") from exc
    if not isinstance(parsed, list) or any(not isinstance(item, str) for item in parsed):
        raise _visual_canon_corrupt("视觉设定特征必须是字符串数组")
    return parsed


def _canon_by_id(library: VisualCanonLibraryResponse, canon_id: str) -> VisualCanonResponse:
    for canon in library.canons:
        if canon.id == canon_id:
            return canon
    raise AssertionError("视觉设定写入后读模型缺失")


def _canon_revision_conflict(current_revision: int) -> ApiError:
    return ApiError(
        status_code=409,
        code="VIDEO_VISUAL_CANON_REVISION_CONFLICT",
        message="视觉设定已经变化，请刷新后重试",
        details={"currentRevision": current_revision},
    )


def _shot_reference_revision_conflict(current_revision: int) -> ApiError:
    return ApiError(
        status_code=409,
        code="VIDEO_SHOT_VISUAL_REFERENCE_REVISION_CONFLICT",
        message="镜头视觉参考已经变化，请刷新后重试",
        details={"currentRevision": current_revision},
    )


def _visual_canon_corrupt(message: str) -> ApiError:
    return ApiError(
        status_code=409,
        code="VIDEO_VISUAL_CANON_DATA_INVALID",
        message=message,
    )
