"""Episode 视频生产链不得重新依赖旧章节改编身份。"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_episode_video_production_has_independent_service_modules() -> None:
    expected = (
        "apps/core-api-java/src/main/java/cn/inkforge/core/video/api/VideoEpisodeController.java",
        "apps/core-api-java/src/main/java/cn/inkforge/core/video/api/VideoProductionController.java",
        "apps/core-api-java/src/main/java/cn/inkforge/core/video/api/VideoEpisodeRenderController.java",
        "apps/core-api-java/src/main/java/cn/inkforge/core/video/api/VideoEpisodePostProductionController.java",
        "apps/agent-service/src/inkforge_agents/execution/video_episode.py",
        "apps/agent-service/src/inkforge_agents/execution/video_storyboard.py",
        "apps/agent-service/src/inkforge_agents/providers/video_generation.py",
        "packages/service-contracts/src/inkforge_contracts/video_episode.py",
        "packages/service-contracts/src/inkforge_contracts/video_storyboard.py",
        "apps/web/src/features/video/production/episode-workspace.tsx",
    )

    assert all((ROOT / relative).is_file() for relative in expected)


def test_episode_domain_does_not_extend_legacy_repository() -> None:
    java_root = ROOT / "apps/core-api-java/src/main/java/cn/inkforge/core/video"
    sources = list(java_root.glob("**/*VideoEpisode*.java"))
    assert sources
    for path in sources:
        source = path.read_text(encoding="utf-8")
        assert "extends JooqVideoAdaptationRepository" not in source
        assert "ChapterAdaptationPlanCandidate" not in source


def test_episode_workspace_replaces_legacy_chapter_workspace() -> None:
    legacy_workspace = ROOT / (
        "apps/web/src/features/video/adaptation/chapter-adaptation-workspace.tsx"
    )
    workspace = ROOT / "apps/web/src/features/video/production/episode-workspace.tsx"

    assert not legacy_workspace.exists()
    source = workspace.read_text(encoding="utf-8")
    assert "adaptationId" not in source
    assert "VideoScene" not in source
    assert "planJson" not in source


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
    assert 'CREATE TABLE IF NOT EXISTS "VideoVisualCanon"' in source
    assert 'CREATE TABLE IF NOT EXISTS "VideoVisualCanonVersion"' in source
    assert 'CREATE TABLE IF NOT EXISTS "VideoShotVisualReferenceSet"' in source
    assert 'CREATE TABLE IF NOT EXISTS "VideoShotPromptVisualReference"' in source
    assert 'ALTER TABLE "VideoScene"' not in source
