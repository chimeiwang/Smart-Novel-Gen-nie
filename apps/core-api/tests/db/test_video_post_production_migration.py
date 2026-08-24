"""P1–P3 开发库具名迁移的静态安全边界。"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parents[4]
MIGRATION_PATH = (
    ROOT / "scripts" / "migrations" / "20260824_video_post_production_p1_p3.sql"
)


def _compact() -> str:
    return re.sub(r"\s+", " ", MIGRATION_PATH.read_text(encoding="utf-8")).strip()


def test_post_production_migration_is_dev_only_transactional_and_serialized() -> None:
    sql = _compact()

    assert sql.startswith("BEGIN;") and sql.endswith("COMMIT;")
    assert "current_database() <> 'novelwriterdev'" in sql
    assert "pg_advisory_xact_lock" in sql
    assert "novelwriter'" not in sql


def test_post_production_migration_defines_exact_owned_tables_and_duties() -> None:
    sql = _compact()
    expected_tables = {
        "VideoTakeFrameExtraction",
        "VideoShotKeyframeVersion",
        "VideoShotKeyframeHead",
        "VideoEpisodeEditVersion",
        "VideoEpisodeEditClip",
        "VideoEpisodeEditHead",
        "VideoEpisodeMixVersion",
        "VideoEpisodeAudioClip",
        "VideoEpisodeSubtitleCue",
        "VideoEpisodeMixHead",
        "VideoEpisodeExportTask",
        "VideoEpisodeExport",
    }
    actual_tables = set(re.findall(r'CREATE TABLE IF NOT EXISTS "([^"]+)"', sql))

    assert actual_tables == expected_tables
    assert "'sfx'" in sql
    assert "'episode_export'" in sql
    assert 'FOREIGN KEY ("assetId", "sourceTakeId", "sourceTimeMs")' in sql
    assert (
        'REFERENCES "VideoTakeFrameExtraction"("assetId", "takeId", "timestampMs")'
        in sql
    )


def test_post_production_migration_keeps_idempotent_replay_repairs() -> None:
    sql = _compact()

    assert len(re.findall(r'CREATE TABLE IF NOT EXISTS "([^"]+)"', sql)) == 12
    assert sql.count("CREATE INDEX IF NOT EXISTS") > 0
    assert sql.count("CREATE UNIQUE INDEX IF NOT EXISTS") > 0
    assert "VideoShotKeyframeVersion_extraction_fkey" in sql
    assert "IF NOT EXISTS ( SELECT 1 FROM pg_constraint" in sql
