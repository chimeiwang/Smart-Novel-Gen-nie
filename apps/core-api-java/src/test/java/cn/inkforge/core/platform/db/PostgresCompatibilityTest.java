package cn.inkforge.core.platform.db;

import static cn.inkforge.core.db.generated.Tables.USER;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Savepoint;
import java.sql.Statement;
import java.time.LocalDateTime;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.Container.ExecResult;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;

@Testcontainers
class PostgresCompatibilityTest {

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_java_test")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    @BeforeAll
    static void 重建从开发库只读导出的完整结构() throws Exception {
        POSTGRES.copyFileToContainer(
                MountableFile.forClasspathResource("db/novelwriterdev-schema.sql"),
                "/tmp/novelwriterdev-schema.sql");
        ExecResult result = POSTGRES.execInContainer(
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                POSTGRES.getUsername(),
                "-d",
                POSTGRES.getDatabaseName(),
                "-f",
                "/tmp/novelwriterdev-schema.sql");
        assertThat(result.getExitCode()).as(result.getStderr()).isZero();
    }

    @Test
    void 数据库测试必须使用PostgreSQL14与pgvector() throws Exception {
        try (Connection connection = DriverManager.getConnection(
                        POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword());
                Statement statement = connection.createStatement()) {
            connection.setAutoCommit(false);
            try {
                statement.execute("CREATE TYPE \"JavaProbeStatus\" AS ENUM ('ready', 'failed')");
                statement.execute(
                        "CREATE TABLE \"JavaSchemaProbe\" ("
                                + "\"id\" TEXT PRIMARY KEY, "
                                + "\"createdAt\" TIMESTAMP(3) NOT NULL, "
                                + "\"embedding\" vector(3) NOT NULL, "
                                + "\"status\" \"JavaProbeStatus\" NOT NULL)"
                );
                statement.execute(
                        "CREATE TABLE \"JavaCompositeParent\" ("
                                + "id text NOT NULL, owner text NOT NULL, UNIQUE (id, owner))");
                statement.execute(
                        "CREATE TABLE \"JavaCompositeChild\" ("
                                + "id text PRIMARY KEY, parent_id text NOT NULL, owner text NOT NULL, "
                                + "FOREIGN KEY (parent_id, owner) "
                                + "REFERENCES \"JavaCompositeParent\" (id, owner))");
                statement.execute(
                        "CREATE TABLE \"JavaPartialProbe\" (scope text NOT NULL, active boolean NOT NULL)");
                statement.execute(
                        "CREATE UNIQUE INDEX \"JavaPartialProbe_active_key\" "
                                + "ON \"JavaPartialProbe\" (scope) WHERE active");

                try (ResultSet result = statement.executeQuery(
                        "SELECT current_setting('server_version_num')::integer, "
                                + "(SELECT extversion FROM pg_extension WHERE extname = 'vector'), "
                                + "format_type(a.atttypid, a.atttypmod) "
                                + "FROM pg_attribute a "
                                + "JOIN pg_class c ON c.oid = a.attrelid "
                                + "WHERE c.relname = 'JavaSchemaProbe' AND a.attname = 'embedding'")) {
                    assertThat(result.next()).isTrue();
                    assertThat(result.getInt(1)).isBetween(140_000, 149_999);
                    assertThat(result.getString(2)).isNotBlank();
                    assertThat(result.getString(3)).isEqualTo("vector(3)");
                }

                statement.execute("INSERT INTO \"JavaCompositeParent\" VALUES ('parent', 'owner-a')");
                Savepoint foreignKeyProbe = connection.setSavepoint();
                assertThatThrownBy(() -> statement.execute(
                                "INSERT INTO \"JavaCompositeChild\" VALUES ('bad', 'parent', 'owner-b')"))
                        .isInstanceOf(SQLException.class)
                        .extracting(error -> ((SQLException) error).getSQLState())
                        .isEqualTo("23503");
                connection.rollback(foreignKeyProbe);
                statement.execute(
                        "INSERT INTO \"JavaCompositeChild\" VALUES ('good', 'parent', 'owner-a')");

                statement.execute("INSERT INTO \"JavaPartialProbe\" VALUES ('scope-a', true)");
                Savepoint partialIndexProbe = connection.setSavepoint();
                assertThatThrownBy(() -> statement.execute(
                                "INSERT INTO \"JavaPartialProbe\" VALUES ('scope-a', true)"))
                        .isInstanceOf(SQLException.class)
                        .extracting(error -> ((SQLException) error).getSQLState())
                        .isEqualTo("23505");
                connection.rollback(partialIndexProbe);
                statement.execute("INSERT INTO \"JavaPartialProbe\" VALUES ('scope-a', false)");
                statement.execute("INSERT INTO \"JavaPartialProbe\" VALUES ('scope-a', false)");
            } finally {
                connection.rollback();
            }
        }
    }

