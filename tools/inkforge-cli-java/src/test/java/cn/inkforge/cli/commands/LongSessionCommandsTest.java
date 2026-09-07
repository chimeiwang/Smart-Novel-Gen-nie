package cn.inkforge.cli.commands;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.cli.config.MemoryConfigStore;
import cn.inkforge.cli.config.MemoryCredentialStore;
import cn.inkforge.cli.config.ProfileConfig;
import cn.inkforge.cli.runtime.CliApplication;
import cn.inkforge.cli.runtime.CliDependencies;
import cn.inkforge.cli.transport.CoreApi;
import cn.inkforge.cli.transport.CoreTransportException;
import cn.inkforge.cli.transport.FileDescriptor;
import cn.inkforge.cli.transport.LoginResult;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.node.ObjectNode;

class LongSessionCommandsTest {
    private final JsonMapper json = JsonMapper.builder().build();

    @Test
    void 会话创建保留标题省略空值和原始完整响应且只调用一次() {
        for (String title : List.of("", ",\"title\":null", ",\"title\":\"  验收😀\\r\\n  \"")) {
            RecordingApi api = new RecordingApi();
            ObjectNode body = (ObjectNode) json.readTree("{\"novelId\":\"n\",\"chapterId\":\"c\"" + title + "}");
            ObjectNode payload = body.deepCopy().put("profile", "default");
            Result result = run(application(api, true), payload);
            assertThat(result.exit()).isZero();
            assertThat(result.output().path("data")).isEqualTo(api.response);
            assertThat(api.calls).isEqualTo(1);
            assertThat(api.body).isEqualTo(body);
        }
    }

    @Test
    void 字段按Unicode码点计数并在发送前拒绝超长和非法类型() {
        for (String field : List.of("novelId", "chapterId", "title")) {
            int maximum = field.equals("title") ? 500 : 256;
            RecordingApi api = new RecordingApi();
            CliApplication app = application(api, true);
            ObjectNode payload = json.createObjectNode().put("novelId", "n").put("chapterId", "c");
            payload.put(field, "😀".repeat(maximum));
            assertThat(run(app, payload).exit()).isZero();
            assertThat(api.body).isEqualTo(payload);
            for (JsonNode value : List.of(
                    json.getNodeFactory().stringNode("😀".repeat(maximum + 1)),
                    json.getNodeFactory().stringNode(""),
                    json.getNodeFactory().booleanNode(true),
                    json.getNodeFactory().numberNode(1),
                    json.createArrayNode(), json.createObjectNode())) {
                payload.set(field, value);
                Result result = run(app, payload);
                assertThat(result.exit()).isEqualTo(2);
                assertThat(result.output().path("error").path("code").asString()).isEqualTo("INVALID_FIELD");
                assertThat(api.calls).isEqualTo(1);
            }
        }
    }

    @Test
    void 缺失ID和未知字段在网络前拒绝且不伪造幂等参数() {
        RecordingApi api = new RecordingApi();
        CliApplication app = application(api, true);
        for (String input : List.of("{}", "{\"novelId\":\"n\"}", "{\"chapterId\":\"c\"}")) {
            Result result = run(app, (ObjectNode) json.readTree(input));
            assertThat(result.exit()).isEqualTo(2);
            assertThat(result.output().path("error").path("code").asString()).isEqualTo("FIELD_REQUIRED");
        }
        for (String field : List.of("clientRequestId", "origin", "token", "model", "outputFile", "unknown")) {
            Result result = run(app, json.createObjectNode()
                    .put("novelId", "n").put("chapterId", "c").put(field, "value"));
            assertThat(result.exit()).isEqualTo(2);
            assertThat(result.output().path("error").path("code").asString()).isEqualTo("UNEXPECTED_FIELDS");
        }
        assertThat(api.calls).isZero();
    }

    @Test
    void 必须有原身份且网络结果不确定不重试创建() {
        RecordingApi api = new RecordingApi();
        ObjectNode payload = json.createObjectNode().put("novelId", "n").put("chapterId", "c");
        Result unauthenticated = run(application(api, false), payload);
        assertThat(unauthenticated.exit()).isEqualTo(3);
        assertThat(unauthenticated.output().path("error").path("code").asString()).isEqualTo("AUTH_REQUIRED");
        assertThat(api.calls).isZero();
        api.fail = true;
        Result uncertain = run(application(api, true), payload);
        assertThat(uncertain.exit()).isEqualTo(5);
        assertThat(uncertain.output().path("error").path("code").asString()).isEqualTo("CORE_TRANSPORT_ERROR");
        assertThat(api.calls).isEqualTo(1);
    }

    private CliApplication application(RecordingApi api, boolean authenticated) {
        MemoryConfigStore configs = new MemoryConfigStore();
        MemoryCredentialStore credentials = new MemoryCredentialStore();
        if (authenticated) {
            configs.save("default", new ProfileConfig("http://127.0.0.1:8000", "nie"));
            credentials.set("default", "http://127.0.0.1:8000", "test-session");
        }
        return CliApplication.createDefault(new CliDependencies(
                (origin, token) -> api, configs, credentials,
                prompt -> new char[0], () -> false, json));
    }

    private Result run(CliApplication app, ObjectNode payload) {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        int code = app.run(List.of("long.session.create"),
                new ByteArrayInputStream(json.writeValueAsBytes(payload)), output, new ByteArrayOutputStream());
        return new Result(code, json.readTree(output.toString(StandardCharsets.UTF_8)));
    }

    private record Result(int exit, JsonNode output) {}

    private final class RecordingApi implements CoreApi {
        private int calls;
        private boolean fail;
        private JsonNode body;
        private final JsonNode response = json.readTree(
                "{\"id\":\"s\",\"novelId\":\"n\",\"chapterId\":\"c\",\"title\":\"验收\",\"phase\":\"idle\",\"messages\":[]}");

        @Override public JsonNode request(String method, String path) { return request(method, path, null); }
        @Override public JsonNode request(String method, String path, JsonNode value) {
            assertThat(method).isEqualTo("POST");
            assertThat(path).isEqualTo("/api/v1/writing/sessions");
            calls++;
            body = value.deepCopy();
            if (fail) throw new CoreTransportException();
            return response;
        }
        @Override public LoginResult login(String username, String password) { throw new AssertionError("不应重新登录"); }
        @Override public FileDescriptor download(String method, String path, Path target) { throw new AssertionError("不应下载"); }
    }
}
