from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parents[4]
MIGRATION_PATH = ROOT / "scripts" / "migrations" / "20260817_video_domain_ownership_chain.sql"
ROLLBACK_PATH = MIGRATION_PATH.with_suffix(".rollback.sql")


def _compact(path: Path) -> str:
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8")).strip()


def test_video_ownership_migration_is_dev_only_transactional_and_serialized() -> None:
    sql = _compact(MIGRATION_PATH)
    rollback = _compact(ROLLBACK_PATH)

    assert sql.startswith("BEGIN;") and sql.endswith("COMMIT;")
    assert rollback.startswith("BEGIN;") and rollback.endswith("COMMIT;")
    assert "current_database() <> 'novelwriterdev'" in sql
    assert "current_database() <> 'novelwriterdev'" in rollback
    assert "pg_advisory_xact_lock" in sql
    assert "pg_advisory_xact_lock" in rollback


def test_video_ownership_migration_backfills_audits_and_seals_the_chain() -> None:
    sql = _compact(MIGRATION_PATH)

    assert 'ADD COLUMN IF NOT EXISTS "novelId" TEXT' in sql
    assert 'ADD COLUMN IF NOT EXISTS "projectId" TEXT' in sql
    assert 'SET "novelId" = project."novelId"' in sql
    assert 'SET "projectId" = scene."projectId"' in sql
    for audit_message in (
        "VideoScene 项目与小说归属不一致",
        "VideoScene 章节与小说归属不一致",
        "ReviewArtifact 场景与小说归属不一致",
        "VideoGenerationTask 场景与项目归属不一致",
        "VideoAssetBinding 场景、素材与项目归属不一致",
    ):
        assert audit_message in sql
    assert 'ALTER COLUMN "novelId" SET NOT NULL' in sql
    assert 'ALTER COLUMN "projectId" SET NOT NULL' in sql

    for constraint in (
        "Chapter_id_novelId_key",
        "VideoScene_id_novelId_key",
        "VideoAsset_id_projectId_key",
        "VideoScene_project_novel_fkey",
        "VideoScene_chapter_novel_fkey",
        "ReviewArtifact_video_scene_novel_fkey",
        "VideoGenerationTask_scene_project_fkey",
        "VideoAssetBinding_scene_project_fkey",
        "VideoAssetBinding_asset_project_fkey",
    ):
        assert f'"{constraint}"' in sql


def test_video_ownership_rollback_only_removes_new_named_structure() -> None:
    rollback = _compact(ROLLBACK_PATH)

    for constraint in (
        "VideoAssetBinding_asset_project_fkey",
        "VideoAssetBinding_scene_project_fkey",
        "VideoGenerationTask_scene_project_fkey",
        "ReviewArtifact_video_scene_novel_fkey",
        "VideoScene_chapter_novel_fkey",
        "VideoScene_project_novel_fkey",
        "VideoAsset_id_projectId_key",
        "VideoScene_id_novelId_key",
        "Chapter_id_novelId_key",
    ):
        assert f'DROP CONSTRAINT IF EXISTS "{constraint}"' in rollback
    assert 'DROP COLUMN IF EXISTS "projectId"' in rollback
    assert 'DROP COLUMN IF EXISTS "novelId"' in rollback
    assert "DROP TABLE IF EXISTS" not in rollback
