from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parents[4]
MIGRATION_PATH = (
    ROOT / "scripts" / "migrations" / "20260817_video_review_decision_command.sql"
)
ROLLBACK_PATH = MIGRATION_PATH.with_suffix(".rollback.sql")


def _compact(path: Path) -> str:
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8")).strip()


def test_video_review_command_migration_is_dev_only_and_transactional() -> None:
    sql = _compact(MIGRATION_PATH)
    rollback = _compact(ROLLBACK_PATH)

    assert sql.startswith("BEGIN;") and sql.endswith("COMMIT;")
    assert rollback.startswith("BEGIN;") and rollback.endswith("COMMIT;")
    assert "current_database() <> 'novelwriterdev'" in sql
    assert "current_database() <> 'novelwriterdev'" in rollback
    assert "pg_advisory_xact_lock" in sql
    assert "pg_advisory_xact_lock" in rollback


def test_video_review_command_migration_declares_idempotency_and_audit_facts() -> None:
    sql = _compact(MIGRATION_PATH)

    assert 'CREATE TABLE IF NOT EXISTS "VideoReviewDecisionCommand"' in sql
    for column in (
        "requestedByUserId",
        "novelId",
        "projectId",
        "sceneId",
        "artifactId",
        "sourceTaskId",
        "expectedArtifactRevision",
        "clientRequestId",
        "requestHash",
        "resultJson",
        "completedAt",
    ):
        assert f'"{column}"' in sql
    assert '"VideoReviewDecisionCommand_user_request_key"' in sql
    assert '"requestedByUserId", "clientRequestId"' in sql
    assert '"VideoReviewDecisionCommand_artifact_revision_idx"' in sql
    assert '"artifactId", "expectedArtifactRevision", "decision"' in sql
    assert "CHECK (\"requestHash\" ~ '^[0-9a-f]{64}$')" in sql
    assert "jsonb_typeof(\"resultJson\"::jsonb) = 'object'" in sql
    for constraint in (
        "Novel_id_userId_key",
        "VideoProject_id_novelId_key",
        "VideoScene_id_projectId_key",
        "ReviewArtifact_id_videoSceneId_key",
        "VideoGenerationTask_id_sceneId_projectId_key",
        "VideoReviewDecisionCommand_novel_owner_fkey",
        "VideoReviewDecisionCommand_project_novel_fkey",
        "VideoReviewDecisionCommand_scene_project_fkey",
        "VideoReviewDecisionCommand_artifact_scene_fkey",
        "VideoReviewDecisionCommand_task_scene_project_fkey",
    ):
        assert f'\"{constraint}\"' in sql
    assert 'ALTER COLUMN "novelId" SET NOT NULL' in sql
    assert 'ALTER COLUMN "projectId" SET NOT NULL' in sql


def test_video_review_command_rollback_only_drops_the_named_preview_table() -> None:
    rollback = _compact(ROLLBACK_PATH)

    assert 'DROP TABLE IF EXISTS "VideoReviewDecisionCommand"' in rollback
    assert 'DROP TABLE IF EXISTS "VideoScene"' not in rollback
    assert 'DROP TABLE IF EXISTS "ReviewArtifact"' not in rollback
    for constraint in (
        "Novel_id_userId_key",
        "VideoProject_id_novelId_key",
        "VideoScene_id_projectId_key",
        "ReviewArtifact_id_videoSceneId_key",
        "VideoGenerationTask_id_sceneId_projectId_key",
    ):
        assert f'DROP CONSTRAINT IF EXISTS "{constraint}"' in rollback
