package cn.inkforge.core.quality.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.doReturn;

import cn.inkforge.core.CoreApplication;
import cn.inkforge.core.identity.api.IdentityController;
import cn.inkforge.core.identity.application.AuthenticatedUser;
import cn.inkforge.core.identity.application.CurrentUserAccess;
import cn.inkforge.core.identity.domain.InvalidSessionTokenException;
import cn.inkforge.core.identity.domain.SessionTokens;
import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.quality.application.QualityRepository;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.catalog.ExecutionRegistryFixtures;
import cn.inkforge.core.quality.application.QualityExecutionReadiness;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/** 原质量公共 API 使用真实 Spring 装配和 PostgreSQL；只替换认证查验与 Agent 就绪端口。 */
@Testcontainers
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
@SpringBootTest(classes = {CoreApplication.class, DurableQualityRuntimeIntegrationTest.TestPorts.class},
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class DurableQualityRuntimeIntegrationTest {
    private static final String USER = "quality-http-author";
    private static final String NOVEL = "quality-http-novel";
    private static final String CHAPTER = "quality-http-chapter";
    private static final String CHECK = "quality-http-check";
    private static final AtomicBoolean READY = new AtomicBoolean(true);
    @Container
    private static final PostgreSQLContainer POSTGRES = new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
            .withDatabaseName("novelwriterdev").withUsername("inkforge").withPassword("isolated-test-only")
            .withCopyFileToContainer(MountableFile.forClasspathResource("db/novelwriterdev-schema.sql", 0644),
                    "/docker-entrypoint-initdb.d/01-schema.sql")
            .withCopyFileToContainer(MountableFile.forClasspathResource("migrations/20260831_durable_agent_execution.sql", 0644),
                    "/docker-entrypoint-initdb.d/02-durable-agent.sql");

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry properties) {
        properties.add("DATABASE_URL", () -> "postgresql://" + POSTGRES.getUsername() + ":"
                + POSTGRES.getPassword() + "@" + POSTGRES.getHost() + ":" + POSTGRES.getMappedPort(5432)
                + "/" + POSTGRES.getDatabaseName());
        properties.add("REDIS_URL", () -> "false");
        properties.add("JWT_SECRET", () -> "一致性耐久HTTP隔离测试专用密钥-不可用于生产环境");
        properties.add("ENVIRONMENT", () -> "test");
        properties.add("VIDEO_PREVIEW_ENABLED", () -> "false");
        properties.add("DURABLE_AGENT_EXECUTION_SCHEMA_READY", () -> "true");
        properties.add("DURABLE_AGENT_EXECUTION_ROUTE_MODE", () -> "allowlist");
        properties.add("DURABLE_AGENT_EXECUTION_USER_ALLOWLIST", () -> USER);
        properties.add("DURABLE_AGENT_EXECUTION_NOVEL_ALLOWLIST", () -> NOVEL);
    }

    @LocalServerPort private int port;
    @Autowired private CoreDatabase database;
    @Autowired private ObjectMapper json;
    @Autowired private SessionTokens sessions;
    @Autowired private QualityRepository legacyQuality;
    @MockitoSpyBean private CoreSettings settings;
    private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();

    @Test
    void 原质量HTTP入口绑定V2并与写作历史和旧队列隔离且关闭路由后可重放() throws Exception {
        fixture();
        String checkPath = "/api/v1/quality-checks/" + CHECK;
        JsonNode initial = send("GET", checkPath, null, 200);
        assertThat(initial.path("status").asText()).isEqualTo("pending");
        JsonNode skipped = send("PATCH", checkPath, Map.of("status", "skipped", "resetResult", false,
                "expectedUpdatedAt", initial.path("updatedAt").asText()), 200);
        assertThat(skipped.path("status").asText()).isEqualTo("skipped");
        JsonNode reset = send("PATCH", checkPath, Map.of("status", "pending", "resetResult", true,
                "expectedUpdatedAt", skipped.path("updatedAt").asText()), 200);
        assertThat(reset.path("status").asText()).isEqualTo("pending");

        Map<String, Object> request = Map.of("clientRequestId", "quality-http-request-0001", "message", "核对完整正文");
        JsonNode accepted = send("POST", checkPath + "/run", request, 202);
        assertThat(accepted.path("accepted").asBoolean()).isTrue();
        assertThat(accepted.path("checkId").asText()).isEqualTo(CHECK);
        String runId = accepted.path("taskId").asText();
        assertThat(runId).isNotBlank();
        var run = database.dsl().fetchOne("SELECT \"engineVersion\", workflow, \"sourceId\", \"targetId\" "
                + "FROM public.\"WorkflowRun\" WHERE id = ?", runId);
        assertThat(run.get("engineVersion", Integer.class)).isEqualTo(2);
        assertThat(run.get("workflow", String.class)).isEqualTo("quality");
        assertThat(run.get("sourceId", String.class)).isEqualTo(CHECK);
        assertThat(run.get("targetId", String.class)).isEqualTo(CHAPTER);
        JsonNode running = send("GET", checkPath, null, 200);
        assertThat(running.path("status").asText()).isEqualTo("running");
        JsonNode denied = send("PATCH", checkPath, Map.of("status", "skipped", "resetResult", false,
                "expectedUpdatedAt", running.path("updatedAt").asText()), 409);
        assertThat(denied.path("code").asText()).isEqualTo("QUALITY_RUN_ACTIVE");
        assertThat(legacyQuality.listDispatchable(20)).noneMatch(value -> value.runId().equals(runId));

        JsonNode history = send("GET", "/api/v1/writing/runs?novelId=" + NOVEL, null, 200);
        assertThat(history.path("items").size()).isZero();
        send("GET", "/api/v1/writing/runs/" + runId, null, 403);

        // 同一个已装配 Core 服务仅切换新运行路由；幂等重放不能受 route-off 或 Agent 离线影响。
        doReturn(false).when(settings).routesNewDurableAgentRun(USER, NOVEL);
        READY.set(false);
        assertThat(send("POST", checkPath + "/run", request, 202).path("taskId").asText()).isEqualTo(runId);
        assertThat(database.dsl().fetchOne("SELECT count(*) AS n FROM public.\"WorkflowRun\" WHERE \"sourceId\" = ?", CHECK)
                .get("n", Long.class)).isEqualTo(1L);
    }

    private void fixture() {
        LocalDateTime now = LocalDateTime.parse("2026-09-05T19:00:00");
        database.dsl().execute("""
                INSERT INTO public."User"(id,username,"passwordHash","creditBalanceMicros","createdAt","updatedAt")
                VALUES (?,?,?,10000000,?,?)
                """, USER, USER, "隔离测试密码摘要", now, now);
        database.dsl().execute("INSERT INTO public.\"Novel\"(id,name,\"userId\",\"createdAt\",\"updatedAt\") VALUES (?,?,?,?,?)",
                NOVEL, "一致性 HTTP 测试", USER, now, now);
        database.dsl().execute("""
                INSERT INTO public."Chapter"(id,"novelId",title,content,"order",status,"createdAt","updatedAt")
                VALUES (?,?,?,?,1,'review',?,?)
                """, CHAPTER, NOVEL, "第一章", "完整正文😀\n第二段", now, now);
        database.dsl().execute("""
                INSERT INTO public."ChapterQualityCheck"(id,"chapterId",type,title,status,"createdAt","updatedAt")
                VALUES (?,?,'consistency',?,'pending',?,?)
                """, CHECK, CHAPTER, "一致性终检", now, now);
    }

    private JsonNode send(String method, String path, Object body, int expected) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + path))
                .timeout(Duration.ofSeconds(10)).header("Content-Type", "application/json")
                .header("Cookie", IdentityController.COOKIE_NAME + "=" + sessions.create(USER))
                .method(method, body == null ? HttpRequest.BodyPublishers.noBody()
                        : HttpRequest.BodyPublishers.ofString(json.writeValueAsString(body))).build();
        HttpResponse<String> response = http.send(request, HttpResponse.BodyHandlers.ofString());
        assertThat(response.statusCode()).as(response.body()).isEqualTo(expected);
        return json.readTree(response.body());
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class TestPorts {
        @Bean
        CurrentUserAccess currentUserAccess(SessionTokens sessions, CoreDatabase database) {
            return token -> {
                if (token == null) throw new ApiException(401, "UNAUTHENTICATED", "请先登录");
                String userId;
                try { userId = sessions.verify(token); }
                catch (InvalidSessionTokenException exception) { throw new ApiException(401, "UNAUTHENTICATED", "请先登录"); }
                var user = database.dsl().fetchOne("SELECT id,username FROM public.\"User\" WHERE id = ?", userId);
                if (user == null) throw new ApiException(401, "UNAUTHENTICATED", "请先登录");
                return new AuthenticatedUser(user.get("id", String.class), user.get("username", String.class));
            };
        }

        @Bean @Primary
        QualityExecutionReadiness testQualityReadiness() { return READY::get; }

        @Bean @Primary
        ExecutionRegistry testQualityRegistry() {
            return ExecutionRegistryFixtures.qualityOperationEnabled(ExecutionRegistry.Environment.TEST);
        }
    }
}
