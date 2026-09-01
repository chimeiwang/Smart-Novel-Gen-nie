package cn.inkforge.core.workflows.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.core.CoreApplication;
import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.db.DurableAgentSchemaGate;
import cn.inkforge.core.reviews.application.ReviewRepository;
import cn.inkforge.core.workflows.api.WorkflowsController;
import cn.inkforge.core.workflows.application.DurableWorkflowService;
import cn.inkforge.core.workflows.application.WorkflowCallbackRepository;
import cn.inkforge.core.workflows.application.WorkflowCancellationReconciler;
import cn.inkforge.core.workflows.application.WorkflowDispatchRepository;
import cn.inkforge.core.workflows.application.WorkflowEventStreamRepository;
import cn.inkforge.core.workflows.application.WorkflowRunCancellationRepository;
import cn.inkforge.core.writing.application.LongSerialDurableRunStarter;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.ApplicationContext;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;

@Testcontainers
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
@SpringBootTest(
        classes = CoreApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class DurableAgentSchemaAssemblyIntegrationTest {

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("novelwriterdev")
                    .withUsername("inkforge")
                    .withPassword("test-only-password")
                    .withCopyFileToContainer(
                            MountableFile.forClasspathResource(
                                    "db/novelwriterdev-schema.sql", 0644),
                            "/docker-entrypoint-initdb.d/01-schema.sql")
                    .withCopyFileToContainer(
                            MountableFile.forClasspathResource(
                                    "migrations/20260831_durable_agent_execution.sql", 0644),
                            "/docker-entrypoint-initdb.d/02-durable-agent.sql");

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("DATABASE_URL", DurableAgentSchemaAssemblyIntegrationTest::databaseUrl);
        registry.add("REDIS_URL", () -> "false");
        registry.add("JWT_SECRET", () -> "Java耐久执行装配测试密钥-长度超过三十二字节-不可用于生产");
        registry.add("ENVIRONMENT", () -> "test");
        registry.add("TRUSTED_AGENT_CIDRS", () -> "127.0.0.1/32");
        registry.add("VIDEO_PREVIEW_ENABLED", () -> "true");
        registry.add("DURABLE_AGENT_EXECUTION_SCHEMA_READY", () -> "true");
        registry.add("DURABLE_AGENT_EXECUTION_ROUTE_MODE", () -> "off");
    }

    @LocalServerPort
    private int port;

    @Autowired
    private ApplicationContext context;

    @Autowired
    private CoreSettings settings;

    @Test
    void 迁移后同一镜像以routeOff装配V2收敛面且保持数据库就绪() throws Exception {
        assertThat(settings.durableAgentExecutionSchemaReady()).isTrue();
        assertThat(settings.routesNewDurableAgentRun("user", "novel")).isFalse();
        assertThat(context.getBean(DurableAgentSchemaGate.class).fingerprint()).isNotBlank();
        assertThat(context.getBean(DurableWorkflowService.class)).isNotNull();
        assertThat(context.getBean(WorkflowDispatchRepository.class)).isNotNull();
        assertThat(context.getBean(WorkflowCallbackRepository.class)).isNotNull();
        assertThat(context.getBean(WorkflowRunCancellationRepository.class)).isNotNull();
        assertThat(context.getBean(WorkflowEventStreamRepository.class)).isNotNull();
        assertThat(context.getBean(WorkflowCancellationReconciler.class)).isNotNull();
        assertThat(context.getBean(LongSerialDurableRunStarter.class)).isNotNull();
        assertThat(context.getBean(ReviewRepository.class)).isNotNull();
        assertThat(context.getBean(WorkflowsController.class)).isNotNull();
        assertThat(context.containsBean("workflowCancellationReconcilerStarter")).isTrue();
        assertThat(context.containsBean("workflowStepDispatcherStarter")).isTrue();

        String mismatchedProgress = """
                {
                  "protocolVersion":"2.0",
                  "progressId":"progress-route-off-1",
                  "jobId":"job-route-off-1",
                  "runId":"run-body",
                  "novelId":"novel-1",
                  "stepId":"step-body",
                  "fencingToken":1,
                  "requestHash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                  "resolvedModel":{
                    "deploymentProfileKey":"creative.default",
                    "deploymentFingerprint":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                    "provider":"fake",
                    "model":"fake-model",
                    "transportProfile":"test.transport",
                    "endpointProfile":"test.endpoint",
                    "structuredOutputRoute":"responses_json_schema_v1",
                    "capabilityVersion":"test.v1",
                    "reasoningMode":"disabled",
                    "supportsRequestIdempotency":true
                  },
                  "sequence":1,
                  "phase":"preparing",
                  "progressCode":"started",
                  "elapsedSeconds":0,
                  "waitingOnProvider":false,
                  "usage":{
                    "usageStatus":"unknown",
                    "providerAttempts":0,
                    "protocolCorrections":0,
                    "wallTimeMillis":0
                  },
                  "occurredAt":"2026-09-01T00:00:00Z"
                }
                """;
        HttpResponse<String> directedCallback = HttpClient.newHttpClient().send(
                HttpRequest.newBuilder()
                        .uri(URI.create("http://127.0.0.1:"
                                + port
                                + "/internal/v1/workflow-runs/run-path/steps/step-path/progress"))
                        .header("Content-Type", "application/json")
                        .PUT(HttpRequest.BodyPublishers.ofString(mismatchedProgress))
                        .build(),
                HttpResponse.BodyHandlers.ofString());
        assertThat(directedCallback.statusCode()).as(directedCallback.body()).isEqualTo(409);

        HttpResponse<String> readiness = HttpClient.newHttpClient().send(
                HttpRequest.newBuilder()
                        .uri(URI.create("http://127.0.0.1:"
                                + port
                                + "/api/v1/health/ready"))
                        .GET()
                        .build(),
                HttpResponse.BodyHandlers.ofString());
        assertThat(readiness.statusCode()).as(readiness.body()).isEqualTo(200);
        assertThat(readiness.body()).contains("\"database\":\"ok\"");
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
