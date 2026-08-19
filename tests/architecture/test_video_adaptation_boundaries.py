"""章节影视化 v2 不得继续寄生在旧 VideoScene/planJson 上。"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_video_adaptation_has_independent_service_modules() -> None:
    expected = (
        "apps/core-api/src/inkforge_core/video/adaptation/repository.py",
        "apps/core-api/src/inkforge_core/video/adaptation/router.py",
        "apps/core-api/src/inkforge_core/video/adaptation/validation.py",
        "apps/agent-service/src/inkforge_agents/jobs/video_adaptation.py",
        "apps/agent-service/src/inkforge_agents/jobs/video_dispatch.py",
        "packages/service-contracts/src/inkforge_contracts/video_adaptation.py",
        "apps/web/src/features/video/adaptation/chapter-adaptation-workspace.tsx",
    )

    assert all((ROOT / relative).is_file() for relative in expected)


def test_new_adaptation_domain_does_not_extend_legacy_repository() -> None:
    legacy_repository = (
        ROOT / "apps/core-api/src/inkforge_core/video/repository.py"
    ).read_text(encoding="utf-8")

    assert "VideoChapterAdaptation" not in legacy_repository
    assert "chapter-adaptations" not in legacy_repository
    assert "ChapterAdaptationPlanCandidate" not in legacy_repository


def test_new_workspace_does_not_use_legacy_scene_or_plan_json() -> None:
    workspace = ROOT / (
        "apps/web/src/features/video/adaptation/chapter-adaptation-workspace.tsx"
    )
    source = workspace.read_text(encoding="utf-8")

    assert "VideoScene" not in source
    assert "planJson" not in source
    assert "chapter-shot-plan" not in source


def test_legacy_agent_handler_does_not_import_chapter_adaptation() -> None:
    source = (
        ROOT / "apps/agent-service/src/inkforge_agents/jobs/video.py"
    ).read_text(encoding="utf-8")

    assert "video_adaptation" not in source
    assert "chapter_cinematic_adaptation_v2" not in source


def test_dev_migration_refuses_every_database_except_novelwriterdev() -> None:
    migration = ROOT / (
        "scripts/migrations/20260818_video_chapter_adaptation_domain.sql"
    )
    source = migration.read_text(encoding="utf-8")

    assert "current_database() <> 'novelwriterdev'" in source
    assert "BEGIN;" in source
    assert "pg_advisory_xact_lock" in source
    assert 'CREATE TABLE IF NOT EXISTS "VideoChapterAdaptation"' in source
    assert 'CREATE TABLE IF NOT EXISTS "VideoShot"' in source
    assert '"VideoShot_beat_scene_plan_fkey"' in source
    assert '"VideoChapterAdaptationHead_current_episode_plan_fkey"' in source
    assert '"VideoShotPromptVersion_source_task_plan_fkey"' in source
    assert 'ALTER TABLE "VideoScene"' not in source
