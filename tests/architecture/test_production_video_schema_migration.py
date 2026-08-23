"""正式库视频结构晋升必须保持具名授权、人工确认和空域回滚边界。"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT / "scripts/migrations/20260823_production_video_adaptation_domain.sql"
)
ROLLBACK = MIGRATION.with_suffix(".rollback.sql")

VIDEO_TABLES = {
    "VideoAdaptationDecisionCommand",
    "VideoAdaptationTask",
    "VideoAsset",
    "VideoAssetBinding",
    "VideoChapterAdaptation",
    "VideoChapterAdaptationHead",
    "VideoCinematicScene",
    "VideoDramaticBeat",
    "VideoDramaticBeatSourceAnchor",
    "VideoEpisodeBoundary",
    "VideoEpisodePlanVersion",
    "VideoGenerationTask",
    "VideoProject",
    "VideoReviewDecisionCommand",
    "VideoScene",
    "VideoShot",
    "VideoShotPlanVersion",
    "VideoShotPromptHead",
    "VideoShotPromptVersion",
    "VideoShotPromptVisualReference",
    "VideoShotSourceAnchor",
    "VideoShotVisualReferenceBinding",
    "VideoShotVisualReferenceSet",
    "VideoVisualCanon",
    "VideoVisualCanonVersion",
}


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_production_migration_requires_exact_database_and_confirmation() -> None:
    source = _source(MIGRATION)

    assert source.startswith("\\set ON_ERROR_STOP on")
    assert "current_database() <> 'novelwriter'" in source
    assert "current_database() <> 'novelwriterdev'" not in source
    assert "novelwriter:20260823:apply" in source
    assert "\\if :{?confirm_production_video_adaptation}" in source
    assert source.count("pg_advisory_xact_lock") >= 5


def test_production_migration_contains_only_the_approved_video_tables() -> None:
    source = _source(MIGRATION)
    created_tables = set(
        re.findall(r'CREATE TABLE IF NOT EXISTS "([^"]+)"', source)
    )

    assert created_tables == VIDEO_TABLES
    assert "ALTER TYPE \"ReviewArtifactKind\" ADD VALUE IF NOT EXISTS 'video_scene_plan'" in source
    assert (
        "ALTER TYPE \"ReviewArtifactKind\" ADD VALUE IF NOT EXISTS "
        "'video_adaptation_plan'"
    ) in source
    for column in ("videoSceneId", "videoAdaptationId", "videoAdaptationTaskId"):
        assert f'ADD COLUMN IF NOT EXISTS "{column}"' in source


def test_production_rollback_refuses_nonempty_video_domain() -> None:
    source = _source(ROLLBACK)

    assert source.startswith("\\set ON_ERROR_STOP on")
    assert "current_database() <> 'novelwriter'" in source
    assert "novelwriter:20260823:rollback-empty-only" in source
    assert "SELECT count(*) FROM public.%I" in source
    assert "拒绝 destructive rollback" in source
    assert "CASCADE" not in source
    assert 'CREATE TYPE "ReviewArtifactKind_20260823_rollback" AS ENUM' in source
    assert 'DROP TYPE "ReviewArtifactKind"' in source
    assert (
        'ALTER TYPE "ReviewArtifactKind_20260823_rollback" '
        'RENAME TO "ReviewArtifactKind"'
    ) in source
    for table in VIDEO_TABLES:
        assert f'"{table}"' in source


def test_original_video_migrations_remain_development_only() -> None:
    paths = (
        "20260807_video_production_control_plane.sql",
        "20260817_video_review_decision_command.sql",
        "20260817_video_domain_ownership_chain.sql",
        "20260818_video_chapter_adaptation_domain.sql",
    )

    for filename in paths:
        source = _source(ROOT / "scripts/migrations" / filename)
        assert "current_database() <> 'novelwriterdev'" in source
        assert "current_database() <> 'novelwriter'" not in source
