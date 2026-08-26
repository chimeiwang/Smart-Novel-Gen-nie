package cn.inkforge.core.lore.api;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.USER;
import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.core.CoreApplication;
import cn.inkforge.core.db.generated.enums.Chapterstatus;
import cn.inkforge.core.platform.db.CoreDatabase;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
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
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

@Testcontainers
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
@SpringBootTest(
        classes = CoreApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class LoreRuntimeIntegrationTest {

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_lore_runtime")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    @Container
    private static final GenericContainer<?> REDIS =
            new GenericContainer<>(DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("DATABASE_URL", LoreRuntimeIntegrationTest::databaseUrl);
        registry.add("REDIS_URL", () -> "redis://"
                + REDIS.getHost() + ":" + REDIS.getMappedPort(6379) + "/0");
        registry.add("JWT_SECRET", () -> "Java设定运行时测试密钥-长度超过三十二字节-不可用于生产");
        registry.add("ENVIRONMENT", () -> "test");
        registry.add("VIDEO_PREVIEW_ENABLED", () -> "true");
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

    @LocalServerPort
    private int port;

    @Autowired
    private CoreDatabase database;

    @Autowired
    private ObjectMapper json;

    private final HttpClient client = HttpClient.newHttpClient();
    private String userId;

    @AfterEach
    void cleanup() {
        if (userId != null) {
            database.dsl().deleteFrom(USER).where(USER.ID.eq(userId)).execute();
        }
    }

    @Test
    void 三十二个冻结设定接口必须在真实运行时闭环() throws Exception {
        String username = "lore_"
                + UUID.randomUUID().toString().replace("-", "").substring(0, 12);
        HttpResponse<String> registration = send(
                "POST",
                "/api/v1/auth/register",
                "{\"username\":\"" + username
                        + "\",\"password\":\"密码1234\",\"confirmPassword\":\"密码1234\"}",
                null);
        assertThat(registration.statusCode()).isEqualTo(201);
        userId = database.dsl().select(USER.ID)
                .from(USER)
                .where(USER.USERNAME.eq(username))
                .fetchSingle(USER.ID);
        String cookie = registration.headers()
                .firstValue("set-cookie")
                .orElseThrow()
                .split(";", 2)[0];
        String novelId = "runtime-lore-" + UUID.randomUUID();
        LocalDateTime initial = LocalDateTime.parse("2026-08-25T02:00:00.000");
        database.dsl().insertInto(NOVEL)
                .set(NOVEL.ID, novelId)
                .set(NOVEL.NAME, "运行时作品")
                .set(NOVEL.USERID, userId)
                .set(NOVEL.CREATEDAT, initial)
                .set(NOVEL.UPDATEDAT, initial)
                .execute();
        String chapterId = novelId + "-chapter";
        database.dsl().insertInto(CHAPTER)
                .set(CHAPTER.ID, chapterId)
                .set(CHAPTER.NOVELID, novelId)
                .set(CHAPTER.TITLE, "第一章")
                .set(CHAPTER.CONTENT, "")
                .set(CHAPTER.ORDER, 1)
                .set(CHAPTER.STATUS, Chapterstatus.drafting)
                .set(CHAPTER.CREATEDAT, initial)
                .set(CHAPTER.UPDATEDAT, initial)
                .execute();

        assertThat(send(
                        "PUT",
                        "/api/v1/novels/" + novelId + "/world-setting",
                        "{\"content\":\"缺少版本\"}",
                        cookie)
                        .statusCode())
                .isEqualTo(422);

        List<EntityCase> cases = List.of(
                new EntityCase("characters", "name", Map.of("name", "角色")),
                new EntityCase("items", "name", Map.of("name", "物品")),
                new EntityCase("locations", "name", Map.of("name", "地点")),
                new EntityCase("factions", "name", Map.of("name", "势力")),
                new EntityCase(
                        "glossary", "term",
                        Map.of("term", "术语", "definition", "释义")));
        for (EntityCase entityCase : cases) {
            Map<String, Object> create = new LinkedHashMap<>(entityCase.createFields());
            create.put("clientRequestId", "runtime-lore-create-" + entityCase.path());
            HttpResponse<String> created = send(
                    "POST",
                    "/api/v1/novels/" + novelId + "/" + entityCase.path(),
                    json.writeValueAsString(create),
                    cookie);
            assertThat(created.statusCode()).as(created.body()).isEqualTo(201);
            JsonNode value = json.readTree(created.body());
            assertThat(value.get("effective").asBoolean()).isTrue();
            String id = value.get("id").asText();
            String version = value.get("updatedAt").asText();

            HttpResponse<String> listed = send(
                    "GET",
                    "/api/v1/novels/" + novelId + "/" + entityCase.path(),
                    null,
                    cookie);
            assertThat(listed.statusCode()).isEqualTo(200);
            assertThat(json.readTree(listed.body()).size()).isEqualTo(1);
            assertThat(listed.body()).doesNotContain("novelId", "clientRequestId");

            HttpResponse<String> updated = send(
                    "PATCH",
                    "/api/v1/novels/" + novelId + "/" + entityCase.path() + "/" + id,
                    json.writeValueAsString(Map.of(
                            entityCase.updateField(), "更新后",
                            "expectedUpdatedAt", version)),
                    cookie);
            assertThat(updated.statusCode()).as(updated.body()).isEqualTo(200);
            String updatedVersion = json.readTree(updated.body()).get("updatedAt").asText();
            HttpResponse<String> deleted = send(
                    "DELETE",
                    "/api/v1/novels/" + novelId + "/" + entityCase.path() + "/" + id,
                    json.writeValueAsString(Map.of("expectedUpdatedAt", updatedVersion)),
                    cookie);
            assertThat(deleted.statusCode()).as(deleted.body()).isEqualTo(200);
        }

        JsonNode characterA = createCharacter(
                novelId, cookie, "甲", "runtime-lore-character-a");
        JsonNode characterB = createCharacter(
                novelId, cookie, "乙", "runtime-lore-character-b");

        HttpResponse<String> createdExperience = send(
                "POST",
                "/api/v1/novels/" + novelId + "/characters/"
                        + characterA.get("id").asText() + "/experiences",
                json.writeValueAsString(Map.of(
                        "clientRequestId", "runtime-lore-experience",
                        "chapterId", chapterId,
                        "content", "  完整经历\r\n  ")),
                cookie);
        assertThat(createdExperience.statusCode()).as(createdExperience.body()).isEqualTo(201);
        JsonNode experience = json.readTree(createdExperience.body());
        assertThat(send(
                        "GET",
                        "/api/v1/novels/" + novelId + "/characters/"
                                + characterA.get("id").asText() + "/experiences",
                        null,
                        cookie)
                        .statusCode())
                .isEqualTo(200);
        HttpResponse<String> changedExperience = send(
                "PATCH",
                "/api/v1/novels/" + novelId + "/experiences/"
                        + experience.get("id").asText(),
                json.writeValueAsString(Map.of(
                        "content", "新经历",
                        "expectedUpdatedAt", experience.get("updatedAt").asText())),
                cookie);
        assertThat(changedExperience.statusCode()).as(changedExperience.body()).isEqualTo(200);
        assertThat(send(
                        "DELETE",
                        "/api/v1/novels/" + novelId + "/experiences/"
                                + experience.get("id").asText(),
                        json.writeValueAsString(Map.of(
                                "expectedUpdatedAt",
                                json.readTree(changedExperience.body())
                                        .get("updatedAt").asText())),
                        cookie)
                        .statusCode())
                .isEqualTo(200);

        HttpResponse<String> createdRelation = send(
                "POST",
                "/api/v1/novels/" + novelId + "/relations",
                json.writeValueAsString(Map.of(
                        "clientRequestId", "runtime-lore-relation",
                        "characterId", characterA.get("id").asText(),
                        "targetId", characterB.get("id").asText(),
                        "relationType", "friend",
                        "intimacy", 20)),
                cookie);
        assertThat(createdRelation.statusCode()).as(createdRelation.body()).isEqualTo(201);
        JsonNode relation = json.readTree(createdRelation.body());
        assertThat(send(
                        "GET",
                        "/api/v1/novels/" + novelId + "/relations",
                        null,
                        cookie)
                        .statusCode())
                .isEqualTo(200);
        HttpResponse<String> changedRelation = send(
                "PATCH",
                "/api/v1/novels/" + novelId + "/relations/"
                        + relation.get("id").asText(),
                json.writeValueAsString(Map.of(
                        "description", "反目",
                        "expectedUpdatedAt", relation.get("updatedAt").asText())),
                cookie);
        assertThat(changedRelation.statusCode()).as(changedRelation.body()).isEqualTo(200);
        assertThat(send(
                        "DELETE",
                        "/api/v1/novels/" + novelId + "/relations/"
                                + relation.get("id").asText(),
                        json.writeValueAsString(Map.of(
                                "expectedUpdatedAt",
                                json.readTree(changedRelation.body())
                                        .get("updatedAt").asText())),
                        cookie)
                        .statusCode())
                .isEqualTo(200);

        String exactContent = "  第一行\r\n\r\n最后一行  ";
        for (String path : List.of("story-background", "world-setting")) {
            HttpResponse<String> response = send(
                    "PUT",
                    "/api/v1/novels/" + novelId + "/" + path,
                    json.writeValueAsString(nullableMap(
                            "content", exactContent, "expectedUpdatedAt", null)),
                    cookie);
            assertThat(response.statusCode()).as(response.body()).isEqualTo(200);
            assertThat(json.readTree(response.body()).get("content").asText())
                    .isEqualTo(exactContent);
        }
        HttpResponse<String> bible = send(
                "PUT",
                "/api/v1/novels/" + novelId + "/writing-bible",
                json.writeValueAsString(nullableMap(
                        "genre", "仙侠", "expectedUpdatedAt", null)),
                cookie);
        assertThat(bible.statusCode()).as(bible.body()).isEqualTo(200);
        assertThat(json.readTree(bible.body()).get("storyLengthProfile").asText())
                .isEqualTo("long_serial");
        HttpResponse<String> progress = send(
                "PUT",
                "/api/v1/novels/" + novelId + "/story-progress",
                json.writeValueAsString(Map.of(
                        "content", "推进到第一章",
                        "expectedUpdatedAt", "2026-08-25T02:00:00Z")),
                cookie);
        assertThat(progress.statusCode()).as(progress.body()).isEqualTo(200);
    }

    private JsonNode createCharacter(
            String novelId, String cookie, String name, String requestId) throws Exception {
        HttpResponse<String> response = send(
                "POST",
                "/api/v1/novels/" + novelId + "/characters",
                json.writeValueAsString(Map.of(
                        "name", name, "clientRequestId", requestId)),
                cookie);
        assertThat(response.statusCode()).as(response.body()).isEqualTo(201);
        return json.readTree(response.body());
    }

    private static Map<String, Object> nullableMap(
            String firstName, Object firstValue, String secondName, Object secondValue) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put(firstName, firstValue);
        value.put(secondName, secondValue);
        return value;
    }

    private HttpResponse<String> send(
            String method, String path, String body, String cookie) throws Exception {
        HttpRequest.Builder request = HttpRequest.newBuilder(uri(path));
        if (cookie != null) request.header("Cookie", cookie);
        if (body == null) {
            request.method(method, HttpRequest.BodyPublishers.noBody());
        } else {
            request.header("Content-Type", "application/json")
                    .method(method, HttpRequest.BodyPublishers.ofString(body));
        }
        return client.send(request.build(), HttpResponse.BodyHandlers.ofString());
    }

    private URI uri(String path) {
        return URI.create("http://127.0.0.1:" + port + path);
    }

    private static String databaseUrl() {
        return "postgresql://"
                + POSTGRES.getUsername() + ":" + POSTGRES.getPassword()
                + "@127.0.0.1:" + POSTGRES.getMappedPort(5432)
                + "/" + POSTGRES.getDatabaseName();
    }

    private record EntityCase(
            String path, String updateField, Map<String, Object> createFields) {}
}
