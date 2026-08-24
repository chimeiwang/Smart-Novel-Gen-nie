from __future__ import annotations

from pathlib import Path

import pytest
from inkforge_contracts.video_render import (
    SeedanceRenderOutput,
    SeedanceRenderQueryResponse,
    SeedanceRenderSubmitRequest,
    SeedanceRenderSubmitResponse,
    VideoShotRenderManifest,
)
from inkforge_core.agent_client import SeedanceSubmissionUnknownError
from inkforge_core.video.adaptation.render_reconciler import VideoShotRenderReconciler
from inkforge_core.video.adaptation.render_repository import (
    CompletedTakeInput,
    ShotRenderClaim,
)
from inkforge_core.video.adaptation.render_storage import ArchivedRenderResult
from inkforge_core.video.storage import StoredVideoAsset


def _manifest() -> VideoShotRenderManifest:
    return VideoShotRenderManifest(
        adaptationId="adaptation-1",
        projectId="project-1",
        novelId="novel-1",
        shotId="shot-1",
        shotKey="SH-001",
        shotPlanVersionId="plan-1",
        promptVersionId="prompt-1",
        promptContentHash="a" * 64,
        promptText="雨夜，人物回头，镜头缓慢推进。",
        sourceTimelineDurationMs=5_000,
        model="seedance-test",
        ratio="9:16",
        durationSeconds=5,
        resolution="720p",
        generateAudio=True,
        watermark=False,
        references=[],
    )


def _claim(*, status: str, provider_task_id: str | None = None) -> ShotRenderClaim:
    return ShotRenderClaim(
        task_id="task-1",
        project_id="project-1",
        novel_id="novel-1",
        status=status,
        provider_task_id=provider_task_id,
        poll_count=1,
        manifest=_manifest(),
    )


class _UnusedArchiver:
    async def archive(self, **_kwargs: object) -> ArchivedRenderResult:
        raise AssertionError("当前测试不应归档视频")


class _Storage:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def delete(self, storage_key: str) -> bool:
        self.deleted.append(storage_key)
        return True


@pytest.mark.asyncio
async def test_submit_unknown_never_turns_into_automatic_resubmit() -> None:
    class Repository:
        def __init__(self) -> None:
            self.unknown: tuple[str, str] | None = None

        async def claim_due_tasks(self, limit: int) -> list[ShotRenderClaim]:
            assert limit == 3
            return [_claim(status="submitting")]

        async def mark_submission_unknown(self, task_id: str, message: str) -> None:
            self.unknown = (task_id, message)

    class Gateway:
        def __init__(self) -> None:
            self.submit_count = 0

        async def submit_seedance_render(self, _request: object) -> object:
            self.submit_count += 1
            raise SeedanceSubmissionUnknownError

    repository = Repository()
    gateway = Gateway()
    reconciler = VideoShotRenderReconciler(
        repository,  # type: ignore[arg-type]
        gateway,  # type: ignore[arg-type]
        _UnusedArchiver(),  # type: ignore[arg-type]
        _Storage(),  # type: ignore[arg-type]
        provider_media_base_url=None,
        provider_asset_token_codec=None,
    )

    assert await reconciler.run_once() == 1
    assert gateway.submit_count == 1
    assert repository.unknown is not None
    assert repository.unknown[0] == "task-1"


@pytest.mark.asyncio
async def test_submit_success_persists_provider_identity() -> None:
    class Repository:
        def __init__(self) -> None:
            self.submitted: tuple[str, str] | None = None

        async def claim_due_tasks(self, _limit: int) -> list[ShotRenderClaim]:
            return [_claim(status="submitting")]

        async def mark_submitted(self, task_id: str, provider_task_id: str) -> None:
            self.submitted = (task_id, provider_task_id)

    class Gateway:
        async def submit_seedance_render(
            self,
            request: SeedanceRenderSubmitRequest,
        ) -> SeedanceRenderSubmitResponse:
            assert request.taskId == "task-1"
            return SeedanceRenderSubmitResponse(
                taskId="task-1",
                providerTaskId="provider-1",
            )

    repository = Repository()
    reconciler = VideoShotRenderReconciler(
        repository,  # type: ignore[arg-type]
        Gateway(),  # type: ignore[arg-type]
        _UnusedArchiver(),  # type: ignore[arg-type]
        _Storage(),  # type: ignore[arg-type]
        provider_media_base_url=None,
        provider_asset_token_codec=None,
    )

    await reconciler.run_once()

    assert repository.submitted == ("task-1", "provider-1")


