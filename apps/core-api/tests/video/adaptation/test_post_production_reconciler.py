"""整集导出协调器必须正确处理数据库提交结果不确定窗口。"""

from __future__ import annotations

from pathlib import Path

import pytest
from inkforge_core.video.adaptation.post_production_manifest import (
    FrozenExportAsset,
    FrozenExportVideoClip,
    VideoEpisodeExportManifest,
)
from inkforge_core.video.adaptation.post_production_media import MediaProcessingError
from inkforge_core.video.adaptation.post_production_reconciler import (
    VideoPostProductionReconciler,
)
from inkforge_core.video.adaptation.post_production_repository import EpisodeExportClaim
from inkforge_core.video.storage import StoredVideoAsset


def _manifest() -> VideoEpisodeExportManifest:
    return VideoEpisodeExportManifest(
        adaptationId="adaptation-1",
        projectId="project-1",
        novelId="novel-1",
        episodePlanVersionId="episode-plan-1",
        shotPlanVersionId="shot-plan-1",
        episodeNo=1,
        editVersionId="edit-1",
        editContentHash="a" * 64,
        mixVersionId="mix-1",
        mixContentHash="b" * 64,
        targetAspectRatio="9:16",
        resolution="720p",
        framesPerSecond=24,
        burnSubtitles=False,
        totalDurationMs=1_000,
        videoClips=[
            FrozenExportVideoClip(
                ordinal=1,
                shotId="shot-1",
                takeId="take-1",
                asset=FrozenExportAsset(
                    assetId="video-1",
                    storageKey="project-1/video-1.mp4",
                    sha256="c" * 64,
                    mimeType="video/mp4",
                    durationMs=1_000,
                ),
                sourceInMs=0,
                sourceOutMs=1_000,
                outputDurationMs=1_000,
                transitionAfter="cut",
                transitionDurationMs=0,
            )
        ],
    )


def _claim() -> EpisodeExportClaim:
    return EpisodeExportClaim(
        task_id="task-1",
        project_id="project-1",
        manifest=_manifest(),
    )


class _Storage:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def delete(self, storage_key: str) -> bool:
        self.deleted.append(storage_key)
        return True


class _Media:
    async def render_episode(self, **_kwargs: object) -> StoredVideoAsset:
        return StoredVideoAsset(
            storage_key="project-1/export_task-1.mp4",
            absolute_path=Path("episode.mp4"),
            mime_type="video/mp4",
            byte_size=100,
            sha256="d" * 64,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("transitioned_to_failed", "expected_delete_count"),
    [(False, 1), (True, 2)],
)
async def test_export_completion_uncertainty_only_deletes_confirmed_failed_file(
    transitioned_to_failed: bool,
    expected_delete_count: int,
) -> None:
    class Repository:
        async def claim_due_export_tasks(self, _limit: int) -> list[EpisodeExportClaim]:
            return [_claim()]

        async def complete_export(self, *_args: object, **_kwargs: object) -> object:
            raise ConnectionError("提交响应丢失")

        async def fail_export(self, *_args: object) -> bool:
            return transitioned_to_failed

    storage = _Storage()
    reconciler = VideoPostProductionReconciler(
        Repository(),  # type: ignore[arg-type]
        _Media(),  # type: ignore[arg-type]
        storage,  # type: ignore[arg-type]
    )

    assert await reconciler.run_once() == 1
    assert storage.deleted == ["project-1/export_task-1.mp4"] * expected_delete_count


@pytest.mark.asyncio
async def test_media_failure_marks_task_failed_without_creating_output() -> None:
    class Repository:
        def __init__(self) -> None:
            self.failure: tuple[str, str, str] | None = None

        async def claim_due_export_tasks(self, _limit: int) -> list[EpisodeExportClaim]:
            return [_claim()]

        async def fail_export(self, task_id: str, code: str, message: str) -> bool:
            self.failure = (task_id, code, message)
            return True

    class Media:
        async def render_episode(self, **_kwargs: object) -> StoredVideoAsset:
            raise MediaProcessingError(
                "VIDEO_EXPORT_ASSET_HASH_MISMATCH",
                "内部哈希详情不应直接返回",
            )

    repository = Repository()
    storage = _Storage()
    reconciler = VideoPostProductionReconciler(
        repository,  # type: ignore[arg-type]
        Media(),  # type: ignore[arg-type]
        storage,  # type: ignore[arg-type]
    )

    await reconciler.run_once()

    assert repository.failure == (
        "task-1",
        "VIDEO_EXPORT_ASSET_HASH_MISMATCH",
        "导出引用的素材哈希已经变化",
    )
    assert storage.deleted == ["project-1/export_task-1.mp4"]
