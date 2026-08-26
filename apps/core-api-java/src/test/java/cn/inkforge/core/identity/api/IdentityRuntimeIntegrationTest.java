package cn.inkforge.core.identity.api;

import static cn.inkforge.core.db.generated.Tables.CREDITLEDGER;
import static cn.inkforge.core.db.generated.Tables.USER;
import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.core.CoreApplication;
import cn.inkforge.core.platform.db.CoreDatabase;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
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

@Testcontainers
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
@SpringBootTest(
        classes = CoreApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class IdentityRuntimeIntegrationTest {

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_identity_runtime")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    @Container
    private static final GenericContainer<?> REDIS =
            new GenericContainer<>(DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("DATABASE_URL", IdentityRuntimeIntegrationTest::databaseUrl);
        registry.add("REDIS_URL", () -> "redis://"
                + REDIS.getHost()
                + ":"
                + REDIS.getMappedPort(6379)
                + "/0");
        registry.add("JWT_SECRET", () -> "Java身份运行时测试密钥-长度超过三十二字节-不可用于生产");
        registry.add("ENVIRONMENT", () -> "test");
        registry.add("VIDEO_PREVIEW_ENABLED", () -> "true");
    }

    @BeforeAll
    static void restoreSchema() throws Exception {
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

    @LocalServerPort
    private int port;

    @Autowired
    private CoreDatabase database;

    private final HttpClient client = HttpClient.newHttpClient();
    private String createdUserId;

    @AfterEach
    void cleanup() {
        if (createdUserId != null) {
            database.dsl().deleteFrom(USER).where(USER.ID.eq(createdUserId)).execute();
        }
    }

    @Test
    void 真实PostgreSQLRedis和HTTP必须完成注册登录会话与赠送流水() throws Exception {
        String username = "java_" + UUID.randomUUID().toString().replace("-", "").substring(0, 12);
        HttpResponse<String> registration = post(
                "/api/v1/auth/register",
                "{\"username\":\"" + username + "\",\"password\":\"密码1234\",\"confirmPassword\":\"密码1234\"}");

        assertThat(registration.statusCode()).isEqualTo(201);
        createdUserId = database.dsl().select(USER.ID)
                .from(USER)
                .where(USER.USERNAME.eq(username))
                .fetchSingle(USER.ID);
        assertThat(database.dsl().fetchCount(
                        CREDITLEDGER, CREDITLEDGER.USERID.eq(createdUserId)))
                .isEqualTo(1);
        String cookie = registration.headers()
                .firstValue("set-cookie")
                .orElseThrow()
                .split(";", 2)[0];

        HttpResponse<String> me = get("/api/v1/auth/me", cookie);
        assertThat(me.statusCode()).isEqualTo(200);
        assertThat(me.body()).contains("\"username\":\"" + username + "\"");

        HttpResponse<String> login = post(
                "/api/v1/auth/login",
                "{\"username\":\"" + username.toUpperCase() + "\",\"password\":\"密码1234\"}");
        assertThat(login.statusCode()).isEqualTo(200);

        HttpResponse<String> ready = get("/api/v1/health/ready", null);
        assertThat(ready.statusCode()).isEqualTo(200);
        assertThat(ready.body()).contains(
                "\"database\":\"ok\"",
                "\"database_schema\":\"ok\"",
                "\"redis\":\"ok\"");
    }

    private HttpResponse<String> post(String path, String body) throws Exception {
        return client.send(
                HttpRequest.newBuilder(uri(path))
                        .header("Content-Type", "application/json")
                        .POST(HttpRequest.BodyPublishers.ofString(body))
                        .build(),
                HttpResponse.BodyHandlers.ofString());
    }

    private HttpResponse<String> get(String path, String cookie) throws Exception {
        HttpRequest.Builder request = HttpRequest.newBuilder(uri(path)).GET();
        if (cookie != null) {
            request.header("Cookie", cookie);
        }
        return client.send(request.build(), HttpResponse.BodyHandlers.ofString());
    }

    private URI uri(String path) {
        return URI.create("http://127.0.0.1:" + port + path);
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
