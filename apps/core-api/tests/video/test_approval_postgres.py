from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import os
import socket
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from inkforge_contracts.video import (
    AssetBinding,
    CameraBeatSpec,
    CompiledAssetBinding,
    ScenePromptSpec,
    SeedanceOutputSpec,
    SeedancePromptPackage,
)
from inkforge_core.db.models import (
    Novel,
    ReviewArtifact,
    User,
    VideoGenerationTask,
    VideoProject,
    VideoReviewDecisionCommand,
    VideoScene,
    WritingBible,
)
from inkforge_core.db.url import asyncpg_connection_options
from inkforge_core.video.repository import VideoRepository
from inkforge_core.video.schemas import ApproveVideoSceneRequest
from sqlalchemy import select, text
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


def _candidate_json(scene_id: str, title: str) -> str:
    output = SeedanceOutputSpec(durationSeconds=4)
    scene_plan = ScenePromptSpec(
        sceneId=scene_id,
        title=title,
        summary="人物按下铜扣后木匣开始转动",
        visualStyle="冷峻写实",
        globalDirection="先展示按键动作，再展示机关启动",
        assets=[
            AssetBinding(
                assetId="fixture-audio",
                modality="audio",
                duty="ambience",
                targetEntity="木匣齿轮声",
                includeFeatures=["金属齿轮咬合声"],
                excludeFeatures=[],
            )
        ],
        beats=[
            CameraBeatSpec(
                beatId="beat-01",
                startSecond=0,
                endSecond=4,
                shotSize="中景",
                cameraAngle="平视",
                cameraMovement="固定机位",
                action="人物按下铜扣，木匣齿轮随即转动",
                referencedAssetIds=["fixture-audio"],
            )
        ],
        negativeConstraints=["禁止齿轮在按键前自行启动"],
        output=output,
    )
    prompt = "人物按下铜扣，木匣齿轮随后启动"
    prompt_package = SeedancePromptPackage(
        sceneId=scene_id,
        prompt=prompt,
        promptCharacterCount=len(prompt),
        assetBindings=[
            CompiledAssetBinding(
                assetId="fixture-audio",
                mediaAssetId=None,
                alias="@素材1",
                modality="audio",
                duty="ambience",
                bindingScope="scene_direct",
                settingReference=None,
                targetEntity="木匣齿轮声",
                isFixture=True,
            )
        ],
        output=output,
        previewOnly=True,
        assetReady=False,
        submissionReady=False,
        fixtureOnly=True,
    )
    return json.dumps(
        {
            "applyTarget": {"type": "video_scene_plan", "sceneId": scene_id},
            "scenePlan": scene_plan.model_dump(mode="json"),
            "promptPackage": prompt_package.model_dump(mode="json"),
        },
        ensure_ascii=False,
    )


