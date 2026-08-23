"""服务器 dev 数据库上的视频归属链真实约束测试。"""

from __future__ import annotations

import hashlib
import ipaddress
import os
import socket
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from inkforge_core.db.models import (
    Chapter,
    Novel,
    ReviewArtifact,
    User,
    VideoAsset,
    VideoAssetBinding,
    VideoGenerationTask,
    VideoProject,
    VideoScene,
    WritingBible,
)
from inkforge_core.db.url import asyncpg_connection_options
from inkforge_core.video.repository import VideoRepository
from inkforge_core.video.schemas import CreateVideoSceneRequest
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError
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


def _scene(
    *,
    scene_id: str,
    project_id: str,
    novel_id: str,
    chapter_id: str | None,
    ordinal: int,
    now: datetime,
) -> VideoScene:
    source_text = "人物推门进入雨夜。"
    return VideoScene(
        id=scene_id,
        projectId=project_id,
        novelId=novel_id,
        chapterId=chapter_id,
        ordinal=ordinal,
        title="归属链测试场景",
        sourceText=source_text,
        sourceHash=hashlib.sha256(source_text.encode()).hexdigest(),
        durationSeconds=4,
        status="draft",
        revision=1,
        createdAt=now,
        updatedAt=now,
    )


def _asset(*, asset_id: str, project_id: str, now: datetime) -> VideoAsset:
    return VideoAsset(
        id=asset_id,
        projectId=project_id,
        name="归属链测试素材",
        modality="image",
        duty="identity",
        storageKey=f"ownership-test/{asset_id}",
        mimeType="image/png",
        byteSize=1,
        sha256="a" * 64,
        sourceKind="user_upload",
        rightsStatus="confirmed",
        createdAt=now,
        updatedAt=now,
    )


