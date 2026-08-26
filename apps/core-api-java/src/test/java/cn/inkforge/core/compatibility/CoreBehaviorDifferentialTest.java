package cn.inkforge.core.compatibility;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.core.CoreApplication;
import java.io.InputStream;
import java.net.URI;
import java.nio.file.Path;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.Container.ExecResult;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.DockerImageName;
import org.testcontainers.utility.MountableFile;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

/** 直接运行两种 Core，实现同场景响应和最终数据库事实的严格差分。 */
@Testcontainers
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
@SpringBootTest(
        classes = CoreApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CoreBehaviorDifferentialTest {

    private static final String TEST_PASSWORD = "test-only-password";
    private static final String JWT_SECRET = "跨语言业务差分测试密钥-长度超过三十二字节-不可用于生产";

    @Container
    private static final PostgreSQLContainer JAVA_POSTGRES = postgres("inkforge_java_parity");

    @Container
    private static final PostgreSQLContainer PYTHON_POSTGRES = postgres("inkforge_python_parity");

    @Container
    private static final GenericContainer<?> JAVA_REDIS = redis();

    @Container
    private static final GenericContainer<?> PYTHON_REDIS = redis();

    private static PythonCoreProcess pythonCore;

    @DynamicPropertySource
    static void javaProperties(DynamicPropertyRegistry registry) {
        registry.add("DATABASE_URL", () -> databaseUrl(JAVA_POSTGRES));
        registry.add("REDIS_URL", () -> redisUrl(JAVA_REDIS));
        registry.add("JWT_SECRET", () -> JWT_SECRET);
        registry.add("ENVIRONMENT", () -> "test");
        registry.add("VIDEO_PREVIEW_ENABLED", () -> "true");
        registry.add("VIDEO_DISPATCH_ENABLED", () -> "false");
        registry.add("VIDEO_DISPATCH_NAMESPACE", () -> "parity");
        registry.add("UPLOADS_ROOT", () -> Path.of(
                        System.getProperty("java.io.tmpdir"),
                        "inkforge-java-core-parity")
                .toString());
    }

    @BeforeAll
    static void startIsolatedRuntimes() throws Exception {
        restoreSchema(JAVA_POSTGRES);
        restoreSchema(PYTHON_POSTGRES);
        pythonCore = PythonCoreProcess.start(
                PYTHON_POSTGRES,
                PYTHON_REDIS,
                JWT_SECRET,
                TEST_PASSWORD);
    }

    @AfterAll
    static void stopPythonRuntime() throws Exception {
        if (pythonCore != null) pythonCore.close();
    }

    @LocalServerPort
    private int javaPort;

    @Autowired
    private ObjectMapper json;

    @Test
    void 认证小说章节响应与最终数据库事实必须和Python一致() throws Exception {
        assertFixture("auth-novel-chapter.json");
    }

    @Test
    void 中短篇设定资料与手工版本必须和Python一致() throws Exception {
        assertFixture("content-and-version.json");
    }

    private void assertFixture(String fixtureName) throws Exception {
        ObjectNode fixture;
        try (InputStream source = getClass().getResourceAsStream(
                "/behavior-fixtures/" + fixtureName)) {
            if (source == null) throw new IllegalStateException("缺少 Core 业务差分 fixture");
            fixture = (ObjectNode) json.readTree(source);
        }
        assertThat(fixture.path("schemaVersion").textValue())
                .isEqualTo("inkforge-core-behavior/1.0");

        CoreBehaviorScenarioRunner runner = new CoreBehaviorScenarioRunner(json);
        JsonNode python = runner.run("Python", pythonCore.origin(), PYTHON_POSTGRES, fixture);
        JsonNode java = runner.run(
                "Java",
                URI.create("http://127.0.0.1:" + javaPort),
                JAVA_POSTGRES,
                fixture);

        assertThat(java).isEqualTo(python);
    }

    private static void restoreSchema(PostgreSQLContainer database) throws Exception {
        database.copyFileToContainer(
                MountableFile.forClasspathResource("db/novelwriterdev-schema.sql"),
                "/tmp/novelwriterdev-schema.sql");
        ExecResult result = database.execInContainer(
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                database.getUsername(),
                "-d",
                database.getDatabaseName(),
                "-f",
                "/tmp/novelwriterdev-schema.sql");
        assertThat(result.getExitCode()).as(result.getStderr()).isZero();
    }

    private static PostgreSQLContainer postgres(String databaseName) {
        return new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                .withDatabaseName(databaseName)
                .withUsername("inkforge")
                .withPassword(TEST_PASSWORD);
    }

    private static GenericContainer<?> redis() {
        return new GenericContainer<>(DockerImageName.parse("redis:7.4-alpine"))
                .withExposedPorts(6379);
    }

    private static String databaseUrl(PostgreSQLContainer database) {
        return "postgresql://"
                + database.getUsername()
                + ":"
                + database.getPassword()
                + "@127.0.0.1:"
                + database.getMappedPort(5432)
                + "/"
                + database.getDatabaseName();
    }

    private static String redisUrl(GenericContainer<?> redis) {
        return "redis://127.0.0.1:" + redis.getMappedPort(6379) + "/0";
    }
}
