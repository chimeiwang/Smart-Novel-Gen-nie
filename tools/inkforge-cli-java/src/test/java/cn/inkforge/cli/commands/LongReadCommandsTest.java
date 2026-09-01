package cn.inkforge.cli.commands;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.cli.config.MemoryConfigStore;
import cn.inkforge.cli.config.MemoryCredentialStore;
import cn.inkforge.cli.config.ProfileConfig;
import cn.inkforge.cli.runtime.CliApplication;
import cn.inkforge.cli.runtime.CliDependencies;
import cn.inkforge.cli.transport.CoreApi;
import cn.inkforge.cli.transport.FileDescriptor;
import cn.inkforge.cli.transport.LoginResult;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

class LongReadCommandsTest {

    private final JsonMapper json = JsonMapper.builder().build();

    @Test
    void 公共路径片段使用RFC3986而不是表单编码() {
        assertThat(Payloads.segment("a~* /😀"))
                .isEqualTo("a~%2A%20%2F%F0%9F%98%80");
    }

    @Test
    void 十六个长篇读取命令使用精确公共路径与查询() {
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);
        List<Case> cases = List.of(
                new Case("long.novel.list", "{}", "/api/v1/novels", q("storyLengthProfile", "long_serial")),
                new Case("long.novel.get", "{\"novelId\":\"作品/1\"}", "/api/v1/novels/%E4%BD%9C%E5%93%81%2F1", Map.of()),
                new Case("long.chapter.list", "{\"novelId\":\"n1\"}", "/api/v1/novels/n1/chapters", Map.of()),
                new Case("long.chapter.get", "{\"chapterId\":\"c 1\"}", "/api/v1/chapters/c%201", Map.of()),
                new Case("long.session.list", "{\"novelId\":\"n1\",\"chapterId\":\"c1\"}", "/api/v1/writing/sessions", q("novelId", "n1", "chapterId", "c1")),
                new Case("long.session.get", "{\"sessionId\":\"s1\"}", "/api/v1/writing/sessions/s1", Map.of()),
                new Case("long.planning.get", "{\"novelId\":\"n1\"}", "/api/v1/novels/n1/workspace/planning", Map.of()),
                new Case("long.lore.get", "{\"novelId\":\"n1\"}", "/api/v1/novels/n1/workspace/lore", Map.of()),
                new Case("long.resources.get", "{\"novelId\":\"n1\"}", "/api/v1/novels/n1/workspace/resources", Map.of()),
                new Case("long.outline-node.list", "{\"novelId\":\"n1\"}", "/api/v1/novels/n1/outline-nodes", Map.of()),
                new Case("long.foreshadowing.list", "{\"novelId\":\"n1\"}", "/api/v1/novels/n1/foreshadowings", Map.of()),
                new Case("long.task.list", "{\"novelId\":\"n1\",\"outcome\":\"waiting_user\",\"limit\":2}", "/api/v1/writing/runs", q("novelId", "n1", "outcome", "waiting_user", "limit", "2")),
                new Case("long.task.get", "{\"taskId\":\"t1\"}", "/api/v1/writing/runs/t1", Map.of()),
                new Case("long.artifact.list", "{\"novelId\":\"n1\",\"status\":\"draft\"}", "/api/v1/review-artifact-summaries", q("novelId", "n1", "status", "draft")),
                new Case("long.artifact.get", "{\"artifactId\":\"a1\"}", "/api/v1/review-artifacts/a1", Map.of()),
                new Case("long.quality.get", "{\"checkId\":\"q1\"}", "/api/v1/quality-checks/q1", Map.of()));

