package cn.inkforge.core.video.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;

import java.nio.file.Files;
import java.nio.file.Path;

/** 第一阶段迁移必须保护共享审核证据，并可在隔离 PostgreSQL 重放。 */
@Testcontainers
class VideoEpisodeMigrationTest {
    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_video_episode_test")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    @Test
    void 迁移可重放且新增审核归属不能级联删除() throws Exception {
        POSTGRES.copyFileToContainer(
                MountableFile.forClasspathResource("db/novelwriterdev-schema.sql"),
                "/tmp/base.sql");
        assertThat(sqlFile("/tmp/base.sql").getExitCode()).isZero();
        POSTGRES.copyFileToContainer(
                MountableFile.forClasspathResource("db/reset-video-production-p2.sql"),
                "/tmp/reset-video-production-p2.sql");
        var p2Reset = sqlFile("/tmp/reset-video-production-p2.sql");
        assertThat(p2Reset.getExitCode()).as(p2Reset.getStderr()).isZero();
        var reset =
                sql(
                        """
ALTER TABLE "ReviewArtifact" DROP CONSTRAINT "ReviewArtifact_video_episode_target_check";
ALTER TABLE "VideoEpisodeScriptVersion" DROP CONSTRAINT "VideoEpisodeScriptVersion_review_episode_fkey";
ALTER TABLE "ReviewArtifact" DROP COLUMN "videoEpisodeId";
DROP TABLE "VideoEpisodeCommand","VideoImpactReview","VideoEpisodeDependency","VideoEpisodeScriptDraft",
  "VideoEpisodeScriptVersion","VideoEpisodeSourceSnapshot","VideoEpisodeSourceSetVersion","VideoEpisode";
ALTER TYPE "ReviewArtifactKind" RENAME TO "ReviewArtifactKind_with_episode";
CREATE TYPE "ReviewArtifactKind" AS ENUM ('agent_updates','outline_draft','chapter_draft','lore_draft','revision_brief','beat_plan_draft','chapter_content','beat_plan','freeform_markdown','video_scene_plan','video_adaptation_plan');
ALTER TABLE "ReviewArtifact" ALTER COLUMN kind TYPE "ReviewArtifactKind" USING kind::text::"ReviewArtifactKind";
DROP TYPE "ReviewArtifactKind_with_episode";
CREATE ROLE episode_application;
ALTER TABLE "User" OWNER TO episode_application;
""");
        assertThat(reset.getExitCode()).as(reset.getStderr()).isZero();
        Path migration =
                Path.of("../../scripts/migrations/20260910_video_episode_script_domain.sql");
        if (!Files.exists(migration))
            migration = Path.of("scripts/migrations/20260910_video_episode_script_domain.sql");
        POSTGRES.copyFileToContainer(
                MountableFile.forHostPath(migration.toAbsolutePath()), "/tmp/episode.sql");
        String failed = Files.readString(migration).replace("COMMIT;", "SELECT 1/0;\nCOMMIT;");
        POSTGRES.copyFileToContainer(
                org.testcontainers.images.builder.Transferable.of(failed), "/tmp/failure.sql");
        assertThat(sqlFile("/tmp/failure.sql").getExitCode()).isNotZero();
        assertThat(sql("SELECT to_regclass('public.\"VideoEpisode\"') IS NULL").getStdout().strip())
                .isEqualTo("t");
        var first = sqlFile("/tmp/episode.sql");
        assertThat(first.getExitCode()).as(first.getStderr()).isZero();
        var second = sqlFile("/tmp/episode.sql");
        assertThat(second.getExitCode()).as(second.getStderr()).isZero();
        var result =
                POSTGRES.execInContainer(
                        "psql",
                        "-At",
                        "-U",
                        "inkforge",
                        "-d",
                        POSTGRES.getDatabaseName(),
                        "-c",
                        "SELECT confdeltype FROM pg_constraint WHERE"
                            + " conname='ReviewArtifact_video_episode_novel_fkey'");
        assertThat(result.getStdout().strip()).isEqualTo("r");
        assertThat(
                        sql("SELECT count(*) FROM pg_tables WHERE tablename IN"
                                + " ('VideoEpisode','VideoEpisodeSourceSetVersion','VideoEpisodeSourceSnapshot','VideoEpisodeScriptDraft','VideoEpisodeScriptVersion','VideoEpisodeDependency','VideoImpactReview','VideoEpisodeCommand')"
                                + " AND tableowner='episode_application'")
                                .getStdout()
                                .strip())
                .isEqualTo("8");
        assertThat(
                        sql("SELECT"
                                + " has_table_privilege('episode_application','\"VideoEpisode\"','INSERT,UPDATE,SELECT')")
                                .getStdout()
                                .strip())
                .isEqualTo("t");
    }

    private static org.testcontainers.containers.Container.ExecResult sqlFile(String path)
            throws Exception {
        return POSTGRES.execInContainer(
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "inkforge",
                "-d",
                POSTGRES.getDatabaseName(),
                "-f",
                path);
    }

    private static org.testcontainers.containers.Container.ExecResult sql(String statement)
            throws Exception {
        return POSTGRES.execInContainer(
                "psql",
                "-At",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "inkforge",
                "-d",
                POSTGRES.getDatabaseName(),
                "-c",
                statement);
    }
}
