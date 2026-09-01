package cn.inkforge.core.writing.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.writing.application.EngineIdentityProbe;
import java.time.LocalDateTime;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.Container.ExecResult;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;

@Testcontainers
class JooqEngineIdentityProbeTest {

    private static final LocalDateTime NOW = LocalDateTime.parse("2026-09-01T04:00:00.000");

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("novelwriterdev")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static JooqEngineIdentityProbe probe;

    @BeforeAll
    static void rebuildSchema() throws Exception {
        POSTGRES.copyFileToContainer(
                MountableFile.forClasspathResource("db/novelwriterdev-schema.sql"),
                "/tmp/novelwriterdev-schema.sql");
        POSTGRES.copyFileToContainer(
                MountableFile.forClasspathResource(
                        "migrations/20260831_durable_agent_execution.sql"),
                "/tmp/20260831_durable_agent_execution.sql");
        executeSql("/tmp/novelwriterdev-schema.sql");
        executeSql("/tmp/20260831_durable_agent_execution.sql");
        database = CoreDatabase.connect(PostgresConnectionSettings.parse(databaseUrl()));
        probe = new JooqEngineIdentityProbe(database, true);
    }

    @AfterAll
    static void closeDatabase() {
        if (database != null) database.close();
    }

    @Test
    void V2Owner可识别非Owner固定拒绝且未命中交给V1() {
        Fixture owner = fixture("engine-owner");
        Fixture other = fixture("engine-other");
        insertV2Run(owner, "owned-v2");

        assertThat(probe.probe(owner.userId(), "owned-v2"))
                .isEqualTo(EngineIdentityProbe.EngineIdentity.V2);
        assertThat(probe.probe(owner.userId(), "missing-or-v1"))
                .isEqualTo(EngineIdentityProbe.EngineIdentity.V1_OR_MISSING);
        assertThatThrownBy(() -> probe.probe(other.userId(), "owned-v2"))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(403);
                    assertThat(error.code()).isEqualTo("WRITING_TASK_FORBIDDEN");
                });
    }

    @Test
    void 同ID存在他人V2时禁止回退到本人V1() {
        Fixture v1Owner = fixture("engine-collision-v1");
        Fixture v2Owner = fixture("engine-collision-v2");
        insertV1Task(v1Owner, "identity-collision");
        insertV2Run(v2Owner, "identity-collision");

        assertThatThrownBy(() -> probe.probe(v1Owner.userId(), "identity-collision"))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(403);
                    assertThat(error.code()).isEqualTo("WRITING_TASK_FORBIDDEN");
                });
    }

    @Test
    void 迁移前配置固定判为V1且不要求V2身份() {
        JooqEngineIdentityProbe legacyOnly = new JooqEngineIdentityProbe(database, false);

        assertThat(legacyOnly.probe("any-user", "owned-v2"))
                .isEqualTo(EngineIdentityProbe.EngineIdentity.V1_OR_MISSING);
    }

    private static Fixture fixture(String prefix) {
        String userId = prefix + "-user";
        String novelId = prefix + "-novel";
        String chapterId = prefix + "-chapter";
        database.dsl().execute(
                """
                INSERT INTO public."User" (
                  id, username, "passwordHash", "creditBalanceMicros", "createdAt", "updatedAt"
                ) VALUES (?, ?, 'test', 1000000, ?, ?)
                """,
                userId,
                userId,
                NOW,
                NOW);
        database.dsl().execute(
                """
                INSERT INTO public."Novel" (id, name, "userId", "createdAt", "updatedAt")
                VALUES (?, ?, ?, ?, ?)
                """,
                novelId,
                prefix,
                userId,
                NOW,
                NOW);
        database.dsl().execute(
                """
                INSERT INTO public."Chapter" (
                  id, "novelId", title, content, "order", status, "createdAt", "updatedAt"
                ) VALUES (?, ?, '第一章', '正文', 1, 'drafting', ?, ?)
                """,
                chapterId,
                novelId,
                NOW,
                NOW);
        return new Fixture(userId, novelId, chapterId);
    }

    private static void insertV1Task(Fixture fixture, String taskId) {
        database.dsl().execute(
                """
                INSERT INTO public."WritingTask" (
                  id, "novelId", "chapterId", phase, "targetWordCount", "selectedAgents",
                  "conversationHistory", "createdAt", "updatedAt"
                ) VALUES (?, ?, ?, 'active', 1000, '写作', '[]', ?, ?)
                """,
                taskId,
                fixture.novelId(),
                fixture.chapterId(),
                NOW,
                NOW);
    }

    private static void insertV2Run(Fixture fixture, String runId) {
        database.dsl().execute(
                """
                INSERT INTO public."WorkflowRun" (
                  id, "novelId", "chapterId", "userId", kind, status, input,
                  "sourceType", "sourceId", "createdAt", "updatedAt", "engineVersion",
                  workflow, operation, "operationCatalogVersion", "idempotencyKey",
                  "requestHash", "targetType", "targetId", "budgetJson", "modelPolicyJson",
                  "lastEventSequence", revision
                ) VALUES (
                  ?, ?, ?, ?, 'chapter_generation', 'pending', '{}', 'chapter', ?, ?, ?, 2,
                  'long_serial', 'rewrite_chapter_selection', 'catalog-test', ?, ?,
                  'chapter', ?, '{}', '{}', 0, 1
                )
                """,
                runId,
                fixture.novelId(),
                fixture.chapterId(),
                fixture.userId(),
                fixture.chapterId(),
                NOW,
                NOW,
                "request-" + runId,
                "a".repeat(64),
                fixture.chapterId());
    }

    private static void executeSql(String path) throws Exception {
        ExecResult result = POSTGRES.execInContainer(
                "psql",
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
                + "@"
                + POSTGRES.getHost()
                + ":"
                + POSTGRES.getFirstMappedPort()
                + "/"
                + POSTGRES.getDatabaseName();
    }

    private record Fixture(String userId, String novelId, String chapterId) {}
}
