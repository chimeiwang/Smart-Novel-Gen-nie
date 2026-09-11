package cn.inkforge.core.video.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;

/** P4 退役后旧审核 enum 只能作为墓碑值保留，不能形成没有目标的审核记录。 */
@Testcontainers
class VideoLegacyDomainRetirementMigrationTest {
    private static final String TARGET_DATABASE = "inkforge_video_legacy_retirement_test";
    private static final String CONFIRMATION =
            "P4_WRITES_REMOVED_HISTORY_EMPTY_READ_RUNTIME_REMOVED_FILES_PRESERVED_"
                    + "SHARED_MEDIA_PRESERVED";

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("novelwriterdev")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    @Test
    void 退役迁移可重放且拒绝两个旧视频审核种类() throws Exception {
        POSTGRES.copyFileToContainer(
                MountableFile.forClasspathResource("db/novelwriterdev-schema.sql"),
                "/tmp/base.sql");
        assertThat(sqlFile("novelwriterdev", "/tmp/base.sql").getExitCode()).isZero();

        Path durable = migration("20260831_durable_agent_execution.sql");
        POSTGRES.copyFileToContainer(
                MountableFile.forHostPath(durable.toAbsolutePath()), "/tmp/durable.sql");
        assertThat(sqlFile("novelwriterdev", "/tmp/durable.sql").getExitCode()).isZero();
        assertThat(
                        sql(
                                        "novelwriterdev",
                                        "CREATE DATABASE \"" + TARGET_DATABASE
                                                + "\" TEMPLATE novelwriterdev")
                                .getExitCode())
                .isZero();

        Path retirement = migration("20260910_video_legacy_domain_retirement.sql");
        POSTGRES.copyFileToContainer(
                MountableFile.forHostPath(retirement.toAbsolutePath()), "/tmp/retirement.sql");
        assertThat(retirement()).satisfies(result -> assertThat(result.getExitCode())
                .as(result.getStderr())
                .isZero());
        assertThat(retirement()).satisfies(result -> assertThat(result.getExitCode())
                .as(result.getStderr())
                .isZero());

        assertThat(
                        sql(
                                        TARGET_DATABASE,
                                        "INSERT INTO \"User\"(id,username,\"passwordHash\",\"updatedAt\")"
                                                + " VALUES ('retirement-user','retirement-user','test',CURRENT_TIMESTAMP);"
                                                + " INSERT INTO \"Novel\"(id,\"userId\",name,\"updatedAt\")"
                                                + " VALUES ('retirement-novel','retirement-user','退役约束',CURRENT_TIMESTAMP)")
                                .getExitCode())
                .isZero();
        assertOldKindRejected("artifact-scene", "video_scene_plan");
        assertOldKindRejected("artifact-adaptation", "video_adaptation_plan");
        assertThat(
                        sql(
                                        TARGET_DATABASE,
                                        "SELECT count(*) FROM \"ReviewArtifact\" WHERE id LIKE 'artifact-%'")
                                .getStdout()
                                .strip())
                .isEqualTo("0");
    }

    private static void assertOldKindRejected(String id, String kind) throws Exception {
        var result =
                sql(
                        TARGET_DATABASE,
                        "INSERT INTO \"ReviewArtifact\""
                                + " (id,\"novelId\",kind,\"payloadJson\",\"updatedAt\") VALUES ('"
                                + id
                                + "','retirement-novel','"
                                + kind
                                + "','{}',CURRENT_TIMESTAMP)");
        assertThat(result.getExitCode()).isNotZero();
        assertThat(result.getStderr()).contains("ReviewArtifact_video_episode_target_check");
    }

    private static Path migration(String name) {
        Path path = Path.of("../../scripts/migrations", name);
        if (!Files.exists(path)) path = Path.of("scripts/migrations", name);
        return path;
    }

    private static org.testcontainers.containers.Container.ExecResult retirement()
            throws Exception {
        return POSTGRES.execInContainer(
                "env",
                "PGOPTIONS=-c inkforge.video_legacy_retirement_confirm=" + CONFIRMATION,
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "inkforge",
                "-d",
                TARGET_DATABASE,
                "-f",
                "/tmp/retirement.sql");
    }

    private static org.testcontainers.containers.Container.ExecResult sqlFile(
            String database, String path) throws Exception {
        return POSTGRES.execInContainer(
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "inkforge",
                "-d",
                database,
                "-f",
                path);
    }

    private static org.testcontainers.containers.Container.ExecResult sql(
            String database, String statement) throws Exception {
        return POSTGRES.execInContainer(
                "psql",
                "-At",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "inkforge",
                "-d",
                database,
                "-c",
                statement);
    }
}
