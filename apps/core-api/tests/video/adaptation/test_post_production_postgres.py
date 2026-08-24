"""服务器开发库上的 P1–P3 真实事务验收；默认跳过且最终整体回滚。"""

from __future__ import annotations

import ipaddress
import os
import socket
from uuid import uuid4

import pytest
from inkforge_core.db.models import (
    Novel,
    VideoChapterAdaptation,
    VideoChapterAdaptationHead,
    VideoEpisodeEditVersion,
    VideoEpisodeMixVersion,
    VideoProject,
    VideoShotKeyframeVersion,
)
from inkforge_core.db.url import asyncpg_connection_options
from inkforge_core.errors import ApiError
from inkforge_core.video.adaptation.post_production_repository import (
    VideoPostProductionRepository,
)
from inkforge_core.video.adaptation.post_production_schemas import (
    EpisodeEditClipInput,
    EpisodeSubtitleCueInput,
    PostProductionReadinessResponse,
    SaveEpisodeEditVersionRequest,
    SaveEpisodeMixVersionRequest,
    SaveShotKeyframeVersionRequest,
    StartEpisodeExportRequest,
)
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def _remote_dev_database_url() -> str:
    database_url = os.environ.get("INKFORGE_VIDEO_DEV_DATABASE_URL")
    if not database_url:
        pytest.skip("未显式提供服务器 dev 数据库地址")
    options = asyncpg_connection_options(database_url)
    assert options.url.database == "novelwriterdev"
    assert options.url.host is not None
    addresses = {
        item[4][0]
        for item in socket.getaddrinfo(
            options.url.host,
            options.url.port or 5432,
            type=socket.SOCK_STREAM,
        )
    }
    assert addresses
    assert all(not ipaddress.ip_address(address).is_loopback for address in addresses)
    return database_url