@pytest.mark.asyncio
async def test_remote_dev_approval_is_concurrent_durable_and_ownership_safe() -> None:
    database_url = _remote_dev_database_url()
    options = asyncpg_connection_options(database_url)
    engine = create_async_engine(
        options.url,
        connect_args=options.connect_args,
        pool_size=6,
        max_overflow=0,
        pool_pre_ping=True,
    )
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    prefix = f"codex-video-approval-{uuid4().hex}"
    user_id = f"{prefix}-user"
    novel_id = f"{prefix}-novel"
    project_id = f"{prefix}-project"
    first_scene_id = f"{prefix}-scene-a"
    second_scene_id = f"{prefix}-scene-b"
    first_artifact_id = f"{prefix}-artifact-a"
    second_artifact_id = f"{prefix}-artifact-b"
    first_task_id = f"{prefix}-task-a"
    second_task_id = f"{prefix}-task-b"
    invalid_command_id = f"{prefix}-invalid-command"
    now = datetime.now(UTC).replace(tzinfo=None)

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
        assert identity[0] == "novelwriterdev"
        assert identity[1] is True

        first_candidate = _candidate_json(first_scene_id, "并发批准场景")
        second_candidate = _candidate_json(second_scene_id, "归属约束场景")
        source_text = "人物按下铜扣，木匣中的齿轮开始转动。"
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
            session.add(
                Novel(
                    id=novel_id,
                    userId=user_id,
                    name="批准并发集成测试",
                    createdAt=now,
                    updatedAt=now,
                )
            )
            await session.flush()
            session.add(
                WritingBible(
                    id=f"{prefix}-bible",
                    novelId=novel_id,
                    storyLengthProfile="long_serial",
                    createdAt=now,
                    updatedAt=now,
                )
            )
            session.add(
                VideoProject(
                    id=project_id,
                    novelId=novel_id,
                    title="批准并发集成测试",
                    mode="highlight",
                    status="active",
                    targetAspectRatio="16:9",
                    targetLanguage="zh-CN",
                    provider="seedance_2_5",
                    revision=1,
                    createdAt=now,
                    updatedAt=now,
                )
            )
            await session.flush()
            session.add_all(
                [
                    VideoScene(
                        id=first_scene_id,
                        projectId=project_id,
                        novelId=novel_id,
                        ordinal=1,
                        title="并发批准场景",
                        sourceText=source_text,
                        sourceHash=hashlib.sha256(source_text.encode()).hexdigest(),
                        durationSeconds=4,
                        status="awaiting_review",
                        revision=1,
                        createdAt=now,
                        updatedAt=now,
                    ),
                    VideoScene(
                        id=second_scene_id,
                        projectId=project_id,
                        novelId=novel_id,
                        ordinal=2,
                        title="归属约束场景",
                        sourceText=source_text,
                        sourceHash=hashlib.sha256(source_text.encode()).hexdigest(),
                        durationSeconds=4,
                        status="awaiting_review",
                        revision=1,
                        createdAt=now,
                        updatedAt=now,
                    ),
                ]
            )
            await session.flush()
            session.add_all(
                [
                    ReviewArtifact(
                        id=first_artifact_id,
                        novelId=novel_id,
                        videoSceneId=first_scene_id,
                        kind="video_scene_plan",
                        status="awaiting_user",
                        payloadJson=first_candidate,
                        revision=2,
                        createdByAgent="剧情",
                        updatedByAgent="剧情",
                        createdAt=now,
                        updatedAt=now,
                    ),
                    ReviewArtifact(
                        id=second_artifact_id,
                        novelId=novel_id,
                        videoSceneId=second_scene_id,
                        kind="video_scene_plan",
                        status="awaiting_user",
                        payloadJson=second_candidate,
                        revision=2,
                        createdByAgent="剧情",
                        updatedByAgent="剧情",
                        createdAt=now,
                        updatedAt=now,
                    ),
                    VideoGenerationTask(
                        id=first_task_id,
                        projectId=project_id,
                        sceneId=first_scene_id,
                        jobId=f"{prefix}-job-a",
                        kind="plan",
                        provider="deepseek",
                        status="completed",
                        idempotencyKey=f"{prefix}-idempotency-a",
                        requestJson="{}",
                        resultJson=first_candidate,
                        attemptCount=1,
                        nextAttemptAt=now,
                        createdAt=now,
                        updatedAt=now,
                        completedAt=now,
                    ),
                    VideoGenerationTask(
                        id=second_task_id,
                        projectId=project_id,
                        sceneId=second_scene_id,
                        jobId=f"{prefix}-job-b",
                        kind="plan",
                        provider="deepseek",
                        status="completed",
                        idempotencyKey=f"{prefix}-idempotency-b",
                        requestJson="{}",
                        resultJson=second_candidate,
                        attemptCount=1,
                        nextAttemptAt=now,
                        createdAt=now,
                        updatedAt=now,
                        completedAt=now,
                    ),
                ]
            )

        repository_a = VideoRepository(session_factory)
        repository_b = VideoRepository(session_factory)
        same_key_request = ApproveVideoSceneRequest(
            clientRequestId=f"{prefix}-same-key",
            expectedArtifactRevision=2,
        )
        same_key_results = await asyncio.gather(
            repository_a.approve_scene(user_id, first_scene_id, same_key_request),
            repository_b.approve_scene(user_id, first_scene_id, same_key_request),
        )
        assert same_key_results[0] == same_key_results[1]

        different_key_results = await asyncio.gather(
            repository_a.approve_scene(
                user_id,
                first_scene_id,
                ApproveVideoSceneRequest(
                    clientRequestId=f"{prefix}-different-key-a",
                    expectedArtifactRevision=2,
                ),
            ),
            repository_b.approve_scene(
                user_id,
                first_scene_id,
                ApproveVideoSceneRequest(
                    clientRequestId=f"{prefix}-different-key-b",
                    expectedArtifactRevision=2,
                ),
            ),
        )
        assert different_key_results == same_key_results

        async with session_factory() as session:
            scene_revision = await session.scalar(
                select(VideoScene.revision).where(VideoScene.id == first_scene_id)
            )
            commands = (
                await session.scalars(
                    select(VideoReviewDecisionCommand)
                    .where(VideoReviewDecisionCommand.requestedByUserId == user_id)
                    .order_by(VideoReviewDecisionCommand.clientRequestId)
                )
            ).all()
        assert scene_revision == 2
        assert len(commands) == 3
        assert len({command.clientRequestId for command in commands}) == 3
        assert len({command.resultJson for command in commands}) == 1

        invalid_command = VideoReviewDecisionCommand(
            id=invalid_command_id,
            requestedByUserId=user_id,
            novelId=novel_id,
            projectId=project_id,
            sceneId=first_scene_id,
            artifactId=second_artifact_id,
            sourceTaskId=first_task_id,
            decision="approve",
            expectedArtifactRevision=2,
            clientRequestId=f"{prefix}-invalid-ownership",
            requestHash="0" * 64,
            status="succeeded",
            resultJson=commands[0].resultJson,
            createdAt=now,
            updatedAt=now,
            completedAt=now,
        )
        with pytest.raises(IntegrityError, match="artifact_scene_fkey"):
            async with session_factory.begin() as session:
                session.add(invalid_command)
                await session.flush()

        async with session_factory() as session:
            assert (
                await session.scalar(
                    select(VideoReviewDecisionCommand.id).where(
                        VideoReviewDecisionCommand.id == invalid_command_id
                    )
                )
                is None
            )
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    'DELETE FROM "VideoReviewDecisionCommand" WHERE "requestedByUserId" = :user_id'
                ),
                {"user_id": user_id},
            )
            await connection.execute(
                text('DELETE FROM "Novel" WHERE "id" = :novel_id'),
                {"novel_id": novel_id},
            )
            await connection.execute(
                text('DELETE FROM "User" WHERE "id" = :user_id'),
                {"user_id": user_id},
            )
            remaining_commands = await connection.scalar(
                text(
                    'SELECT count(*) FROM "VideoReviewDecisionCommand" '
                    'WHERE "requestedByUserId" = :user_id'
                ),
                {"user_id": user_id},
            )
            remaining_roots = await connection.scalar(
                text('SELECT count(*) FROM "Novel" WHERE "id" = :novel_id'),
                {"novel_id": novel_id},
            )
            assert remaining_commands == 0
            assert remaining_roots == 0
        await engine.dispose()
