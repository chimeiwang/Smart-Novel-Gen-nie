package cn.inkforge.core.styles.api;

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
import cn.inkforge.core.styles.application.PortraitRunSubmitter;
import cn.inkforge.core.styles.application.StylePortraitExecutionReadiness;
import cn.inkforge.core.styles.application.StyleRepository;
import cn.inkforge.core.styles.domain.PortraitDispatchStatus;
import cn.inkforge.core.workflows.application.WorkflowStylePortraitCompletion;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.catalog.ExecutionRegistryFixtures;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.AfterAll;
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

/** 原公共 HTTP、真实上传存储和 PostgreSQL 装配；Agent 仅替换就绪与旧投递边界。 */
@Testcontainers
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
@SpringBootTest(classes = {CoreApplication.class, DurableStylePortraitRuntimeIntegrationTest.TestPorts.class},
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class DurableStylePortraitRuntimeIntegrationTest {
    private static final String USER = "style-v2-http-author";
    private static final Path UPLOADS = Path.of(System.getProperty("java.io.tmpdir"), "inkforge-style-v2-http-" + UUID.randomUUID());
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
        properties.add("JWT_SECRET", () -> "文风画像HTTP隔离测试专用密钥-不可用于生产环境");
        properties.add("ENVIRONMENT", () -> "test");
        properties.add("UPLOADS_ROOT", UPLOADS::toString);
        properties.add("VIDEO_PREVIEW_ENABLED", () -> "false");
        properties.add("DURABLE_AGENT_EXECUTION_SCHEMA_READY", () -> "true");
        properties.add("DURABLE_AGENT_EXECUTION_ROUTE_MODE", () -> "allowlist");
        properties.add("DURABLE_AGENT_EXECUTION_USER_ALLOWLIST", () -> USER);
        properties.add("DURABLE_AGENT_EXECUTION_NOVEL_ALLOWLIST", () -> "unused-novel-allowlist");
    }

    @AfterAll
    static void cleanupUploads() throws Exception {
        if (!Files.exists(UPLOADS)) return;
        try (var paths = Files.walk(UPLOADS)) {
            for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) Files.deleteIfExists(path);
        }
    }

    @LocalServerPort private int port;
    @Autowired private CoreDatabase database;
    @Autowired private ObjectMapper json;
    @Autowired private SessionTokens sessions;
    @Autowired private StyleRepository repository;
    @Autowired private WorkflowStylePortraitCompletion completion;
    @MockitoSpyBean private CoreSettings settings;
    private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();

    @Test
    void 原文风HTTP入口无小说创建V2并保留上传编辑双读查询及删除语义() throws Exception {
        LocalDateTime now = LocalDateTime.parse("2026-09-05T21:00:00");
        database.dsl().execute("""
                INSERT INTO public."User"(id,username,"passwordHash","creditBalanceMicros","createdAt","updatedAt")
                VALUES (?,?,?,10000000,?,?)
                """, USER, USER, "隔离测试摘要", now, now);
        String styleId = send("POST", "/api/v1/styles", Map.of("name", "耐久画像"), 201).get("id").asText();
        String base = "/api/v1/styles/" + styleId;
        JsonNode uploaded = upload(base + "/references", "\uFEFF甲😀\r\n乙\n");
        String referenceId = uploaded.get("id").asText();
        assertThat(uploaded.get("charCount").asInt()).isEqualTo(4);
        String runId = send("POST", base + "/portrait", null, 202).get("taskId").asText();
        var run = database.dsl().fetchOne("SELECT \"engineVersion\", \"novelId\", \"chapterId\", \"sourceId\" "
                + "FROM public.\"WorkflowRun\" WHERE id = ?", runId);
        assertThat(run.get("engineVersion", Integer.class)).isEqualTo(2);
        assertThat(run.get("novelId")).isNull();
        assertThat(run.get("chapterId")).isNull();
        assertThat(run.get("sourceId", String.class)).isEqualTo(styleId);
        assertThat(database.dsl().fetchOne("SELECT count(*) AS n FROM public.\"StylePortraitTask\" WHERE \"styleId\" = ?", styleId)
                .get("n", Long.class)).isZero();
        assertThat(repository.listReconcilable(100, OffsetDateTime.now().minusMinutes(10)))
                .noneMatch(value -> value.taskId().equals(runId));
        assertThat(send("GET", "/api/v1/portrait-tasks/" + runId, null, 200).get("status").asText()).isEqualTo("pending");
        assertThat(send("GET", "/api/v1/styles", null, 200).get(0).get("tasks").get(0).get("id").asText()).isEqualTo(runId);

        doReturn(false).when(settings).routesNewUserScopedDurableAgentRun(USER);
        assertThat(send("POST", base + "/portrait", null, 409).get("code").asText()).isEqualTo("PORTRAIT_TASK_ACTIVE");
        assertThat(send("GET", "/api/v1/portrait-tasks/" + runId, null, 200).get("status").asText()).isEqualTo("pending");
        send("PATCH", base + "/sections/styleTraits", Map.of("content", "作者可继续编辑"), 200);
        send("DELETE", base + "/references/" + referenceId, null, 204);
        assertThat(database.<Boolean>transactionResult(tx -> completion.isDeleted(tx, runId))).isFalse();
        JsonNode frozen = json.readTree(database.dsl().fetchOne("""
                SELECT item."contentJson" FROM public."WorkflowEvidenceItem" item
                JOIN public."WorkflowEvidenceBundle" bundle ON bundle.id = item."bundleId" WHERE bundle."runId" = ?
                """, runId).get("contentJson", String.class));
        assertThat(frozen.get("references").get(0).get("content").asText()).isEqualTo("\uFEFF甲😀\r\n乙\n");
        Map<String, String> sections = new LinkedHashMap<>();
        WorkflowStylePortraitCompletion.SECTIONS.forEach(section -> sections.put(section, " " + section + " "));
        // 通用签名回调与五步恢复另有真实 PostgreSQL 测试；此处聚焦原公共业务投影的 Spring 装配。
        database.transactionResult(tx -> {
            assertThat(completion.complete(tx, runId, sections)).isEqualTo("completed");
            tx.execute("UPDATE public.\"WorkflowRun\" SET status = 'completed', \"completedAt\" = \"createdAt\" WHERE id = ?", runId);
            return null;
        });
        assertThat(send("GET", "/api/v1/portrait-tasks/" + runId, null, 200).get("status").asText()).isEqualTo("success");
        JsonNode style = send("GET", "/api/v1/styles", null, 200).get(0);
        assertThat(style.get("styleTraits").asText()).isEqualTo("styleTraits");
        assertThat(style.get("originalCharCount").asInt()).isEqualTo(4);

        upload(base + "/references", "新资料");
        doReturn(true).when(settings).routesNewUserScopedDurableAgentRun(USER);
        String singleId = send("POST", base + "/sections/uniqueMarkers/portrait", null, 202).get("taskId").asText();
        assertThat(send("GET", "/api/v1/portrait-tasks/" + singleId, null, 200).get("section").asText()).isEqualTo("uniqueMarkers");
        send("DELETE", base, null, 204);
        send("GET", "/api/v1/portrait-tasks/" + runId, null, 404);
        send("GET", "/api/v1/portrait-tasks/" + singleId, null, 404);
        assertThat(send("GET", "/api/v1/styles", null, 200).size()).isZero();
        assertThat(completion.findDeletedRuns(100)).anyMatch(value -> value.runId().equals(singleId));
    }

    private JsonNode upload(String path, String content) throws Exception {
        String boundary = "inkforge-durable-style-boundary";
        String body = "--" + boundary + "\r\nContent-Disposition: form-data; name=\"file\"; filename=\"参考.txt\"\r\n"
                + "Content-Type: text/plain; charset=utf-8\r\n\r\n" + content + "\r\n--" + boundary + "--\r\n";
        HttpRequest request = request(path).header("Content-Type", "multipart/form-data; boundary=" + boundary)
                .POST(HttpRequest.BodyPublishers.ofString(body)).build();
        var response = http.send(request, HttpResponse.BodyHandlers.ofString());
        assertThat(response.statusCode()).as(response.body()).isEqualTo(201);
        return json.readTree(response.body());
    }

    private JsonNode send(String method, String path, Object body, int status) throws Exception {
        var request = request(path).header("Content-Type", "application/json")
                .method(method, body == null ? HttpRequest.BodyPublishers.noBody()
                        : HttpRequest.BodyPublishers.ofString(json.writeValueAsString(body))).build();
        var response = http.send(request, HttpResponse.BodyHandlers.ofString());
        assertThat(response.statusCode()).as(response.body()).isEqualTo(status);
        return status == 204 ? null : json.readTree(response.body());
    }

    private HttpRequest.Builder request(String path) {
        return HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + path)).timeout(Duration.ofSeconds(10))
                .header("Cookie", IdentityController.COOKIE_NAME + "=" + sessions.create(USER));
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
                var user = database.dsl().fetchOne("SELECT id, username FROM public.\"User\" WHERE id = ?", userId);
                if (user == null) throw new ApiException(401, "UNAUTHENTICATED", "请先登录");
                return new AuthenticatedUser(user.get("id", String.class), user.get("username", String.class));
            };
        }
        @Bean @Primary
        StylePortraitExecutionReadiness testStyleReadiness() { return () -> true; }
        @Bean @Primary
        PortraitRunSubmitter oldPortraitSubmitter() { return (userId, styleId, taskId, runId, section) -> PortraitDispatchStatus.QUEUED; }
        @Bean @Primary
        ExecutionRegistry testStyleRegistry() { return ExecutionRegistryFixtures.styleOperationEnabled(ExecutionRegistry.Environment.TEST); }
    }
}