@pytest.mark.asyncio
async def test_remote_dev_post_production_versions_are_durable_and_replay_safe() -> None:
    """真实 PostgreSQL 执行 CAS/重放/FK，并用外层事务保证不遗留验收数据。"""

    database_url = _remote_dev_database_url()
    options = asyncpg_connection_options(database_url)
    engine = create_async_engine(
        options.url,
        connect_args=options.connect_args,
        pool_size=1,
        max_overflow=0,
        pool_pre_ping=True,
    )
    request_suffix = uuid4().hex
    keyframe_request_id = f"codex-p13-keyframe-{request_suffix}"
    edit_request_id = f"codex-p13-edit-{request_suffix}"
    edit_second_request_id = f"codex-p13-edit-second-{request_suffix}"
    edit_branch_request_id = f"codex-p13-edit-branch-{request_suffix}"
    mix_request_id = f"codex-p13-mix-{request_suffix}"
    mix_second_request_id = f"codex-p13-mix-second-{request_suffix}"
    mix_branch_request_id = f"codex-p13-mix-branch-{request_suffix}"
    export_request_id = f"codex-p13-export-{request_suffix}"
    try:
        async with engine.connect() as identity_connection:
            identity = (
                await identity_connection.execute(
                    text(
                        """
                        SELECT
                          current_database(),
                          inet_server_addr() IS NOT NULL
                          AND NOT (
                            (family(inet_server_addr()) = 4
                              AND inet_server_addr() << inet '127.0.0.0/8')
                            OR inet_server_addr() = inet '::1'
                          )
                        """
                    )
                )
            ).one()
        assert identity == ("novelwriterdev", True)

        async with engine.connect() as connection:
            outer_transaction = await connection.begin()
            session_factory = async_sessionmaker(
                bind=connection,
                class_=AsyncSession,
                expire_on_commit=False,
                autoflush=False,
                join_transaction_mode="create_savepoint",
            )
            repository = VideoPostProductionRepository(session_factory)
            try:
                async with session_factory() as lookup_session:
                    owned = (
                        await lookup_session.execute(
                            select(VideoChapterAdaptation.id, Novel.userId)
                            .join(
                                VideoProject,
                                VideoProject.id == VideoChapterAdaptation.projectId,
                            )
                            .join(Novel, Novel.id == VideoProject.novelId)
                            .join(
                                VideoChapterAdaptationHead,
                                VideoChapterAdaptationHead.adaptationId
                                == VideoChapterAdaptation.id,
                            )
                            .where(
                                VideoChapterAdaptationHead.currentShotPlanVersionId.is_not(None),
                                VideoChapterAdaptationHead.currentEpisodePlanVersionId.is_not(None),
                            )
                            .order_by(VideoChapterAdaptation.createdAt.desc())
                            .limit(1)
                        )
                    ).one()
                adaptation_id, user_id = owned
                workspace = await repository.get_workspace(
                    user_id,
                    adaptation_id,
                    PostProductionReadinessResponse(
                        ffmpegAvailable=True,
                        ffprobeAvailable=True,
                        blockers=[],
                    ),
                )
                assert workspace.shots
                assert workspace.episodes

                shot = workspace.shots[0]
                keyframe_head = next(
                    head for head in shot.heads if head.role == "initial_state"
                )
                keyframe_request = SaveShotKeyframeVersionRequest(
                    clientRequestId=keyframe_request_id,
                    expectedRevision=keyframe_head.revision,
                    role="initial_state",
                    assetId=None,
                )
                saved_keyframe = await repository.save_keyframe(
                    user_id,
                    adaptation_id,
                    shot.shotId,
                    keyframe_request,
                )
                replayed_keyframe = await repository.save_keyframe(
                    user_id,
                    adaptation_id,
                    shot.shotId,
                    keyframe_request,
                )
                assert saved_keyframe.currentVersion is not None
                assert replayed_keyframe.currentVersion is not None
                assert (
                    replayed_keyframe.currentVersion.id
                    == saved_keyframe.currentVersion.id
                )
                refreshed_workspace = await repository.get_workspace(
                    user_id,
                    adaptation_id,
                    PostProductionReadinessResponse(
                        ffmpegAvailable=True,
                        ffprobeAvailable=True,
                        blockers=[],
                    ),
                )
                refreshed_keyframe_head = next(
                    head
                    for head in refreshed_workspace.shots[0].heads
                    if head.role == "initial_state"
                )
                assert [item.id for item in refreshed_keyframe_head.history][0] == (
                    saved_keyframe.currentVersion.id
                )

                episode = workspace.episodes[0]
                # 验收刻意保存全占位粗剪，既不依赖开发库已有 Take，也能验证导出门禁。
                placeholder_clips = [
                    EpisodeEditClipInput(
                        shotId=clip.shotId,
                        takeId=None,
                        sourceInMs=None,
                        sourceOutMs=None,
                        outputDurationMs=clip.outputDurationMs,
                        transitionAfter="cut",
                        transitionDurationMs=0,
                    )
                    for clip in episode.defaultClips
                ]
                edit_request = SaveEpisodeEditVersionRequest(
                    clientRequestId=edit_request_id,
                    expectedRevision=episode.editHead.revision,
                    clips=placeholder_clips,
                )
                saved_edit = await repository.save_edit_version(
                    user_id,
                    adaptation_id,
                    episode.episodeNo,
                    edit_request,
                )
                assert saved_edit.currentVersion is not None
                second_edit = await repository.save_edit_version(
                    user_id,
                    adaptation_id,
                    episode.episodeNo,
                    SaveEpisodeEditVersionRequest(
                        clientRequestId=edit_second_request_id,
                        expectedRevision=saved_edit.revision,
                        basedOnVersionId=saved_edit.currentVersion.id,
                        clips=placeholder_clips,
                    ),
                )
                assert second_edit.currentVersion is not None
                branched_edit = await repository.save_edit_version(
                    user_id,
                    adaptation_id,
                    episode.episodeNo,
                    SaveEpisodeEditVersionRequest(
                        clientRequestId=edit_branch_request_id,
                        expectedRevision=second_edit.revision,
                        basedOnVersionId=saved_edit.currentVersion.id,
                        clips=placeholder_clips,
                    ),
                )
                replayed_edit = await repository.save_edit_version(
                    user_id,
                    adaptation_id,
                    episode.episodeNo,
                    SaveEpisodeEditVersionRequest(
                        clientRequestId=edit_branch_request_id,
                        expectedRevision=second_edit.revision,
                        basedOnVersionId=saved_edit.currentVersion.id,
                        clips=placeholder_clips,
                    ),
                )
                assert branched_edit.currentVersion is not None
                assert replayed_edit.currentVersion is not None
                assert replayed_edit.currentVersion.id == branched_edit.currentVersion.id
                assert branched_edit.currentVersion.basedOnVersionId == (
                    saved_edit.currentVersion.id
                )
                assert len(branched_edit.currentVersion.clips) == len(episode.shots)

                subtitle_end = min(branched_edit.currentVersion.totalDurationMs, 1_000)
                mix_request = SaveEpisodeMixVersionRequest(
                    clientRequestId=mix_request_id,
                    expectedRevision=episode.mixHead.revision,
                    editVersionId=branched_edit.currentVersion.id,
                    audioClips=[],
                    subtitleCues=[
                        EpisodeSubtitleCueInput(
                            shotId=episode.shots[0].shotId,
                            startMs=0,
                            endMs=subtitle_end,
                            speaker="验收",
                            text="P1–P3 开发库事务验收字幕。",
                        )
                    ],
                )
                saved_mix = await repository.save_mix_version(
                    user_id,
                    adaptation_id,
                    episode.episodeNo,
                    mix_request,
                )
                assert saved_mix.currentVersion is not None
                second_mix = await repository.save_mix_version(
                    user_id,
                    adaptation_id,
                    episode.episodeNo,
                    SaveEpisodeMixVersionRequest(
                        clientRequestId=mix_second_request_id,
                        expectedRevision=saved_mix.revision,
                        basedOnVersionId=saved_mix.currentVersion.id,
                        editVersionId=branched_edit.currentVersion.id,
                        audioClips=[],
                        subtitleCues=[
                            EpisodeSubtitleCueInput(
                                shotId=episode.shots[0].shotId,
                                startMs=0,
                                endMs=subtitle_end,
                                speaker="验收",
                                text="第二个声音字幕版本。",
                            )
                        ],
                    ),
                )
                assert second_mix.currentVersion is not None
                branched_mix_request = SaveEpisodeMixVersionRequest(
                    clientRequestId=mix_branch_request_id,
                    expectedRevision=second_mix.revision,
                    basedOnVersionId=saved_mix.currentVersion.id,
                    editVersionId=branched_edit.currentVersion.id,
                    audioClips=[],
                    subtitleCues=[
                        EpisodeSubtitleCueInput(
                            shotId=episode.shots[0].shotId,
                            startMs=0,
                            endMs=subtitle_end,
                            speaker="验收",
                            text="从第一个声音版本创建的分支。",
                        )
                    ],
                )
                branched_mix = await repository.save_mix_version(
                    user_id,
                    adaptation_id,
                    episode.episodeNo,
                    branched_mix_request,
                )
                replayed_mix = await repository.save_mix_version(
                    user_id,
                    adaptation_id,
                    episode.episodeNo,
                    branched_mix_request,
                )
                assert branched_mix.currentVersion is not None
                assert replayed_mix.currentVersion is not None
                assert replayed_mix.currentVersion.id == branched_mix.currentVersion.id
                assert branched_mix.currentVersion.basedOnVersionId == (
                    saved_mix.currentVersion.id
                )
                assert len(branched_mix.currentVersion.subtitleCues) == 1

                with pytest.raises(ApiError) as export_error:
                    await repository.create_export_task(
                        user_id,
                        adaptation_id,
                        episode.episodeNo,
                        StartEpisodeExportRequest(
                            clientRequestId=export_request_id,
                            editVersionId=branched_edit.currentVersion.id,
                            mixVersionId=branched_mix.currentVersion.id,
                        ),
                    )
                assert export_error.value.code == "VIDEO_EXPORT_PLACEHOLDER_REMAINING"
            finally:
                await outer_transaction.rollback()

        # 外层回滚后再开独立连接，证明所有版本化写入都没有污染共享开发库。
        async with engine.connect() as verification_connection:
            counts = []
            for model, request_ids in (
                (VideoShotKeyframeVersion, [keyframe_request_id]),
                (
                    VideoEpisodeEditVersion,
                    [edit_request_id, edit_second_request_id, edit_branch_request_id],
                ),
                (
                    VideoEpisodeMixVersion,
                    [mix_request_id, mix_second_request_id, mix_branch_request_id],
                ),
            ):
                counts.append(
                    await verification_connection.scalar(
                        select(func.count()).select_from(model).where(
                            model.clientRequestId.in_(request_ids)
                        )
                    )
                )
        assert counts == [0, 0, 0]
    finally:
        await engine.dispose()
