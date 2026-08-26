package cn.inkforge.core.video.api;

import static cn.inkforge.core.db.generated.Tables.USER;
import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.core.CoreApplication;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.InternalServiceAuthenticator;
import java.io.ByteArrayOutputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;
import org.testcontainers.containers.Container.ExecResult;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.DockerImageName;
import org.testcontainers.utility.MountableFile;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

@Testcontainers
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
@SpringBootTest(
        classes = {CoreApplication.class, VideoRuntimeIntegrationTest.TestPorts.class},
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class VideoRuntimeIntegrationTest {

    private static final Path UPLOAD_ROOT = Path.of(
            System.getProperty("java.io.tmpdir"),
            "inkforge-video-runtime-" + UUID.randomUUID());

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_video_runtime")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    @Container
    private static final GenericContainer<?> REDIS =
            new GenericContainer<>(DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("DATABASE_URL", VideoRuntimeIntegrationTest::databaseUrl);
        registry.add("REDIS_URL", () -> "redis://"
                + REDIS.getHost() + ":" + REDIS.getMappedPort(6379) + "/0");
        registry.add("JWT_SECRET", () -> "Java视频运行时测试密钥-长度超过三十二字节-不可用于生产");
        registry.add("ENVIRONMENT", () -> "test");
        registry.add("TRUSTED_AGENT_CIDRS", () -> "127.0.0.1/32");
        registry.add("UPLOADS_ROOT", UPLOAD_ROOT::toString);
        registry.add("VIDEO_PREVIEW_ENABLED", () -> "true");
        registry.add("VIDEO_DISPATCH_ENABLED", () -> "false");
        registry.add("SEEDANCE_ENABLED", () -> "false");
        // 生产 Compose 会显式传入空值；空值必须等价于未配置，而不是误创建令牌编码器。
        registry.add("VIDEO_PROVIDER_MEDIA_BASE_URL", () -> "");
        registry.add("VIDEO_PROVIDER_MEDIA_TOKEN_SECRET", () -> "");
    }

    @BeforeAll
    static void restoreSchema() throws Exception {
        POSTGRES.copyFileToContainer(
                MountableFile.forClasspathResource("db/novelwriterdev-schema.sql"),
                "/tmp/novelwriterdev-schema.sql");
        ExecResult result = POSTGRES.execInContainer(
                "psql", "-v", "ON_ERROR_STOP=1",
                "-U", POSTGRES.getUsername(),
                "-d", POSTGRES.getDatabaseName(),
                "-f", "/tmp/novelwriterdev-schema.sql");
        assertThat(result.getExitCode()).as(result.getStderr()).isZero();
    }

    @AfterAll
    static void cleanupUploads() throws Exception {
        if (!Files.exists(UPLOAD_ROOT)) return;
        try (var paths = Files.walk(UPLOAD_ROOT)) {
            for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
                Files.deleteIfExists(path);
            }
        }
    }

    @LocalServerPort
    private int port;

    @Autowired
    private CoreDatabase database;

    @Autowired
    private ObjectMapper json;

    @Autowired
    @Qualifier("requestMappingHandlerMapping")
    private RequestMappingHandlerMapping mappings;

    private final HttpClient client = HttpClient.newHttpClient();
    private String userId;

    @AfterEach
    void cleanupRows() {
        if (userId != null) {
            database.dsl().deleteFrom(USER).where(USER.ID.eq(userId)).execute();
        }
    }

    @Test
    void 四十八个视频映射与项目素材章节改编内部进度必须在真实运行时闭环() throws Exception {
        var videoHandlers = mappings.getHandlerMethods().entrySet().stream()
                .filter(entry -> entry.getValue().getBeanType() == VideoController.class)
                .toList();
        Set<String> videoMappings = videoHandlers.stream()
                .flatMap(entry -> entry.getKey().getPatternValues().stream())
                .collect(Collectors.toSet());
        assertThat(videoHandlers).hasSize(48);
        // 项目、章节改编和视觉设定各有一组 GET/POST 共用路径，因此 48 个操作对应 45 条路径。
        assertThat(videoMappings).hasSize(45);
        assertThat(videoMappings)
                .contains(
                        "/api/v1/video/novels/{novel_id}/projects",
                        "/api/v1/video/chapter-adaptations/{adaptation_id}/post-production",
                        "/internal/v1/video/adaptations/{adaptation_id}/progress",
                        "/internal/v1/video/scenes/{scene_id}/progress");

        String username = "video_"
                + UUID.randomUUID().toString().replace("-", "").substring(0, 12);
        HttpResponse<String> registration = jsonRequest(
                "POST",
                "/api/v1/auth/register",
                "{\"username\":\"" + username
                        + "\",\"password\":\"密码1234\",\"confirmPassword\":\"密码1234\"}",
                null,
                false);
        assertThat(registration.statusCode()).as(registration.body()).isEqualTo(201);
        userId = database.dsl().select(USER.ID)
                .from(USER)
                .where(USER.USERNAME.eq(username))
                .fetchSingle(USER.ID);
        String cookie = registration.headers()
                .firstValue("set-cookie")
                .orElseThrow()
                .split(";", 2)[0];

        HttpResponse<String> novel = jsonRequest(
                "POST",
                "/api/v1/novels",
                "{\"name\":\"视频运行时长篇\",\"storyLengthProfile\":\"long_serial\","
                        + "\"firstChapterGoal\":\"建立第一章冲突\"}",
                cookie,
                false);
        assertThat(novel.statusCode()).as(novel.body()).isEqualTo(201);
        JsonNode novelJson = json.readTree(novel.body());
        String novelId = novelJson.get("novelId").asString();
        String chapterId = novelJson.get("chapterId").asString();

        JsonNode chapter = json.readTree(jsonRequest(
                "GET", "/api/v1/chapters/" + chapterId, null, cookie, false).body());
        HttpResponse<String> chapterUpdated = jsonRequest(
                "PATCH",
                "/api/v1/chapters/" + chapterId,
                json.writeValueAsString(java.util.Map.of(
                        "title", "第一章",
                        "content", "雨夜里，沈砚听见门外异响。",
                        "expectedUpdatedAt", chapter.get("updatedAt").asString())),
                cookie,
                false);
        assertThat(chapterUpdated.statusCode()).as(chapterUpdated.body()).isEqualTo(200);
        String chapterUpdatedAt = json.readTree(chapterUpdated.body()).get("updatedAt").asString();

        HttpResponse<String> createdProject = jsonRequest(
                "POST",
                "/api/v1/video/novels/" + novelId + "/projects",
                "{\"title\":\"第一章影视化\",\"mode\":\"series\","
                        + "\"targetAspectRatio\":\"16:9\",\"targetLanguage\":\"zh-CN\"}",
                cookie,
                false);
        assertThat(createdProject.statusCode()).as(createdProject.body()).isEqualTo(201);
        String projectId = json.readTree(createdProject.body()).get("id").asString();
        assertThat(jsonRequest(
                        "GET",
                        "/api/v1/video/novels/" + novelId + "/projects",
                        null,
                        cookie,
                        false)
                .body()).contains(projectId);
        assertThat(jsonRequest(
                        "GET", "/api/v1/video/projects/" + projectId, null, cookie, false)
                .statusCode()).isEqualTo(200);

        byte[] png = new byte[] {
            (byte) 0x89, 'P', 'N', 'G', '\r', '\n', 0x1a, '\n', 0, 0, 0, 0
        };
        HttpResponse<String> uploaded = multipart(
                "/api/v1/video/projects/" + projectId + "/assets",
                cookie,
                png);
        assertThat(uploaded.statusCode()).as(uploaded.body()).isEqualTo(201);
        String assetId = json.readTree(uploaded.body()).get("id").asString();
        HttpResponse<String> confirmed = jsonRequest(
                "PATCH",
                "/api/v1/video/assets/" + assetId + "/rights",
                "{\"rightsStatus\":\"confirmed\"}",
                cookie,
                false);
        assertThat(confirmed.statusCode()).as(confirmed.body()).isEqualTo(200);
        assertThat(binary(
                        "/api/v1/video/assets/" + assetId + "/content", cookie)
                .body()).isEqualTo(png);
        assertThat(binary(
                        "/api/v1/video/assets/" + assetId + "/preview", cookie)
                .body()).isEqualTo(png);

        HttpResponse<String> adaptation = jsonRequest(
                "POST",
                "/api/v1/video/projects/" + projectId + "/chapter-adaptations",
                json.writeValueAsString(java.util.Map.of(
                        "chapterId", chapterId,
                        "clientRequestId", "runtime-video-adaptation-0001",
                        "expectedChapterUpdatedAt", chapterUpdatedAt)),
                cookie,
                false);
        assertThat(adaptation.statusCode()).as(adaptation.body()).isEqualTo(201);
        String adaptationId = json.readTree(adaptation.body()).get("id").asString();
        assertThat(jsonRequest(
                        "GET",
                        "/api/v1/video/projects/" + projectId + "/chapter-adaptations",
                        null,
                        cookie,
                        false)
                .body()).contains(adaptationId);
        assertThat(jsonRequest(
                        "GET",
                        "/api/v1/video/chapter-adaptations/" + adaptationId,
                        null,
                        cookie,
                        false)
                .statusCode()).isEqualTo(200);
        assertThat(jsonRequest(
                        "GET",
                        "/api/v1/video/projects/" + projectId + "/visual-canons",
                        null,
                        cookie,
                        false)
                .statusCode()).isEqualTo(200);
        assertThat(jsonRequest(
                        "GET",
                        "/api/v1/video/chapter-adaptations/" + adaptationId + "/renders",
                        null,
                        cookie,
                        false)
                .statusCode()).isEqualTo(200);
        HttpResponse<String> postProduction = jsonRequest(
                "GET",
                "/api/v1/video/chapter-adaptations/" + adaptationId + "/post-production",
                null,
                cookie,
                false);
        assertThat(postProduction.statusCode()).isEqualTo(409);
        assertThat(json.readTree(postProduction.body()).get("code").asString())
                .isEqualTo("VIDEO_POST_PRODUCTION_FORMAL_PLAN_REQUIRED");

        HttpResponse<String> started = jsonRequest(
                "POST",
                "/api/v1/video/chapter-adaptations/" + adaptationId + "/shot-plan-runs",
                "{\"clientRequestId\":\"runtime-video-plan-0001\"}",
                cookie,
                false);
        assertThat(started.statusCode()).as(started.body()).isEqualTo(202);
        JsonNode task = json.readTree(started.body()).get("task");
        String taskId = task.get("id").asString();
        String jobId = task.get("jobId").asString();
        String progressBody = json.writeValueAsString(java.util.Map.of(
                "protocolVersion", "1.0",
                "jobId", jobId,
                "runId", taskId,
                "taskId", taskId,
                "novelId", novelId,
                "projectId", projectId,
                "adaptationId", adaptationId,
                "workflow", "chapter_cinematic_adaptation_v2"));
        HttpResponse<String> progress = jsonRequest(
                "POST",
                "/internal/v1/video/adaptations/" + adaptationId + "/progress",
                progressBody,
                null,
                true);
        assertThat(progress.statusCode()).as(progress.body()).isEqualTo(200);
        assertThat(json.readTree(progress.body()).get("status").asString()).isEqualTo("active");
    }

    private HttpResponse<String> jsonRequest(
            String method,
            String path,
            String body,
            String cookie,
            boolean internal) throws Exception {
        HttpRequest.Builder request = HttpRequest.newBuilder(uri(path));
        if (cookie != null) request.header("Cookie", cookie);
        if (internal) request.header("Authorization", "Bearer captured-by-test");
        if (body == null) {
            request.method(method, HttpRequest.BodyPublishers.noBody());
        } else {
            request.header("Content-Type", "application/json")
                    .method(method, HttpRequest.BodyPublishers.ofString(body));
        }
        return client.send(request.build(), HttpResponse.BodyHandlers.ofString());
    }

    private HttpResponse<byte[]> binary(String path, String cookie) throws Exception {
        return client.send(
                HttpRequest.newBuilder(uri(path)).header("Cookie", cookie).GET().build(),
                HttpResponse.BodyHandlers.ofByteArray());
    }

    private HttpResponse<String> multipart(String path, String cookie, byte[] file)
            throws Exception {
        String boundary = "InkForgeBoundary" + UUID.randomUUID().toString().replace("-", "");
        ByteArrayOutputStream body = new ByteArrayOutputStream();
        field(body, boundary, "duty", "identity");
        field(body, boundary, "modality", "image");
        field(body, boundary, "name", "沈砚角色参考");
        field(body, boundary, "sourceKind", "user_upload");
        body.write(("--" + boundary + "\r\n"
                        + "Content-Disposition: form-data; name=\"file\"; filename=\"reference.png\"\r\n"
                        + "Content-Type: image/png\r\n\r\n")
                .getBytes(StandardCharsets.UTF_8));
        body.write(file);
        body.write(("\r\n--" + boundary + "--\r\n").getBytes(StandardCharsets.UTF_8));
        HttpRequest request = HttpRequest.newBuilder(uri(path))
                .header("Cookie", cookie)
                .header("Content-Type", "multipart/form-data; boundary=" + boundary)
                .POST(HttpRequest.BodyPublishers.ofByteArray(body.toByteArray()))
                .build();
        return client.send(request, HttpResponse.BodyHandlers.ofString());
    }

    private static void field(
            ByteArrayOutputStream body, String boundary, String name, String value)
            throws java.io.IOException {
        body.write(("--" + boundary + "\r\n"
                        + "Content-Disposition: form-data; name=\"" + name + "\"\r\n\r\n"
                        + value + "\r\n")
                .getBytes(StandardCharsets.UTF_8));
    }

    private URI uri(String path) {
        return URI.create("http://127.0.0.1:" + port + path);
    }

    private static String databaseUrl() {
        return "postgresql://"
                + POSTGRES.getUsername() + ":" + POSTGRES.getPassword()
                + "@" + POSTGRES.getHost() + ":" + POSTGRES.getFirstMappedPort()
                + "/" + POSTGRES.getDatabaseName();
    }

    @TestConfiguration
    static class TestPorts {

        @Bean
        @Primary
        InternalServiceAuthenticator videoRuntimeAuthenticator() {
            return (request,
                            body,
                            scope,
                            taskId,
                            runId,
                            novelId,
                            unavailableCode,
                            unavailableMessage) -> null;
        }
    }
}
