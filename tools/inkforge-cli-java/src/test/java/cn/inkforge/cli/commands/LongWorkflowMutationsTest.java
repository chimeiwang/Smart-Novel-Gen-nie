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
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

class LongWorkflowMutationsTest {

    private final JsonMapper json = JsonMapper.builder().build();

    @Test
    void Agent启动恢复取消保持工作流身份与选区约束() {
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);

        assertLastRequest(
                application,
                api,
                "long.agent.start",
                "{\"novelId\":\"n1\",\"chapterId\":\"c1\",\"clientRequestId\":\"agent-start-000001\","
                        + "\"operation\":\"write_chapter\",\"target\":{\"type\":\"chapter\",\"id\":\"c1\"},"
                        + "\"scope\":{\"kind\":\"chapter\",\"chapterId\":\"c1\"},\"writingSessionId\":null,"
                        + "\"targetWordCount\":3000,\"userInstruction\":\"  保持悬念  \"}",
                "POST",
                "/api/v1/writing/runs",
                "{\"clientRequestId\":\"agent-start-000001\",\"workflow\":\"long_serial\",\"novelId\":\"n1\","
                        + "\"chapterId\":\"c1\",\"operation\":\"write_chapter\",\"target\":{\"type\":\"chapter\",\"id\":\"c1\"},"
                        + "\"scope\":{\"kind\":\"chapter\",\"chapterId\":\"c1\"},\"userInstruction\":\"  保持悬念  \","
                        + "\"writingSessionId\":null,\"targetWordCount\":3000}");

        assertLastRequest(
                application,
                api,
                "long.agent.start",
                "{\"novelId\":\"n1\",\"chapterId\":\"c1\",\"clientRequestId\":\"agent-select-00001\","
                        + "\"operation\":\"rewrite_outline_selection\",\"target\":{\"type\":\"chapter\",\"id\":\"c1\"},"
                        + "\"scope\":{\"kind\":\"outline_node\",\"outlineNodeId\":\"o1\"},"
                        + "\"selectionTarget\":{\"resourceType\":\"outline_node_content\",\"resourceId\":\"o1\","
                        + "\"baseUpdatedAt\":\"v1\",\"baseContentHash\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\","
                        + "\"selectionStart\":2,\"selectionEnd\":8,\"selectedTextHash\":\"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\"},"
                        + "\"userInstruction\":\"改写\"}",
                "POST",
                "/api/v1/writing/runs",
                "{\"clientRequestId\":\"agent-select-00001\",\"workflow\":\"long_serial\",\"novelId\":\"n1\","
                        + "\"chapterId\":\"c1\",\"operation\":\"rewrite_outline_selection\",\"target\":{\"type\":\"chapter\",\"id\":\"c1\"},"
                        + "\"scope\":{\"kind\":\"outline_node\",\"outlineNodeId\":\"o1\"},\"userInstruction\":\"改写\","
                        + "\"selectionTarget\":{\"resourceType\":\"outline_node_content\",\"resourceId\":\"o1\",\"baseUpdatedAt\":\"v1\","
                        + "\"baseContentHash\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"selectionStart\":2,\"selectionEnd\":8,"
                        + "\"selectedTextHash\":\"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\"}}\n".trim());