@pytest.mark.asyncio
async def test_successful_query_archives_before_creating_take() -> None:
    class Repository:
        def __init__(self) -> None:
            self.completed: CompletedTakeInput | None = None

        async def claim_due_tasks(self, _limit: int) -> list[ShotRenderClaim]:
            return [_claim(status="running", provider_task_id="provider-1")]

        async def begin_archiving(self, task_id: str) -> bool:
            assert task_id == "task-1"
            return True

        async def complete_take(
            self,
            task_id: str,
            completed: CompletedTakeInput,
        ) -> object:
            assert task_id == "task-1"
            self.completed = completed
            return object()

    class Gateway:
        async def query_seedance_render(self, _request: object) -> SeedanceRenderQueryResponse:
            return SeedanceRenderQueryResponse(
                taskId="task-1",
                providerTaskId="provider-1",
                status="succeeded",
                output=SeedanceRenderOutput(
                    videoUrl="https://result.example/video.mp4",
                    durationSeconds=5.25,
                    usage={"frames": 126},
                ),
            )

    class Archiver:
        async def archive(self, **kwargs: object) -> ArchivedRenderResult:
            assert kwargs["video_url"] == "https://result.example/video.mp4"
            return ArchivedRenderResult(
                asset_id="task-1",
                stored=StoredVideoAsset(
                    storage_key="project-1/task-1.mp4",
                    absolute_path=Path("task-1.mp4"),
                    mime_type="video/mp4",
                    byte_size=12,
                    sha256="b" * 64,
                ),
            )

    repository = Repository()
    storage = _Storage()
    reconciler = VideoShotRenderReconciler(
        repository,  # type: ignore[arg-type]
        Gateway(),  # type: ignore[arg-type]
        Archiver(),  # type: ignore[arg-type]
        storage,  # type: ignore[arg-type]
        provider_media_base_url=None,
        provider_asset_token_codec=None,
    )

    await reconciler.run_once()

    assert repository.completed is not None
    assert repository.completed.duration_ms == 5_250
    assert repository.completed.provider_metadata == {
        "durationSeconds": 5.25,
        "resolution": None,
        "ratio": None,
        "framesPerSecond": None,
        "generateAudio": None,
        "usage": {"frames": 126},
    }
    assert storage.deleted == ["project-1/task-1.mp4"]


@pytest.mark.asyncio
async def test_archive_failure_does_not_create_take_and_cleans_exact_file() -> None:
    class Repository:
        def __init__(self) -> None:
            self.failed: tuple[str, str] | None = None

        async def claim_due_tasks(self, _limit: int) -> list[ShotRenderClaim]:
            return [_claim(status="running", provider_task_id="provider-1")]

        async def begin_archiving(self, _task_id: str) -> bool:
            return True

        async def fail_archiving(self, task_id: str, message: str) -> bool:
            self.failed = (task_id, message)
            return True

    class Gateway:
        async def query_seedance_render(self, _request: object) -> SeedanceRenderQueryResponse:
            return SeedanceRenderQueryResponse(
                taskId="task-1",
                providerTaskId="provider-1",
                status="succeeded",
                output=SeedanceRenderOutput(
                    videoUrl="https://result.example/video.mp4",
                ),
            )

    class Archiver:
        async def archive(self, **_kwargs: object) -> ArchivedRenderResult:
            raise RuntimeError("磁盘写入失败")

    repository = Repository()
    storage = _Storage()
    reconciler = VideoShotRenderReconciler(
        repository,  # type: ignore[arg-type]
        Gateway(),  # type: ignore[arg-type]
        Archiver(),  # type: ignore[arg-type]
        storage,  # type: ignore[arg-type]
        provider_media_base_url=None,
        provider_asset_token_codec=None,
    )

    await reconciler.run_once()

    assert repository.failed is not None
    assert repository.failed[0] == "task-1"
    assert storage.deleted == ["project-1/task-1.mp4", "project-1/task-1.mp4"]


@pytest.mark.asyncio
async def test_take_commit_response_loss_preserves_already_registered_file() -> None:
    class Repository:
        async def claim_due_tasks(self, _limit: int) -> list[ShotRenderClaim]:
            return [_claim(status="running", provider_task_id="provider-1")]

        async def begin_archiving(self, _task_id: str) -> bool:
            return True

        async def complete_take(self, _task_id: str, _completed: object) -> object:
            raise ConnectionError("提交响应丢失")

        async def fail_archiving(self, _task_id: str, _message: str) -> bool:
            # 新事务已经看到 succeeded，不能再转成 failed。
            return False

    class Gateway:
        async def query_seedance_render(self, _request: object) -> SeedanceRenderQueryResponse:
            return SeedanceRenderQueryResponse(
                taskId="task-1",
                providerTaskId="provider-1",
                status="succeeded",
                output=SeedanceRenderOutput(videoUrl="https://result.example/video.mp4"),
            )

    class Archiver:
        async def archive(self, **_kwargs: object) -> ArchivedRenderResult:
            return ArchivedRenderResult(
                asset_id="task-1",
                stored=StoredVideoAsset(
                    storage_key="project-1/task-1.mp4",
                    absolute_path=Path("task-1.mp4"),
                    mime_type="video/mp4",
                    byte_size=12,
                    sha256="b" * 64,
                ),
            )

    storage = _Storage()
    reconciler = VideoShotRenderReconciler(
        Repository(),  # type: ignore[arg-type]
        Gateway(),  # type: ignore[arg-type]
        Archiver(),  # type: ignore[arg-type]
        storage,  # type: ignore[arg-type]
        provider_media_base_url=None,
        provider_asset_token_codec=None,
    )

    await reconciler.run_once()

    assert storage.deleted == ["project-1/task-1.mp4"]
