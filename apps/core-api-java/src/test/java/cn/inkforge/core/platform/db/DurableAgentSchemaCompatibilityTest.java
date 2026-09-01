package cn.inkforge.core.platform.db;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.Statement;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicLong;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.Container.ExecResult;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;

@Testcontainers
class DurableAgentSchemaCompatibilityTest {

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("novelwriterdev")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    @BeforeAll
    static void restorePreMigrationSchema() throws Exception {
        POSTGRES.copyFileToContainer(
                MountableFile.forClasspathResource("db/novelwriterdev-schema.sql"),
                "/tmp/novelwriterdev-schema.sql");
        POSTGRES.copyFileToContainer(
                MountableFile.forClasspathResource(
                        "migrations/20260831_durable_agent_execution.sql"),
                "/tmp/20260831_durable_agent_execution.sql");
        executeSql("/tmp/novelwriterdev-schema.sql");
    }

    @Test
    void 同一镜像必须精确接受在线迁移前后结构且拒绝任意额外漂移() throws Exception {
        SchemaContract pre = SchemaContracts.loadPreDurableAgentV2();
        SchemaContract post = SchemaContracts.loadPostDurableAgentV2();
        AtomicLong monotonicNanos = new AtomicLong();
        try (CoreDatabase database = CoreDatabase.connect(
                PostgresConnectionSettings.parse(databaseUrl()))) {
            DatabaseReadiness readiness = new DatabaseReadiness(
                    database,
                    SchemaProfile.FULL,
                    monotonicNanos::get,
                    Duration.ofSeconds(30),
                    Duration.ofSeconds(5));

            assertThat(readiness.checkSchema()).isTrue();
            assertAllProfilesMatchOneExactContract(pre.fingerprint());
            assertThatThrownBy(() -> new DurableAgentSchemaGate(database, SchemaProfile.FULL))
                    .isInstanceOf(IllegalStateException.class)
                    .hasMessageContaining("未精确命中迁移后契约");

            executeSql("/tmp/20260831_durable_agent_execution.sql");
            monotonicNanos.addAndGet(Duration.ofSeconds(31).toNanos());

            // 这是迁移前已经创建的同一 readiness 实例；缓存过期后必须精确识别迁移后完整结构。
            assertThat(readiness.checkSchema()).isTrue();
            assertAllProfilesMatchOneExactContract(post.fingerprint());
            assertThat(new DurableAgentSchemaGate(database, SchemaProfile.FULL).fingerprint())
                    .isEqualTo(post.fingerprint());

            try (Connection connection = DriverManager.getConnection(
                            POSTGRES.getJdbcUrl(),
                            POSTGRES.getUsername(),
                            POSTGRES.getPassword());
                    Statement statement = connection.createStatement()) {
                SchemaVerificationResult preOnly =
                        new SchemaVerifier(pre, SchemaProfile.FULL)
                                .verify(connection, "public");
                assertThat(preOnly.ready()).isFalse();
                statement.execute(
                        "ALTER TABLE public.\"WorkflowRun\" ADD COLUMN \"unexpectedDrift\" text");
                try {
                    SchemaVerificationResult drift = new SchemaVerifier(
                                    SchemaContracts.loadBundled(), SchemaProfile.FULL)
                            .verify(connection, "public");
                    assertThat(drift.ready()).isFalse();
                    assertThat(drift.diffs())
                            .extracting(SchemaDiff::path)
                            .contains("tables.WorkflowRun.columns.unexpectedDrift");
                } finally {
                    statement.execute(
                            "ALTER TABLE public.\"WorkflowRun\" DROP COLUMN \"unexpectedDrift\"");
                }
            }
        }
    }

    private static void assertAllProfilesMatchOneExactContract(String expectedFullFingerprint)
            throws Exception {
        try (Connection connection = DriverManager.getConnection(
                POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword())) {
            for (SchemaProfile profile : SchemaProfile.values()) {
                SchemaVerificationResult result = new SchemaVerifier(
                                SchemaContracts.loadBundled(), profile)
                        .verify(connection, "public");
                assertThat(result.ready()).as(profile.name()).isTrue();
                assertThat(result.diffs()).as(profile.name()).isEmpty();
                if (profile == SchemaProfile.FULL) {
                    assertThat(result.fingerprint()).isEqualTo(expectedFullFingerprint);
                }
            }
        }
    }

    private static void executeSql(String path) throws Exception {
        ExecResult result = POSTGRES.execInContainer(
                "psql",
                "-X",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                POSTGRES.getUsername(),
                "-d",
                POSTGRES.getDatabaseName(),
                "-f",
                path);
        assertThat(result.getExitCode()).as(result.getStderr()).isZero();
    }

    private static String databaseUrl() {
        return "postgresql://"
                + POSTGRES.getUsername()
                + ":"
                + POSTGRES.getPassword()
                + "@127.0.0.1:"
                + POSTGRES.getMappedPort(5432)
                + "/"
                + POSTGRES.getDatabaseName();
    }
}
