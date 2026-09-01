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
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.node.ObjectNode;

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
                "{\"novelId\":\"n1\",\"chapterId\":\"c1\",\"clientRequestId\":\"agent-answer-00001\","
                        + "\"operation\":\"answer_question\",\"target\":{\"type\":\"chapter\",\"id\":\"c1\"},"
                        + "\"scope\":{\"kind\":\"chapter\",\"chapterId\":\"c1\"},\"writingSessionId\":\"s1\","
                        + "\"userInstruction\":\"这一章的主要冲突是什么？\"}",
                "POST",
                "/api/v1/writing/runs",
                "{\"clientRequestId\":\"agent-answer-00001\",\"workflow\":\"long_serial\",\"novelId\":\"n1\","
                        + "\"chapterId\":\"c1\",\"operation\":\"answer_question\",\"target\":{\"type\":\"chapter\",\"id\":\"c1\"},"
                        + "\"scope\":{\"kind\":\"chapter\",\"chapterId\":\"c1\"},\"userInstruction\":\"这一章的主要冲突是什么？\","
                        + "\"writingSessionId\":\"s1\"}");

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

        for (String sessionField : List.of(
                "",
                "\"writingSessionId\":null,",
                "\"writingSessionId\":\"\",",
                "\"writingSessionId\":7,")) {
            int beforeInvalidSession = api.calls.size();
            Result invalidSession = run(
                    application,
                    "long.agent.start",
                    "{\"novelId\":\"n1\",\"chapterId\":\"c1\",\"clientRequestId\":\"agent-invalid-0003\","
                            + "\"operation\":\"answer_question\",\"target\":{\"type\":\"chapter\",\"id\":\"c1\"},"
                            + "\"scope\":{\"kind\":\"chapter\",\"chapterId\":\"c1\"},"
                            + sessionField
                            + "\"userInstruction\":\"问\"}");
            assertThat(invalidSession.exit()).as(sessionField).isEqualTo(2);
            assertThat(invalidSession.stdout()).as(sessionField)
                    .contains("WRITING_SESSION_REQUIRED");
            assertThat(api.calls).as(sessionField).hasSize(beforeInvalidSession);
        }
    }

    @Test
    void Agent用户指令Unicode全空白在网络前拒绝且正常中文逐字发送() {
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);
        List<String> blankInstructions = List.of(
                "\u3000",
                "\u00a0",
                "\u0085",
                "\n\u3000\u00a0\t\r");

        for (int index = 0; index < blankInstructions.size(); index++) {
            int before = api.calls.size();
            Result rejected = run(
                    application,
                    "long.agent.start",
                    answerStartPayload(
                                    "agent-blank-unicode-" + index,
                                    blankInstructions.get(index))
                            .toString());
            assertThat(rejected.exit()).isEqualTo(2);
            assertThat(rejected.stdout()).contains("INVALID_USER_INSTRUCTION");
            assertThat(api.calls).hasSize(before);
        }

        String instruction = " \u3000正常中文\u00a0 ";
        int beforeAccepted = api.calls.size();
        Result accepted = run(
                application,
                "long.agent.start",
                answerStartPayload("agent-unicode-normal-01", instruction).toString());
        assertThat(accepted.exit()).as(accepted.stdout()).isZero();
        assertThat(api.calls).hasSize(beforeAccepted + 1);
        assertThat(api.calls.getLast().method()).isEqualTo("POST");
        assertThat(api.calls.getLast().path()).isEqualTo("/api/v1/writing/runs");
        assertThat(api.calls.getLast().body().get("userInstruction").textValue())
                .isEqualTo(instruction);
    }

    @Test
    void Artifact批准返工先验证详情来源并按草案类型限制编辑字段(@TempDir Path directory) throws Exception {
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);
        Path edited = directory.resolve("完整正文.txt");
        Files.writeString(edited, "正文\r\n末尾😀", StandardCharsets.UTF_8);

        api.nextGet = artifact(1, "a/1", 2, "verified", "replace_full");
        Result approve = run(
                application,
                "long.artifact.approve",
                "{\"artifactId\":\"a/1\",\"clientRequestId\":\"artifact-approve-01\",\"engineVersion\":1,\"expectedRevision\":2,"
                        + "\"editedContentFile\":" + json.writeValueAsString(edited.toString()) + ",\"selectedUpdateRefs\":[\"u1\"],\"userMessage\":null}");
        assertThat(approve.exit()).as(approve.stdout()).isZero();
        assertThat(api.calls).extracting(Call::method, Call::path)
                .endsWith(
                        org.assertj.core.groups.Tuple.tuple("GET", "/api/v1/review-artifacts/a%2F1"),
                        org.assertj.core.groups.Tuple.tuple("POST", "/api/v1/review-artifacts/a%2F1/decision"));
        assertThat(api.calls.get(api.calls.size() - 2).query())
                .isEqualTo(Map.of("revision", List.of("2")));
        assertThat(api.calls.getLast().body().toString()).isEqualTo(
                "{\"engineVersion\":1,\"clientRequestId\":\"artifact-approve-01\",\"expectedRevision\":2,\"decision\":\"approve\","
                        + "\"editedContent\":\"正文\\r\\n末尾😀\",\"selectedUpdateRefs\":[\"u1\"],\"userMessage\":null}");

        api.nextGet = artifact(1, "a2", 3, "verified", "replace_selection");
        Result revise = run(
                application,
                "long.artifact.revise",
                "{\"artifactId\":\"a2\",\"clientRequestId\":\"artifact-revise-01\",\"engineVersion\":1,\"expectedRevision\":3,"
                        + "\"editedReplacement\":\"替换文本\",\"userMessage\":\"请按意见返工\"}");
        assertThat(revise.exit()).as(revise.stdout()).isZero();
        assertThat(api.calls.getLast().body().toString()).isEqualTo(
                "{\"engineVersion\":1,\"clientRequestId\":\"artifact-revise-01\",\"expectedRevision\":3,\"decision\":\"revise\","
                        + "\"editedReplacement\":\"替换文本\",\"userMessage\":\"请按意见返工\"}");

        int beforeDiscard = api.calls.size();
        assertLastRequest(
                application,
                api,
                "long.artifact.discard",
                "{\"artifactId\":\"a3\",\"clientRequestId\":\"artifact-discard-01\",\"engineVersion\":2,\"expectedRevision\":1}",
                "POST",
                "/api/v1/review-artifacts/a3/decision",
                "{\"engineVersion\":2,\"clientRequestId\":\"artifact-discard-01\",\"expectedRevision\":1,\"decision\":\"discard\"}");
        assertThat(api.calls).hasSize(beforeDiscard + 1);
        assertThat(api.calls.get(beforeDiscard).method()).isEqualTo("POST");
    }

    @Test
    void ArtifactV1丢弃在草案物理删除后仍直接幂等重放相同请求() {
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);
        String input = "{\"artifactId\":\"deleted-v1\",\"clientRequestId\":\"artifact-v1-discard-replay\","
                + "\"expectedRevision\":5}";
        String expectedBody = "{\"engineVersion\":1,\"clientRequestId\":\"artifact-v1-discard-replay\","
                + "\"expectedRevision\":5,\"decision\":\"discard\"}";

        Result first = run(application, "long.artifact.discard", input);
        Result replay = run(application, "long.artifact.discard", input);

        assertThat(first.exit()).as(first.stdout()).isZero();
        assertThat(replay.exit()).as(replay.stdout()).isZero();
        assertThat(api.calls).hasSize(2).allSatisfy(call -> {
            assertThat(call.method()).isEqualTo("POST");
            assertThat(call.path())
                    .isEqualTo("/api/v1/review-artifacts/deleted-v1/decision");
            assertThat(call.query()).isEmpty();
            assertThat(call.body().toString()).isEqualTo(expectedBody);
        });
    }

    @Test
    void Artifact决定省略引擎仅兼容V1且显式值始终核对详情引擎() {
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);

        api.nextGet = artifact(1, "a1", 1, "verified", "replace_full");
        Result legacyV1 = run(
                application,
                "long.artifact.approve",
                "{\"artifactId\":\"a1\",\"clientRequestId\":\"artifact-engine-missing\","
                        + "\"expectedRevision\":1}");
        assertThat(legacyV1.exit()).as(legacyV1.stdout()).isZero();
        assertThat(api.calls.getLast().body().path("engineVersion").intValue()).isEqualTo(1);

        api.nextGet = artifact(2, "a2", 1, "verified", "replace_selection");
        Result omittedV2 = run(
                application,
                "long.artifact.approve",
                "{\"artifactId\":\"a2\",\"clientRequestId\":\"artifact-v2-engine-missing\","
                        + "\"expectedRevision\":1}");
        assertThat(omittedV2.exit()).isEqualTo(4);
        assertThat(omittedV2.stdout()).contains("ARTIFACT_ENGINE_VERSION_MISMATCH");

        int callsBeforeInvalid = api.calls.size();

        for (String invalidVersion : List.of("null", "0", "3", "true", "1.5", "\"2\"")) {
            Result invalid = run(
                    application,
                    "long.artifact.discard",
                    "{\"artifactId\":\"a1\",\"clientRequestId\":\"artifact-engine-invalid\","
                            + "\"engineVersion\":" + invalidVersion + ",\"expectedRevision\":1}");
            assertThat(invalid.exit()).as(invalidVersion).isEqualTo(2);
            assertThat(invalid.stdout()).as(invalidVersion)
                    .contains("INVALID_ENGINE_VERSION");
            assertThat(api.calls).as(invalidVersion).hasSize(callsBeforeInvalid);
        }

        api.nextGet = artifact(2, "a1", 1, "verified", "replace_selection");
        Result mismatch = run(
                application,
                "long.artifact.approve",
                "{\"artifactId\":\"a1\",\"clientRequestId\":\"artifact-engine-mismatch\","
                        + "\"engineVersion\":1,\"expectedRevision\":1}");
        assertThat(mismatch.exit()).isEqualTo(4);
        assertThat(mismatch.stdout()).contains("ARTIFACT_ENGINE_VERSION_MISMATCH");
        assertThat(api.calls).hasSize(callsBeforeInvalid + 1);
        assertThat(api.calls.getLast().method()).isEqualTo("GET");
    }

    @Test
    void ArtifactV2只允许选区批准且V1返工保持可选说明() {
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);

        api.nextGet = artifact(2, "a2", 7, "verified", "replace_selection");
        Result approve = run(
                application,
                "long.artifact.approve",
                "{\"artifactId\":\"a2\",\"clientRequestId\":\"artifact-v2-approve\",\"engineVersion\":2,\"expectedRevision\":7,"
                        + "\"editedReplacement\":\"新选区\"}");
        assertThat(approve.exit()).as(approve.stdout()).isZero();
        assertThat(api.calls.getLast().body().toString()).isEqualTo(
                "{\"engineVersion\":2,\"clientRequestId\":\"artifact-v2-approve\",\"expectedRevision\":7,"
                        + "\"decision\":\"approve\",\"editedReplacement\":\"新选区\"}");

        api.nextGet = artifact(2, "a2", 8, "verified", "replace_selection");
        Result revise = run(
                application,
                "long.artifact.revise",
                "{\"artifactId\":\"a2\",\"clientRequestId\":\"artifact-v2-revise-01\",\"engineVersion\":2,\"expectedRevision\":8,"
                        + "\"userMessage\":\"保留含义，压缩动作\"}");
        assertThat(revise.exit()).as(revise.stdout()).isZero();
        assertThat(api.calls.getLast().body().toString()).isEqualTo(
                "{\"engineVersion\":2,\"clientRequestId\":\"artifact-v2-revise-01\",\"expectedRevision\":8,"
                        + "\"decision\":\"revise\",\"userMessage\":\"保留含义，压缩动作\"}");

        int beforeInvalid = api.calls.size();
        api.nextGet = artifact(2, "a2", 9, "verified", "replace_selection");
        Result invalid = run(
                application,
                "long.artifact.approve",
                "{\"artifactId\":\"a2\",\"clientRequestId\":\"artifact-v2-invalid-1\",\"engineVersion\":2,\"expectedRevision\":9,"
                        + "\"editedContent\":\"不允许\"}");
        assertThat(invalid.exit()).isEqualTo(2);
        assertThat(invalid.stdout()).contains("V2_EDIT_FIELDS_FORBIDDEN");
        assertThat(api.calls).hasSize(beforeInvalid + 1);

        int beforeInvalidRevise = api.calls.size();
        api.nextGet = artifact(2, "a2", 10, "verified", "replace_selection");
        Result invalidRevise = run(
                application,
                "long.artifact.revise",
                "{\"artifactId\":\"a2\",\"clientRequestId\":\"artifact-v2-invalid-2\",\"engineVersion\":2,\"expectedRevision\":10,"
                        + "\"editedReplacement\":\"不能在返工时编辑\",\"userMessage\":\"重新写\"}");
        assertThat(invalidRevise.exit()).isEqualTo(2);
        assertThat(invalidRevise.stdout()).contains("V2_EDIT_FIELDS_FORBIDDEN");
        assertThat(api.calls).hasSize(beforeInvalidRevise + 1);

        int beforeMissingMessage = api.calls.size();
        api.nextGet = artifact(2, "a2", 11, "verified", "replace_selection");
        Result missingMessage = run(
                application,
                "long.artifact.revise",
                "{\"artifactId\":\"a2\",\"clientRequestId\":\"artifact-v2-invalid-3\",\"engineVersion\":2,\"expectedRevision\":11}");
        assertThat(missingMessage.exit()).isEqualTo(2);
        assertThat(missingMessage.stdout()).contains("USER_MESSAGE_REQUIRED");
        assertThat(api.calls).hasSize(beforeMissingMessage + 1);

        api.nextGet = artifact(1, "a1", 4, "verified", "replace_full");
        Result v1Revise = run(
                application,
                "long.artifact.revise",
                "{\"artifactId\":\"a1\",\"clientRequestId\":\"artifact-v1-revise-01\",\"engineVersion\":1,\"expectedRevision\":4}");
        assertThat(v1Revise.exit()).as(v1Revise.stdout()).isZero();
        assertThat(api.calls.getLast().body().toString()).isEqualTo(
                "{\"engineVersion\":1,\"clientRequestId\":\"artifact-v1-revise-01\",\"expectedRevision\":4,"
                        + "\"decision\":\"revise\"}");
    }

    @Test
    void Artifact未验证来源阻止决定且质量命令保持精确状态机() {
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);

        api.nextGet = artifact(1, "a1", 1, "legacy_missing", "replace_full");
        int before = api.calls.size();
        Result blocked = run(
                application,
                "long.artifact.approve",
                "{\"artifactId\":\"a1\",\"clientRequestId\":\"artifact-blocked-01\",\"engineVersion\":1,\"expectedRevision\":1}");
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

    private JsonNode artifact(
            int engineVersion,
            String artifactId,
            int revision,
            String sourceBindingStatus,
            String targetMode) {
        return json.readTree("{\"engineVersion\":" + engineVersion
                + ",\"id\":" + json.writeValueAsString(artifactId)
                + ",\"revision\":" + revision
                + ",\"sourceBindingStatus\":" + json.writeValueAsString(sourceBindingStatus)
                + ",\"payload\":{\"target\":{\"mode\":"
                + json.writeValueAsString(targetMode) + "}}}");
    }

    private ObjectNode answerStartPayload(String clientRequestId, String instruction) {
        ObjectNode payload = json.createObjectNode();
        payload.put("novelId", "n1");
        payload.put("chapterId", "c1");
        payload.put("clientRequestId", clientRequestId);
        payload.put("operation", "answer_question");
        payload.set("target", json.valueToTree(Map.of("type", "chapter", "id", "c1")));
        payload.set(
                "scope",
                json.valueToTree(Map.of("kind", "chapter", "chapterId", "c1")));
        payload.put("writingSessionId", "s1");
        payload.put("userInstruction", instruction);
        return payload;
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

    private record Call(
            String method,
            String path,
            Map<String, List<String>> query,
            JsonNode body) {}

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
            return request(method, path, Map.of(), body);
        }

        @Override
        public JsonNode request(
                String method,
                String path,
                Map<String, List<String>> query,
                JsonNode body) {
            calls.add(new Call(method, path, Map.copyOf(query), body));
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