        for (Case item : cases) {
            Result result = run(application, item.command(), item.input());
            assertThat(result.exit()).as(item.command()).isZero();
            assertThat(api.method).as(item.command()).isEqualTo("GET");
            assertThat(api.path).as(item.command()).isEqualTo(item.path());
            assertThat(api.query).as(item.command()).isEqualTo(item.query());
        }
    }

    @Test
    void Artifact有界列表与精确详情保留V1V2判别字段() {
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);

        api.nextResponse = json.readTree("{\"items\":[{\"engineVersion\":2,\"id\":\"a2\","
                + "\"revision\":7,\"actionable\":true}],\"nextCursor\":null}");
        Result summaries = run(
                application,
                "long.artifact.list",
                "{\"novelId\":\"n1\",\"status\":\"awaiting_user\"}");
        assertThat(summaries.exit()).as(summaries.stdout()).isZero();
        assertThat(api.path).isEqualTo("/api/v1/review-artifact-summaries");
        assertThat(summaries.stdout())
                .contains("\"engineVersion\":2", "\"revision\":7", "\"actionable\":true");

        api.nextResponse = json.readTree("{\"engineVersion\":2,\"id\":\"a2\","
                + "\"revision\":7,\"payload\":{\"replacement\":\"完整替换\"}}");
        Result v2Detail = run(
                application,
                "long.artifact.get",
                "{\"artifactId\":\"a2\",\"revision\":7}");
        assertThat(v2Detail.exit()).as(v2Detail.stdout()).isZero();
        assertThat(api.path).isEqualTo("/api/v1/review-artifacts/a2");
        assertThat(api.query).isEqualTo(q("revision", "7"));
        assertThat(v2Detail.stdout())
                .contains("\"engineVersion\":2", "\"revision\":7", "完整替换");

        api.nextResponse = json.readTree(
                "{\"engineVersion\":1,\"id\":\"legacy-a1\",\"revision\":3}");
        Result v1Compatible = run(
                application,
                "long.artifact.get",
                "{\"artifactId\":\"legacy-a1\"}");
        assertThat(v1Compatible.exit()).as(v1Compatible.stdout()).isZero();
        assertThat(api.path).isEqualTo("/api/v1/review-artifacts/legacy-a1");
        assertThat(api.query).isEmpty();
        assertThat(v1Compatible.stdout()).contains("\"engineVersion\":1");
    }

    @Test
    void Artifact精确详情在联网前拒绝非法revision() {
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);

        for (String revision : List.of("null", "0", "-1", "true", "1.5", "\"1\"")) {
            Result invalid = run(
                    application,
                    "long.artifact.get",
                    "{\"artifactId\":\"a1\",\"revision\":" + revision + "}");
            assertThat(invalid.exit()).as(revision).isEqualTo(2);
            assertThat(invalid.stdout()).as(revision)
                    .contains("INVALID_ARTIFACT_REVISION");
            assertThat(api.calls).as(revision).isZero();
        }
    }

    @Test
    void 读取命令拒绝未知字段并支持显式完整文件输出(@TempDir Path directory) throws Exception {
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);

        Result invalid = run(
                application,
                "long.novel.get",
                "{\"novelId\":\"n1\",\"unknown\":true}");
        assertThat(invalid.exit()).isEqualTo(2);
        assertThat(invalid.stdout()).contains("\"code\":\"UNEXPECTED_FIELDS\"");
        assertThat(api.calls).isZero();

        Path output = directory.resolve("chapter.txt");
        Result file = run(
                application,
                "long.chapter.get",
                "{\"chapterId\":\"c1\",\"outputFile\":"
                        + json.writeValueAsString(output.toString()) + "}");
        assertThat(file.exit()).isZero();
        assertThat(Files.readString(output)).isEqualTo("完整正文\r\n末尾");
        assertThat(file.stdout())
                .contains("\"contentFile\":{", "\"bytes\":20")
                .doesNotContain("完整正文");
    }

    private CliApplication application(RecordingApi api) {
        MemoryConfigStore configs = new MemoryConfigStore();
        MemoryCredentialStore credentials = new MemoryCredentialStore();
        configs.save("default", new ProfileConfig("http://127.0.0.1:8000", "nie"));
        credentials.set("default", "http://127.0.0.1:8000", "token");
        return CliApplication.createDefault(new CliDependencies(
                (origin, token) -> api,
                configs,
                credentials,
                prompt -> new char[0],
                () -> false,
                json));
    }

    private Result run(CliApplication application, String command, String input) {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        int exit = application.run(
                List.of(command),
                new ByteArrayInputStream(input.getBytes(StandardCharsets.UTF_8)),
                output,
                new ByteArrayOutputStream());
        return new Result(exit, output.toString(StandardCharsets.UTF_8));
    }

    private static Map<String, List<String>> q(String... values) {
        LinkedHashMap<String, List<String>> result = new LinkedHashMap<>();
        for (int index = 0; index < values.length; index += 2) {
            result.put(values[index], List.of(values[index + 1]));
        }
        return result;
    }

    private record Case(
            String command,
            String input,
            String path,
            Map<String, List<String>> query) {}

    private record Result(int exit, String stdout) {}

    private static final class RecordingApi implements CoreApi {

        private final JsonMapper json;
        private String method;
        private String path;
        private Map<String, List<String>> query = Map.of();
        private int calls;
        private JsonNode nextResponse;

        private RecordingApi(JsonMapper json) {
            this.json = json;
        }

        @Override
        public JsonNode request(String method, String path) {
            return request(method, path, Map.of(), null);
        }

        @Override
        public JsonNode request(String method, String path, JsonNode body) {
            return request(method, path, Map.of(), body);
        }

        @Override
        public JsonNode request(
                String method,
                String path,
                Map<String, List<String>> query,
                JsonNode body) {
            this.method = method;
            this.path = path;
            this.query = query;
            this.calls++;
            if (nextResponse != null) {
                JsonNode response = nextResponse;
                nextResponse = null;
                return response;
            }
            return json.createObjectNode()
                    .put("id", "result")
                    .put("content", "完整正文\r\n末尾")
                    .putNull("nullable");
        }

        @Override
        public LoginResult login(String username, String password) {
            throw new UnsupportedOperationException();
        }

        @Override
        public FileDescriptor download(String method, String path, Path target) {
            throw new UnsupportedOperationException();
        }
    }
}
