"""后期制作仓储读模型必须如实保留当前指针与完整关键帧历史。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from inkforge_core.db.models import (
    VideoAsset,
    VideoShotKeyframeHead,
    VideoShotKeyframeVersion,
)
from inkforge_core.errors import ApiError
from inkforge_core.video.adaptation.post_production_repository import (
    _keyframe_head_from_loaded,
)


def _version(version_no: int, asset_id: str | None) -> VideoShotKeyframeVersion:
    now = datetime.now(UTC).replace(tzinfo=None)
    return VideoShotKeyframeVersion(
        id=f"version-{version_no}",
        adaptationId="adaptation-1",
        projectId="project-1",
        novelId="novel-1",
        shotId="shot-1",
        shotPlanVersionId="plan-1",
        role="initial_state",
        versionNo=version_no,
        basedOnVersionId=f"version-{version_no - 1}" if version_no > 1 else None,
        assetId=asset_id,
        sourceKind="asset" if asset_id else "cleared",
        sourceTakeId=None,
        sourceTimeMs=None,
        clientRequestId=f"keyframe-request-{version_no:04d}",
        requestHash="a" * 64,
        contentHash="b" * 64,
        createdByUserId="user-1",
        createdAt=now,
    )


def test_keyframe_head_returns_current_and_every_immutable_version() -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    versions = [_version(3, "asset-3"), _version(2, None), _version(1, "asset-1")]
    head = VideoShotKeyframeHead(
        shotId="shot-1",
        shotPlanVersionId="plan-1",
        role="initial_state",
        currentVersionId="version-3",
        revision=4,
        updatedAt=now,
    )
    assets = {
        asset_id: VideoAsset(
            id=asset_id,
            projectId="project-1",
            name=asset_id,
            modality="image",
            duty="keyframe",
            storageKey=f"project-1/{asset_id}.png",
            mimeType="image/png",
            byteSize=10,
            durationMs=None,
            sha256=sha,
            sourceKind="user_upload",
            rightsStatus="confirmed",
            lockedAt=now,
            createdAt=now,
            updatedAt=now,
        )
        for asset_id, sha in (("asset-1", "1" * 64), ("asset-3", "3" * 64))
    }

    response = _keyframe_head_from_loaded(
        shot_id="shot-1",
        role="initial_state",
        head=head,
        versions=versions,
        assets=assets,
    )

    assert response.revision == 4
    assert response.currentVersion is not None
    assert response.currentVersion.id == "version-3"
    assert [version.id for version in response.history] == [
        "version-3",
        "version-2",
        "version-1",
    ]
    assert response.history[1].sourceKind == "cleared"
    assert response.history[1].asset is None


def test_keyframe_head_rejects_dangling_current_pointer() -> None:
    head = VideoShotKeyframeHead(
        shotId="shot-1",
        shotPlanVersionId="plan-1",
        role="initial_state",
        currentVersionId="missing-version",
        revision=2,
        updatedAt=datetime.now(UTC).replace(tzinfo=None),
    )

    with pytest.raises(ApiError) as caught:
        _keyframe_head_from_loaded(
            shot_id="shot-1",
            role="initial_state",
            head=head,
            versions=[],
            assets={},
        )

    assert caught.value.code == "VIDEO_KEYFRAME_HEAD_INVALID"
