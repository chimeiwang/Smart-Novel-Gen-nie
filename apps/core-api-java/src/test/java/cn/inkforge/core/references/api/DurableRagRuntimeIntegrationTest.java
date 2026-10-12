package cn.inkforge.core.references.api;

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
import cn.inkforge.core.references.application.RagIndexSubmitter;
import cn.inkforge.core.references.application.RagSubmissionException;
import cn.inkforge.core.references.domain.RagDispatchStatus;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.catalog.ExecutionRegistryFixtures;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
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

/** 原资料公共接口使用真实 Spring/PostgreSQL，仅用失败可控的旧投递端口取代 Agent 网络。 */
@Testcontainers
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
@SpringBootTest(classes = {CoreApplication.class, DurableRagRuntimeIntegrationTest.TestPorts.class},
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class DurableRagRuntimeIntegrationTest {
    private static final String USER = "rag-http-user";
    private static final String NOVEL = "rag-http-novel";
    private static final AtomicInteger LEGACY_CALLS = new AtomicInteger();
    private static final AtomicBoolean LEGACY_FAILS = new AtomicBoolean(true);
    @Container
    private static final PostgreSQLContainer POSTGRES = new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
            .withDatabaseName("novelwriterdev").withUsername("inkforge").withPassword("isolated-test-only")
            .withCopyFileToContainer(MountableFile.forClasspathResource("db/novelwriterdev-schema.sql", 0644),
                    "/docker-entrypoint-initdb.d/01-schema.sql")
            .withCopyFileToContainer(MountableFile.forClasspathResource("migrations/20260831_durable_agent_execution.sql", 0644),
                    "/docker-entrypoint-initdb.d/02-durable.sql");

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry properties) {
        properties.add("DATABASE_URL", () -> "postgresql://" + POSTGRES.getUsername() + ":" + POSTGRES.getPassword()
                + "@" + POSTGRES.getHost() + ":" + POSTGRES.getMappedPort(5432) + "/" + POSTGRES.getDatabaseName());
        properties.add("REDIS_URL", () -> "false");
        properties.add("JWT_SECRET", () -> "资料索引HTTP隔离测试专用密钥-不可用于生产环境");
        properties.add("ENVIRONMENT", () -> "test");
        properties.add("VIDEO_PREVIEW_ENABLED", () -> "false");
        properties.add("RAG_INDEX_ENABLED", () -> "true");
        properties.add("RAG_EMBEDDING_MODEL", () -> "e2e-embedding-vector-v1");
        properties.add("RAG_EMBEDDING_BASE_URL", () -> "http://e2e-control:8090");
        properties.add("DURABLE_AGENT_EXECUTION_SCHEMA_READY", () -> "true");
        properties.add("DURABLE_AGENT_EXECUTION_ROUTE_MODE", () -> "allowlist");
        properties.add("DURABLE_AGENT_EXECUTION_USER_ALLOWLIST", () -> USER);
        properties.add("DURABLE_AGENT_EXECUTION_NOVEL_ALLOWLIST", () -> NOVEL);
    }

    @LocalServerPort private int port;
    @Autowired private CoreDatabase database;
    @Autowired private ObjectMapper json;
    @Autowired private SessionTokens sessions;
    @MockitoSpyBean private CoreSettings settings;
    private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();

    @Test
    void 原CRUD和reindex保持响应并固定新旧代次且自动网络失败不撤销正文() throws Exception {
        LocalDateTime now = LocalDateTime.parse("2026-09-05T23:00:00");
        database.dsl().execute("INSERT INTO public.\"User\"(id,username,\"passwordHash\",\"createdAt\",\"updatedAt\") VALUES (?,?,?,?,?)",
                USER, USER, "隔离测试摘要", now, now);
        database.dsl().execute("INSERT INTO public.\"Novel\"(id,name,\"userId\",\"createdAt\",\"updatedAt\") VALUES (?,?,?,?,?)",
                NOVEL, "资料 HTTP 测试", USER, now, now);
        String base = "/api/v1/novels/" + NOVEL + "/references";
        JsonNode created = send("POST", base, Map.of("clientRequestId", "rag-http-create-0001", "title", "标题",
                "type", "note", "content", "\uFEFF甲😀\r\n乙\n"), 201);
        String reference = created.get("id").asText();
        String path = base + "/" + reference;
        assertThat(created.get("ragStatus").asText()).isEqualTo("disabled");
        assertThat(runCount(reference)).isEqualTo(1);
        assertThat(LEGACY_CALLS).hasValue(0);
        doReturn(false).when(settings).routesNewDurableAgentRun(USER, NOVEL);
        assertThat(send("POST", path + "/reindex", Map.of("expectedContentHash", created.get("contentHash").asText()), 202)
                .get("accepted").asBoolean()).isTrue();
        assertThat(runCount(reference)).isEqualTo(1);
        assertThat(LEGACY_CALLS).hasValue(0);
        JsonNode titled = send("PATCH", path, Map.of("expectedUpdatedAt", created.get("updatedAt").asText(), "title", "新标题"), 200);
        assertThat(runCount(reference)).isEqualTo(1);
        JsonNode changed = send("PATCH", path, Map.of("expectedUpdatedAt", titled.get("updatedAt").asText(), "content", "完整新正文"), 200);
        assertThat(changed.get("content").asText()).isEqualTo("完整新正文");
        assertThat(changed.get("ragStatus").asText()).isEqualTo("disabled");
        assertThat(LEGACY_CALLS.get()).isGreaterThanOrEqualTo(1);
        assertThat(send("POST", path + "/reindex", Map.of("expectedContentHash", changed.get("contentHash").asText()), 503)
                .get("code").asText()).isEqualTo("RAG_INDEX_SUBMIT_FAILED");
        assertThat(send("GET", base, null, 200).get(0).get("content").asText()).isEqualTo("完整新正文");
        doReturn(true).when(settings).routesNewDurableAgentRun(USER, NOVEL);
        send("POST", path + "/reindex", Map.of("expectedContentHash", changed.get("contentHash").asText()), 503);
        assertThat(runCount(reference)).isEqualTo(1);
        LEGACY_FAILS.set(false);
        send("POST", path + "/reindex", Map.of("expectedContentHash", changed.get("contentHash").asText()), 202);
        JsonNode latest = send("PATCH", path, Map.of("expectedUpdatedAt", changed.get("updatedAt").asText(), "content", "第三份完整正文"), 200);
        assertThat(runCount(reference)).isEqualTo(2);
        int legacyBeforeLocal = LEGACY_CALLS.get();
        JsonNode empty = send("POST", base, Map.of("clientRequestId", "rag-http-empty-0001", "title", "空资料", "type", "note", "content", ""), 201);
        assertThat(empty.get("ragStatus").asText()).isEqualTo("ready");
        assertThat(runCount(empty.get("id").asText())).isZero();
        String hugeContent = "甲".repeat(1800 * 64 + 1);
        JsonNode huge = send("POST", base, Map.of("clientRequestId", "rag-http-huge-0001", "title", "完整大资料", "type", "note", "content", hugeContent), 201);
        assertThat(huge.get("ragStatus").asText()).isEqualTo("failed");
        assertThat(huge.get("content").asText()).isEqualTo(hugeContent);
        assertThat(runCount(huge.get("id").asText())).isZero();
        assertThat(LEGACY_CALLS.get()).isEqualTo(legacyBeforeLocal);
        send("DELETE", path, Map.of("expectedUpdatedAt", latest.get("updatedAt").asText()), 200);
    }

    private int runCount(String reference) {
        return database.dsl().fetchOne("SELECT count(*) AS n FROM public.\"WorkflowRun\" WHERE \"sourceId\"=?", reference).get("n", Integer.class);
    }

    private JsonNode send(String method, String path, Object body, int status) throws Exception {
        var request = HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + path)).timeout(Duration.ofSeconds(10))
                .header("Cookie", IdentityController.COOKIE_NAME + "=" + sessions.create(USER)).header("Content-Type", "application/json")
                .method(method, body == null ? HttpRequest.BodyPublishers.noBody()
                        : HttpRequest.BodyPublishers.ofString(json.writeValueAsString(body))).build();
        var response = http.send(request, HttpResponse.BodyHandlers.ofString());
        assertThat(response.statusCode()).as(response.body()).isEqualTo(status);
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
                var user = database.dsl().fetchOne("SELECT id,username FROM public.\"User\" WHERE id=?", userId);
                if (user == null) throw new ApiException(401, "UNAUTHENTICATED", "请先登录");
                return new AuthenticatedUser(user.get("id", String.class), user.get("username", String.class));
            };
        }
        @Bean(name = "ragAgentSubmitter")
        RagIndexSubmitter oldRagSubmitter() {
            return (user, novel, reference, hash, generation) -> {
                LEGACY_CALLS.incrementAndGet();
                if (LEGACY_FAILS.get()) throw new RagSubmissionException("ISOLATED_SUBMIT_FAILED");
                return RagDispatchStatus.QUEUED;
            };
        }
        @Bean @Primary
        ExecutionRegistry testRagRegistry() { return ExecutionRegistryFixtures.ragOperationEnabled(ExecutionRegistry.Environment.TEST); }
    }
}
