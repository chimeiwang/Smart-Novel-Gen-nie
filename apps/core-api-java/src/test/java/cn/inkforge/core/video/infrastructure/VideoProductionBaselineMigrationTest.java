package cn.inkforge.core.video.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;

/** P2 具名迁移须在隔离 PostgreSQL 中原子、幂等并保持应用角色所有权。 */
@Testcontainers
class VideoProductionBaselineMigrationTest {
    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_video_production_test")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    @Test
    void 迁移失败完整回滚且重放后归属和媒体消费者范围完整() throws Exception {
        POSTGRES.copyFileToContainer(
                MountableFile.forClasspathResource("db/novelwriterdev-schema.sql"),
                "/tmp/base.sql");
        assertThat(sqlFile("/tmp/base.sql").getExitCode()).isZero();
        resetP2IfPresent();
        assertThat(sql("CREATE ROLE video_p2_application").getExitCode()).isZero();
        assertThat(sql("ALTER TABLE \"User\" OWNER TO video_p2_application").getExitCode())
                .isZero();

        Path migration =
                Path.of("../../scripts/migrations/20260910_video_production_baseline_domain.sql");
        if (!Files.exists(migration)) {
            migration =
                    Path.of("scripts/migrations/20260910_video_production_baseline_domain.sql");
        }
        String failed = Files.readString(migration).replace("COMMIT;", "SELECT 1/0;\nCOMMIT;");
        POSTGRES.copyFileToContainer(
                org.testcontainers.images.builder.Transferable.of(failed), "/tmp/p2-failed.sql");
        assertThat(sqlFile("/tmp/p2-failed.sql").getExitCode()).isNotZero();
        assertThat(sqlText("SELECT to_regclass('public.\"VideoEpisodeShot\"') IS NULL"))
                .isEqualTo("t");
        assertThat(
                        sqlText(
                                "SELECT count(*) FROM information_schema.columns WHERE"
                                        + " table_schema='public' AND table_name='VideoEpisode' AND"
                                        + " column_name IN ('currentStoryboardVersionId',"
                                        + "'latestDeliveryVersionId','deliveryRevision')"))
                .isEqualTo("0");

        POSTGRES.copyFileToContainer(
                MountableFile.forHostPath(migration.toAbsolutePath()), "/tmp/p2.sql");
        assertThat(sqlFile("/tmp/p2.sql").getExitCode()).isZero();
        assertThat(sqlFile("/tmp/p2.sql").getExitCode()).isZero();
        assertThat(
                        sqlText(
                                "SELECT count(*) FROM pg_tables WHERE schemaname='public' AND"
                                        + " tablename IN ('VideoEpisodeShot','VideoShotLineage',"
                                        + "'VideoStoryboardDraft','VideoStoryboardVersion','VideoShotVersion',"
                                        + "'VideoProductionBaseline','VideoTakeAdoption','VideoProductionBaselineShot',"
                                        + "'VideoProductionEditHead','VideoProductionMixHead')"
                                        + " AND tableowner='video_p2_application'"))
                .isEqualTo("10");
        assertThat(
                        sqlText(
                                "SELECT count(*) FROM information_schema.columns WHERE"
                                        + " table_schema='public' AND column_name='productionBaselineId' AND"
                                        + " table_name IN ('VideoShotPromptVersion','VideoShotKeyframeVersion',"
                                        + "'VideoShotRenderTask','VideoShotTake','VideoTakeFrameExtraction',"
                                        + "'VideoEpisodeEditVersion','VideoEpisodeEditClip','VideoEpisodeMixVersion',"
                                        + "'VideoEpisodeAudioClip','VideoEpisodeSubtitleCue',"
                                        + "'VideoEpisodeExportTask','VideoEpisodeExport')"))
                .isEqualTo("12");
        assertThat(
                        sqlText(
                                "SELECT count(*) FROM pg_constraint WHERE conname IN"
                                        + " ('VideoProductionBaselineShot_adoption_scope_fkey',"
                                        + "'VideoTakeAdoption_source_scope_fkey',"
                                        + "'VideoShotTake_last_frame_asset_fkey',"
                                        + "'VideoEpisode_current_storyboard_fkey',"
                                        + "'VideoEpisode_current_baseline_fkey',"
                                        + "'VideoEpisode_delivery_revision_check',"
                                        + "'VideoEpisodeExport_id_video_episode_key',"
                                        + "'VideoEpisode_latest_delivery_fkey')"))
                .isEqualTo("8");
        assertThat(
                        sqlText(
                                "SELECT count(*) FROM information_schema.columns WHERE"
                                        + " table_schema='public' AND table_name='VideoEpisode' AND"
                                        + " column_name IN ('latestDeliveryVersionId','deliveryRevision')"))
                .isEqualTo("2");
    }

    private static void resetP2IfPresent() throws Exception {
        POSTGRES.copyFileToContainer(
                MountableFile.forClasspathResource("db/reset-video-production-p2.sql"),
                "/tmp/reset-video-production-p2.sql");
        var result = sqlFile("/tmp/reset-video-production-p2.sql");
        assertThat(result.getExitCode()).as(result.getStderr()).isZero();
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

    private static String sqlText(String statement) throws Exception {
        return sql(statement).getStdout().strip();
    }
}