    @Test
    void 隔离容器必须完整还原冻结结构() throws Exception {
        try (Connection connection = DriverManager.getConnection(
                        POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword());
                Statement statement = connection.createStatement();
                ResultSet result = statement.executeQuery(
                        "SELECT "
                                + "(SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                                + "WHERE n.nspname = 'public' AND c.relkind = 'r'), "
                                + "(SELECT count(DISTINCT t.oid) FROM pg_type t "
                                + "JOIN pg_namespace n ON n.oid = t.typnamespace "
                                + "JOIN pg_enum e ON e.enumtypid = t.oid WHERE n.nspname = 'public'), "
                                + "to_regclass('public.\"VideoEpisodeExport\"') IS NOT NULL, "
                                + "to_regclass('public.\"WritingTask\"') IS NOT NULL")) {
            assertThat(result.next()).isTrue();
            assertThat(result.getInt(1)).isEqualTo(86);
            assertThat(result.getInt(2)).isEqualTo(22);
            assertThat(result.getBoolean(3)).isTrue();
            assertThat(result.getBoolean(4)).isTrue();
        }
    }

    @Test
    void Java只读结构检查必须与Python契约逐字段一致() throws Exception {
        try (Connection connection = DriverManager.getConnection(
                POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword())) {
            SchemaVerificationResult result = new SchemaVerifier(SchemaContract.load(readContract()))
                    .verify(connection, "public");

            assertThat(result.ready()).isTrue();
            assertThat(result.fingerprint()).isEqualTo(SchemaContract.load(readContract()).fingerprint());
            assertThat(result.diffs()).isEmpty();
        }
    }

    @Test
    void 镜像结构守卫命令必须只输出实时指纹() throws Exception {
        String databaseUrl = "postgresql://"
                + POSTGRES.getUsername()
                + ":"
                + POSTGRES.getPassword()
                + "@127.0.0.1:"
                + POSTGRES.getMappedPort(5432)
                + "/"
                + POSTGRES.getDatabaseName();
        ByteArrayOutputStream stdout = new ByteArrayOutputStream();
        ByteArrayOutputStream stderr = new ByteArrayOutputStream();

        int status = SchemaGuardCommand.run(
                Map.of(
                        "DATABASE_URL", databaseUrl,
                        "VIDEO_PREVIEW_ENABLED", "true",
                        "PHONE_AUTH_ENABLED", "true",
                        "PHONE_AUTH_SEND_ENABLED", "true"),
                new PrintStream(stdout, true, StandardCharsets.UTF_8),
                new PrintStream(stderr, true, StandardCharsets.UTF_8));

        assertThat(status).isZero();
        assertThat(stdout.toString(StandardCharsets.UTF_8))
                .isEqualTo(SchemaContract.load(readContract()).fingerprint() + System.lineSeparator());
        assertThat(stderr.toString(StandardCharsets.UTF_8)).isEmpty();
    }

    @Test
    void 镜像结构守卫兼容模式必须先校验完整契约再输出v1指纹() throws Exception {
        String databaseUrl = "postgresql://"
                + POSTGRES.getUsername()
                + ":"
                + POSTGRES.getPassword()
                + "@127.0.0.1:"
                + POSTGRES.getMappedPort(5432)
                + "/"
                + POSTGRES.getDatabaseName();
        ByteArrayOutputStream stdout = new ByteArrayOutputStream();
        ByteArrayOutputStream stderr = new ByteArrayOutputStream();

        int status = SchemaGuardCommand.run(
                new String[] {"--compatibility-fingerprint-v1"},
                Map.of(
                        "DATABASE_URL", databaseUrl,
                        "VIDEO_PREVIEW_ENABLED", "true",
                        "PHONE_AUTH_ENABLED", "true",
                        "PHONE_AUTH_SEND_ENABLED", "true"),
                new PrintStream(stdout, true, StandardCharsets.UTF_8),
                new PrintStream(stderr, true, StandardCharsets.UTF_8));

        assertThat(status).isZero();
        assertThat(stdout.toString(StandardCharsets.UTF_8))
                .isEqualTo(
                        SchemaGuardCommand.compatibilityFingerprintV1(
                                        SchemaContract.load(readContract()))
                                + System.lineSeparator());
        assertThat(stderr.toString(StandardCharsets.UTF_8)).isEmpty();
    }

    @Test
    void 任意结构漂移都必须拒绝就绪并给出字段路径() throws Exception {
        try (Connection connection = DriverManager.getConnection(
                        POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword());
                Statement statement = connection.createStatement()) {
            statement.execute("ALTER TABLE \"User\" ADD COLUMN \"javaDriftProbe\" text");
            try {
                SchemaVerificationResult result = new SchemaVerifier(SchemaContract.load(readContract()))
                        .verify(connection, "public");

                assertThat(result.ready()).isFalse();
                assertThat(result.diffs())
                        .extracting(SchemaDiff::path)
                        .contains("tables.User.columns.javaDriftProbe");
            } finally {
                statement.execute("ALTER TABLE \"User\" DROP COLUMN \"javaDriftProbe\"");
            }
        }
    }

    @Test
    void 受限Hikari连接池与jooq必须复用同一真实结构() {
        String databaseUrl = "postgresql://"
                + POSTGRES.getUsername()
                + ":"
                + POSTGRES.getPassword()
                + "@127.0.0.1:"
                + POSTGRES.getMappedPort(5432)
                + "/"
                + POSTGRES.getDatabaseName();
        try (CoreDatabase database = CoreDatabase.connect(PostgresConnectionSettings.parse(databaseUrl))) {
            DatabaseReadiness readiness = new DatabaseReadiness(database, SchemaProfile.FULL);

            assertThat(database.dsl().fetchValue("SELECT 1", Integer.class)).isEqualTo(1);
            assertThat(readiness.checkConnection()).isTrue();
            assertThat(readiness.checkSchema()).isTrue();
            assertThat(readiness.checkSchema()).isTrue();
        }
    }

    @Test
    void 跨模块嵌套工作必须加入同一外层事务并整体回滚() {
        String databaseUrl = "postgresql://"
                + POSTGRES.getUsername()
                + ":"
                + POSTGRES.getPassword()
                + "@127.0.0.1:"
                + POSTGRES.getMappedPort(5432)
                + "/"
                + POSTGRES.getDatabaseName();
        try (CoreDatabase database = CoreDatabase.connect(PostgresConnectionSettings.parse(databaseUrl))) {
            assertThatThrownBy(() -> database.transactionResult(outer -> {
                        outer.insertInto(USER)
                                .set(USER.ID, "nested-uow-user-1")
                                .set(USER.USERNAME, "nested-uow-user-1")
                                .set(USER.PASSWORDHASH, "test")
                                .set(USER.CREDITBALANCEMICROS, 0L)
                                .set(USER.CREATEDAT, LocalDateTime.of(2026, 8, 25, 0, 0))
                                .set(USER.UPDATEDAT, LocalDateTime.of(2026, 8, 25, 0, 0))
                                .execute();
                        database.transactionResult(inner -> {
                            assertThat(inner.fetchCount(
                                            USER, USER.ID.eq("nested-uow-user-1")))
                                    .isEqualTo(1);
                            inner.insertInto(USER)
                                    .set(USER.ID, "nested-uow-user-2")
                                    .set(USER.USERNAME, "nested-uow-user-2")
                                    .set(USER.PASSWORDHASH, "test")
                                    .set(USER.CREDITBALANCEMICROS, 0L)
                                    .set(USER.CREATEDAT, LocalDateTime.of(2026, 8, 25, 0, 0))
                                    .set(USER.UPDATEDAT, LocalDateTime.of(2026, 8, 25, 0, 0))
                                    .execute();
                            return null;
                        });
                        throw new IllegalStateException("触发外层回滚");
                    }))
                    .isInstanceOf(IllegalStateException.class);
            assertThat(database.dsl().fetchCount(
                            USER, USER.ID.in("nested-uow-user-1", "nested-uow-user-2")))
                    .isZero();
        }
    }

    private JsonNode readContract() throws Exception {
        try (var input = getClass().getResourceAsStream("/db/schema-contract.json")) {
            if (input == null) {
                throw new IllegalStateException("测试资源缺少 schema-contract.json");
            }
            return new ObjectMapper().readTree(input);
        }
    }
}
