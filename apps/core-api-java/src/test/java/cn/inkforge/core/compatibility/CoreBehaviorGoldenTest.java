package cn.inkforge.core.compatibility;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.core.CoreApplication;
import java.io.InputStream;
import java.net.URI;
import java.nio.file.Path;
import java.util.Map;
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
import org.testcontainers.utility.MountableFile;
import org.testcontainers.utility.DockerImageName;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** 使用语言中立 golden fixture 回归 Java Core 的 HTTP 和数据库最终事实。 */
@Testcontainers
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
@SpringBootTest(classes = CoreApplication.class, webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CoreBehaviorGoldenTest {

    private static final String TEST_PASSWORD = "test-only-password";
    private static final String JWT_SECRET = "跨语言业务回归测试密钥-长度超过三十二字节-不可用于生产";

    @Container
    private static final PostgreSQLContainer DATABASE = new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
            .withDatabaseName("inkforge_java_golden")
            .withUsername("inkforge")
            .withPassword(TEST_PASSWORD);

    @Container
    private static final GenericContainer<?> REDIS = new GenericContainer<>(DockerImageName.parse("redis:7.4-alpine"))
            .withExposedPorts(6379);

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("DATABASE_URL", CoreBehaviorGoldenTest::databaseUrl);
        registry.add("REDIS_URL", () -> "redis://127.0.0.1:" + REDIS.getMappedPort(6379) + "/0");
        registry.add("JWT_SECRET", () -> JWT_SECRET);
        registry.add("ENVIRONMENT", () -> "test");
        registry.add("VIDEO_PREVIEW_ENABLED", () -> "true");
        registry.add("VIDEO_DISPATCH_ENABLED", () -> "false");
        registry.add("UPLOADS_ROOT", () -> Path.of(System.getProperty("java.io.tmpdir"), "inkforge-java-golden").toString());
    }

    @LocalServerPort
    private int javaPort;

    @Autowired
    private ObjectMapper json;

    @BeforeAll
    static void restoreSchema() throws Exception {
        DATABASE.copyFileToContainer(
                MountableFile.forClasspathResource("db/novelwriterdev-schema.sql"),
                "/tmp/novelwriterdev-schema.sql");
        ExecResult result = DATABASE.execInContainer(
                "psql", "-v", "ON_ERROR_STOP=1", "-U", DATABASE.getUsername(),
                "-d", DATABASE.getDatabaseName(), "-f", "/tmp/novelwriterdev-schema.sql");
        assertThat(result.getExitCode()).as(result.getStderr()).isZero();
    }

    @Test
    void 认证小说章节golden必须通过JavaCore() throws Exception {
        assertGolden("auth-novel-chapter.json");
    }

    @Test
    void 中短篇设定和版本golden必须通过JavaCore() throws Exception {
        assertGolden("content-and-version.json");
    }

    private void assertGolden(String fixtureName) throws Exception {
        ObjectNode fixture;
        try (InputStream source = getClass().getResourceAsStream("/behavior-fixtures/" + fixtureName)) {
            if (source == null) throw new IllegalStateException("缺少 Core 行为 golden fixture: " + fixtureName);
            fixture = (ObjectNode) json.readTree(source);
        }
        CoreBehaviorScenarioRunner runner = new CoreBehaviorScenarioRunner(json);
        ObjectNode result = runner.run(
                "Java", URI.create("http://127.0.0.1:" + javaPort), DATABASE, fixture);
        assertThat(result.withArray("responses")).hasSize(fixture.withArray("steps").size());
        assertThat(result.withArray("snapshots")).hasSize(fixture.withArray("snapshotQueries").size());
        JsonNode snapshot = result.path("snapshots").get(0).path("rows").get(0);
        assertThat(snapshot).as("golden fixture 必须返回一条最终业务事实").isNotNull();
        if (fixtureName.equals("auth-novel-chapter.json")) {
            assertSnapshot(snapshot, Map.ofEntries(
                    Map.entry("username", "parity_user_01"),
                    Map.entry("creditBalanceMicros", "1000000000"),
                    Map.entry("ledgerCount", 1),
                    Map.entry("novelName", "差分长篇"),
                    Map.entry("novelSummary", "更新简介"),
                    Map.entry("storyProgress", "第一章目标：建立冲突"),
                    Map.entry("storyLengthProfile", "long_serial"),
                    Map.entry("targetTotalWordCount", 1_000_000),
                    Map.entry("chapterTitle", "未命名章节"),
                    Map.entry("chapterContent", "  第一行\r\n\n最后一行😀  "),
                    Map.entry("chapterProgress", "完整进展\r\n尾部😀"),
                    Map.entry("outlineContent", "")));
        } else {
            assertSnapshot(snapshot, Map.ofEntries(
                    Map.entry("username", "parity_content_01"),
                    Map.entry("novelName", "差分中短篇"),
                    Map.entry("storyLengthProfile", "short_medium"),
                    Map.entry("targetTotalWordCount", 12_000),
                    Map.entry("outlineContent", "第一段😀\n\n完整大纲尾部"),
                    Map.entry("characterName", "  角色甲  "),
                    Map.entry("characterAppearance", "  黑衣😀  "),
                    Map.entry("outlineNodeTitle", "  第一幕  "),
                    Map.entry("outlineNodeContent", "建立人物与冲突"),
                    Map.entry("outlineNodeKind", "stage"),
                    Map.entry("referenceTitle", "  资料标题  "),
                    Map.entry("referenceContent", "  资料第一行\r\n尾部😀  ")));
        }
    }

    private static void assertSnapshot(JsonNode snapshot, Map<String, Object> expected) {
        expected.forEach((name, value) -> {
            JsonNode actual = snapshot.path(name);
            assertThat(actual.isMissingNode() || actual.isNull())
                    .as("golden snapshot 缺少字段: " + name).isFalse();
            if (value instanceof Integer number) assertThat(actual.intValue()).isEqualTo(number);
            else assertThat(actual.textValue()).as(name).isEqualTo(value);
        });
    }

    private static String databaseUrl() {
        return "postgresql://" + DATABASE.getUsername() + ":" + DATABASE.getPassword()
                + "@127.0.0.1:" + DATABASE.getMappedPort(5432) + "/" + DATABASE.getDatabaseName();
    }
}