@pytest.mark.asyncio
async def test_remote_dev_database_rejects_cross_domain_video_ownership() -> None:
    database_url = _remote_dev_database_url()
    options = asyncpg_connection_options(database_url)
    engine = create_async_engine(
        options.url,
        connect_args=options.connect_args,
        pool_size=2,
        max_overflow=0,
        pool_pre_ping=True,
    )
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    prefix = f"codex-video-ownership-{uuid4().hex}"
    user_id = f"{prefix}-user"
    novel_a = f"{prefix}-novel-a"
    novel_b = f"{prefix}-novel-b"
    chapter_a = f"{prefix}-chapter-a"
    chapter_b = f"{prefix}-chapter-b"
    project_a = f"{prefix}-project-a"
    project_b = f"{prefix}-project-b"
    scene_a = f"{prefix}-scene-a"
    asset_a = f"{prefix}-asset-a"
    asset_b = f"{prefix}-asset-b"
    valid_binding_id = f"{prefix}-binding-valid"
    now = datetime.now(UTC).replace(tzinfo=None)
    now = now.replace(microsecond=(now.microsecond // 1_000) * 1_000)

    try:
        async with engine.connect() as connection:
            identity = (
                await connection.execute(
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

        async with session_factory.begin() as session:
            session.add(
                User(
                    id=user_id,
                    username=prefix,
                    passwordHash="integration-test-only",
                    createdAt=now,
                    updatedAt=now,
                )
            )
            await session.flush()
            session.add_all(
                [
                    Novel(
                        id=novel_a,
                        userId=user_id,
                        name="归属链小说 A",
                        createdAt=now,
                        updatedAt=now,
                    ),
                    Novel(
                        id=novel_b,
                        userId=user_id,
                        name="归属链小说 B",
                        createdAt=now,
                        updatedAt=now,
                    ),
                ]
            )
            await session.flush()
            session.add_all(
                [
                    Chapter(
                        id=chapter_a,
                        novelId=novel_a,
                        order=1,
                        title="小说 A 第一章",
                        content="测试正文 A",
                        createdAt=now,
                        updatedAt=now,
                    ),
                    Chapter(
                        id=chapter_b,
                        novelId=novel_b,
                        order=1,
                        title="小说 B 第一章",
                        content="测试正文 B",
                        createdAt=now,
                        updatedAt=now,
                    ),
                    VideoProject(
                        id=project_a,
                        novelId=novel_a,
                        title="视频项目 A",
                        mode="highlight",
                        status="active",
                        targetAspectRatio="16:9",
                        targetLanguage="zh-CN",
                        provider="seedance_2_5",
                        revision=1,
                        createdAt=now,
                        updatedAt=now,
                    ),
                    VideoProject(
                        id=project_b,
                        novelId=novel_b,
                        title="视频项目 B",
                        mode="highlight",
                        status="active",
                        targetAspectRatio="16:9",
                        targetLanguage="zh-CN",
                        provider="seedance_2_5",
                        revision=1,
                        createdAt=now,
                        updatedAt=now,
                    ),
                    WritingBible(
                        id=f"{prefix}-bible-a",
                        novelId=novel_a,
                        storyLengthProfile="long_serial",
                        createdAt=now,
                        updatedAt=now,
                    ),
                ]
            )
            await session.flush()
            session.add_all(
                [
                    _scene(
                        scene_id=scene_a,
                        project_id=project_a,
                        novel_id=novel_a,
                        chapter_id=chapter_a,
                        ordinal=1,
                        now=now,
                    ),
                    _asset(asset_id=asset_a, project_id=project_a, now=now),
                    _asset(asset_id=asset_b, project_id=project_b, now=now),
                ]
            )
            await session.flush()

        acceptance = await VideoRepository(session_factory).create_scene_task(
            user_id,
            project_a,
            CreateVideoSceneRequest(
                clientRequestId=f"{prefix}-create-scene",
                chapterId=chapter_a,
                title="仓储创建场景",
                expectedChapterUpdatedAt=now,
                selectionStartUtf16=0,
                selectionEndUtf16=4,
                selectedText="测试正文",
                durationSeconds=4,
            ),
        )
        async with session_factory() as session:
            repository_scene = await session.get(VideoScene, acceptance.scene_id)
            repository_task = await session.get(VideoGenerationTask, acceptance.task_id)
        assert repository_scene is not None
        assert repository_scene.novelId == novel_a
        assert repository_scene.projectId == project_a
        assert repository_task is not None
        assert repository_task.sceneId == repository_scene.id
        assert repository_task.projectId == repository_scene.projectId

        with pytest.raises(IntegrityError, match="VideoScene_project_novel_fkey"):
            async with session_factory.begin() as session:
                session.add(
                    _scene(
                        scene_id=f"{prefix}-scene-wrong-project-novel",
                        project_id=project_a,
                        novel_id=novel_b,
                        chapter_id=chapter_b,
                        ordinal=10,
                        now=now,
                    )
                )
                await session.flush()

        with pytest.raises(IntegrityError, match="VideoScene_chapter_novel_fkey"):
            async with session_factory.begin() as session:
                session.add(
                    _scene(
                        scene_id=f"{prefix}-scene-wrong-chapter",
                        project_id=project_a,
                        novel_id=novel_a,
                        chapter_id=chapter_b,
                        ordinal=10,
                        now=now,
                    )
                )
                await session.flush()

        with pytest.raises(
            IntegrityError,
            match="ReviewArtifact_video_scene_novel_fkey",
        ):
            async with session_factory.begin() as session:
                session.add(
                    ReviewArtifact(
                        id=f"{prefix}-artifact-wrong-novel",
                        novelId=novel_b,
                        videoSceneId=scene_a,
                        kind="video_scene_plan",
                        status="awaiting_user",
                        payloadJson="{}",
                        revision=1,
                        createdAt=now,
                        updatedAt=now,
                    )
                )
                await session.flush()

        with pytest.raises(
            IntegrityError,
            match="VideoGenerationTask_scene_project_fkey",
        ):
            async with session_factory.begin() as session:
                session.add(
                    VideoGenerationTask(
                        id=f"{prefix}-task-wrong-project",
                        projectId=project_b,
                        sceneId=scene_a,
                        jobId=f"{prefix}-job-wrong-project",
                        kind="plan",
                        provider="deepseek",
                        status="pending",
                        idempotencyKey=f"{prefix}-task-wrong-project",
                        requestJson="{}",
                        attemptCount=0,
                        nextAttemptAt=now,
                        createdAt=now,
                        updatedAt=now,
                    )
                )
                await session.flush()

        with pytest.raises(
            IntegrityError,
            match="VideoAssetBinding_asset_project_fkey",
        ):
            async with session_factory.begin() as session:
                session.add(
                    VideoAssetBinding(
                        id=f"{prefix}-binding-wrong-asset",
                        sceneId=scene_a,
                        assetId=asset_b,
                        projectId=project_a,
                        targetEntity="人物",
                        includeFeaturesJson="[]",
                        excludeFeaturesJson="[]",
                        priority=50,
                        createdAt=now,
                        updatedAt=now,
                    )
                )
                await session.flush()

        with pytest.raises(
            IntegrityError,
            match="VideoAssetBinding_scene_project_fkey",
        ):
            async with session_factory.begin() as session:
                session.add(
                    VideoAssetBinding(
                        id=f"{prefix}-binding-wrong-scene",
                        sceneId=scene_a,
                        assetId=asset_b,
                        projectId=project_b,
                        targetEntity="人物",
                        includeFeaturesJson="[]",
                        excludeFeaturesJson="[]",
                        priority=50,
                        createdAt=now,
                        updatedAt=now,
                    )
                )
                await session.flush()

        async with session_factory.begin() as session:
            session.add(
                VideoAssetBinding(
                    id=valid_binding_id,
                    sceneId=scene_a,
                    assetId=asset_a,
                    projectId=project_a,
                    targetEntity="人物",
                    includeFeaturesJson="[]",
                    excludeFeaturesJson="[]",
                    priority=50,
                    createdAt=now,
                    updatedAt=now,
                )
            )
            await session.flush()

        # 原有 chapterId 外键仍保持删除章节后置空，而不是误删视频场景。
        async with session_factory.begin() as session:
            await session.execute(delete(Chapter).where(Chapter.id == chapter_a))
        async with session_factory() as session:
            chapter_after_delete = await session.scalar(
                select(VideoScene.chapterId).where(VideoScene.id == scene_a)
            )
            binding_after_delete = await session.scalar(
                select(VideoAssetBinding.id).where(VideoAssetBinding.id == valid_binding_id)
            )
        assert chapter_after_delete is None
        assert binding_after_delete == valid_binding_id
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text('DELETE FROM "Novel" WHERE "id" IN (:novel_a, :novel_b)'),
                {"novel_a": novel_a, "novel_b": novel_b},
            )
            await connection.execute(
                text('DELETE FROM "User" WHERE "id" = :user_id'),
                {"user_id": user_id},
            )
            remaining = await connection.scalar(
                text('SELECT count(*) FROM "Novel" WHERE "id" IN (:novel_a, :novel_b)'),
                {"novel_a": novel_a, "novel_b": novel_b},
            )
            assert remaining == 0
        await engine.dispose()