        assertLastRequest(
                application,
                api,
                "long.task.resume",
                "{\"taskId\":\"t/1\",\"clientRequestId\":\"agent-resume-00001\",\"writingSessionId\":\"s1\",\"userMessage\":null}",
                "POST",
                "/api/v1/writing/runs/t%2F1/resume",
                "{\"clientRequestId\":\"agent-resume-00001\",\"writingSessionId\":\"s1\",\"userMessage\":null}");
        assertLastRequest(
                application,
                api,
                "long.task.cancel",
                "{\"taskId\":\"t1\",\"clientRequestId\":\"agent-cancel-00001\"}",
                "POST",
                "/api/v1/writing/runs/t1/cancel",
                "{\"clientRequestId\":\"agent-cancel-00001\"}");
    }

    @Test
    void Agent非法目标和选区在网络前拒绝() {
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);
        for (String payload : List.of(
                "{\"novelId\":\"n1\",\"chapterId\":\"c1\",\"clientRequestId\":\"agent-invalid-0001\",\"operation\":\"write_chapter\",\"target\":{\"type\":\"chapter\",\"id\":\"c2\"},\"scope\":{\"kind\":\"chapter\",\"chapterId\":\"c1\"},\"userInstruction\":\"写\"}",
                "{\"novelId\":\"n1\",\"chapterId\":\"c1\",\"clientRequestId\":\"agent-invalid-0002\",\"operation\":\"rewrite_chapter_selection\",\"target\":{\"type\":\"chapter\",\"id\":\"c1\"},\"scope\":{\"kind\":\"chapter\",\"chapterId\":\"c1\"},\"userInstruction\":\"写\"}")) {
            int before = api.calls.size();
            assertThat(run(application, "long.agent.start", payload).exit()).isEqualTo(2);
            assertThat(api.calls).hasSize(before);
        }
    }

    @Test
    void Artifact决定先验证来源绑定并按草案类型限制编辑字段(@TempDir Path directory) throws Exception {
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);
        Path edited = directory.resolve("完整正文.txt");
        Files.writeString(edited, "正文\r\n末尾😀", StandardCharsets.UTF_8);

        api.nextGet = json.readTree("{\"sourceBindingStatus\":\"verified\",\"payload\":{\"target\":{\"mode\":\"replace_full\"}}}");
        Result approve = run(
                application,
                "long.artifact.approve",
                "{\"artifactId\":\"a/1\",\"clientRequestId\":\"artifact-approve-01\",\"expectedRevision\":2,"
                        + "\"editedContentFile\":" + json.writeValueAsString(edited.toString()) + ",\"selectedUpdateRefs\":[\"u1\"],\"userMessage\":null}");
        assertThat(approve.exit()).as(approve.stdout()).isZero();
        assertThat(api.calls).extracting(Call::method, Call::path)
                .endsWith(
                        org.assertj.core.groups.Tuple.tuple("GET", "/api/v1/review-artifacts/a%2F1"),
                        org.assertj.core.groups.Tuple.tuple("POST", "/api/v1/review-artifacts/a%2F1/decision"));
        assertThat(api.calls.getLast().body().toString()).isEqualTo(
                "{\"clientRequestId\":\"artifact-approve-01\",\"expectedRevision\":2,\"decision\":\"approve\","
                        + "\"editedContent\":\"正文\\r\\n末尾😀\",\"selectedUpdateRefs\":[\"u1\"],\"userMessage\":null}");

        api.nextGet = json.readTree("{\"sourceBindingStatus\":\"verified\",\"payload\":{\"target\":{\"mode\":\"replace_selection\"}}}");
        Result revise = run(
                application,
                "long.artifact.revise",
                "{\"artifactId\":\"a2\",\"clientRequestId\":\"artifact-revise-01\",\"expectedRevision\":3,"
                        + "\"editedReplacement\":\"替换文本\",\"userMessage\":\"请按意见返工\"}");
        assertThat(revise.exit()).as(revise.stdout()).isZero();
        assertThat(api.calls.getLast().body().toString()).isEqualTo(
                "{\"clientRequestId\":\"artifact-revise-01\",\"expectedRevision\":3,\"decision\":\"revise\","
                        + "\"editedReplacement\":\"替换文本\",\"userMessage\":\"请按意见返工\"}");

        int beforeDiscard = api.calls.size();
        assertLastRequest(
                application,
                api,
                "long.artifact.discard",
                "{\"artifactId\":\"a3\",\"clientRequestId\":\"artifact-discard-01\",\"expectedRevision\":1}",
                "POST",
                "/api/v1/review-artifacts/a3/decision",
                "{\"clientRequestId\":\"artifact-discard-01\",\"expectedRevision\":1,\"decision\":\"discard\"}");
        assertThat(api.calls).hasSize(beforeDiscard + 1);
    }

    @Test
    void Artifact未验证来源阻止决定且质量命令保持精确状态机() {
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);

        api.nextGet = json.readTree("{\"sourceBindingStatus\":\"legacy_missing\"}");
        int before = api.calls.size();
        Result blocked = run(
                application,
                "long.artifact.approve",
                "{\"artifactId\":\"a1\",\"clientRequestId\":\"artifact-blocked-01\",\"expectedRevision\":1}");
        assertThat(blocked.exit()).isEqualTo(4);
        assertThat(blocked.stdout()).contains("SOURCE_BINDING_NOT_VERIFIED");
        assertThat(api.calls).hasSize(before + 1);

        assertLastRequest(
                application,
                api,
                "long.quality.run",
                "{\"checkId\":\"q/1\",\"clientRequestId\":\"quality-run-00001\",\"taskId\":null,\"message\":\"重跑\"}",
                "POST",
                "/api/v1/quality-checks/q%2F1/run",
                "{\"clientRequestId\":\"quality-run-00001\",\"taskId\":null,\"message\":\"重跑\"}");
        assertLastRequest(
                application,
                api,
                "long.quality.skip",
                "{\"checkId\":\"q1\",\"expectedUpdatedAt\":\"v1\"}",
                "PATCH",
                "/api/v1/quality-checks/q1",
                "{\"status\":\"skipped\",\"resetResult\":false,\"expectedUpdatedAt\":\"v1\"}");
        assertLastRequest(
                application,
                api,
                "long.quality.reset",
                "{\"checkId\":\"q1\",\"expectedUpdatedAt\":\"v2\"}",
                "PATCH",
                "/api/v1/quality-checks/q1",
                "{\"status\":\"pending\",\"resetResult\":true,\"expectedUpdatedAt\":\"v2\"}");
    }

    private void assertLastRequest(
            CliApplication application,
            RecordingApi api,
            String command,
            String input,
            String method,
            String path,
            String body) {
        Result result = run(application, command, input);
        assertThat(result.exit()).as(command + " " + result.stdout()).isZero();
        Call call = api.calls.getLast();
        assertThat(call.method()).isEqualTo(method);
        assertThat(call.path()).isEqualTo(path);
        assertThat(call.body() == null ? null : call.body().toString()).isEqualTo(body);
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

    private record Result(int exit, String stdout) {}

    private record Call(String method, String path, JsonNode body) {}

    private static final class RecordingApi implements CoreApi {
        private final JsonMapper json;
        private final List<Call> calls = new ArrayList<>();
        private JsonNode nextGet;

        private RecordingApi(JsonMapper json) {
            this.json = json;
        }

        @Override
        public JsonNode request(String method, String path) {
            return request(method, path, null);
        }

        @Override
        public JsonNode request(String method, String path, JsonNode body) {
            calls.add(new Call(method, path, body));
            if (method.equals("GET") && nextGet != null) {
                JsonNode result = nextGet;
                nextGet = null;
                return result;
            }
            return json.createObjectNode().put("id", "ok");
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
