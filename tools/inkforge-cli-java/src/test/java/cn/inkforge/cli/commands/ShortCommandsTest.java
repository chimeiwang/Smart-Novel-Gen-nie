package cn.inkforge.cli.commands;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.cli.config.MemoryConfigStore;
import cn.inkforge.cli.config.MemoryCredentialStore;
import cn.inkforge.cli.config.ProfileConfig;
import cn.inkforge.cli.runtime.CliApplication;
import cn.inkforge.cli.runtime.CliDependencies;
import cn.inkforge.cli.runtime.StableJson;
import cn.inkforge.cli.transport.CoreApi;
import cn.inkforge.cli.transport.FileDescriptor;
import cn.inkforge.cli.transport.LoginResult;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

class ShortCommandsTest {

    private final JsonMapper json = JsonMapper.builder().build();

    @Test
    void 列表创建与Agent启动只发送公共短篇契约(@TempDir Path directory) throws Exception {
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);
        api.enqueue(json.readTree("[{\"id\":\"n1\"}]"));
        Result list = run(application, "short.list", "{}");
        assertThat(list.exit()).as(list.stdout()).isZero();
        assertThat(json.readTree(list.stdout()).at("/data/novels/0/id").textValue())
                .isEqualTo("n1");
        assertThat(api.calls.getLast().query())
                .containsEntry("storyLengthProfile", List.of("short_medium"));

        api.enqueue(json.createObjectNode().put("id", "n2"));
        assertRequest(
                application,
                api,
                "short.create",
                "{\"clientRequestId\":\"short-create-0001\",\"name\":\"短篇\",\"storyLengthProfile\":\"short_medium\",\"sourceText\":\"灵感\"}",
                "POST",
                "/api/v1/novels",
                "{\"clientRequestId\":\"short-create-0001\",\"name\":\"短篇\",\"storyLengthProfile\":\"short_medium\",\"sourceText\":\"灵感\"}");

        Path manifest = cleanSnapshot(directory, "n1", "大纲\r\n", "正文😀");
        assertRequest(
                application,
                api,
                "short.agent.start",
                "{\"clientRequestId\":\"short-agent-00001\",\"novelId\":\"n1\",\"operation\":\"selection\","
                        + "\"documentType\":\"manuscript\",\"chapterId\":\"c1\",\"baseVersionId\":\"v1\","
                        + "\"selectionStart\":1,\"selectionEnd\":3,\"selectedTextHash\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\","
                        + "\"userInstruction\":\"加强冲突\",\"manifestPath\":" + json.writeValueAsString(manifest.toString()) + ","
                        + "\"content\":\"不得发送\",\"target\":\"不得发送\"}",
                "POST",
                "/api/v1/writing/runs",
                "{\"clientRequestId\":\"short-agent-00001\",\"novelId\":\"n1\",\"documentType\":\"manuscript\","
                        + "\"chapterId\":\"c1\",\"baseVersionId\":\"v1\",\"selectionStart\":1,\"selectionEnd\":3,"
                        + "\"selectedTextHash\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"userInstruction\":\"加强冲突\","
                        + "\"workflow\":\"short_medium\",\"operation\":\"replace_selection\"}");
    }

    @Test
    void Pull导出完整文档版本元数据且拒绝覆盖脏快照(@TempDir Path directory) throws Exception {
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);
        enqueuePull(api);
        Result result = run(
                application,
                "short.pull",
                "{\"novelId\":\"n/1\",\"outputDirectory\":"
                        + json.writeValueAsString(directory.toString()) + "}");
        assertThat(result.exit()).as(result.stdout()).isZero();
        assertThat(Files.readString(directory.resolve("outline.md"), StandardCharsets.UTF_8))
                .isEqualTo("完整大纲\r\n尾部😀");
        assertThat(Files.readString(directory.resolve("manuscript.txt"), StandardCharsets.UTF_8))
                .isEqualTo("完整正文\r\n尾部😀");
        JsonNode manifest = json.readTree(Files.readString(directory.resolve("manifest.json")));
        assertThat(manifest.get("novelId").textValue()).isEqualTo("n/1");
        assertThat(manifest.at("/outlineVersions/0/id").textValue()).isEqualTo("ov1");
        assertThat(manifest.at("/manuscriptVersions/0/id").textValue()).isEqualTo("mv1");
        assertThat(manifest.at("/documents/outline/path").textValue())
                .isEqualTo(directory.resolve("outline.md").toAbsolutePath().normalize().toString());
        assertThat(Files.readAllBytes(directory.resolve("manifest.json")))
                .endsWith((byte) '\n');
        assertThat(api.calls).extracting(Call::path).containsExactly(
                "/api/v1/novels/n%2F1/workspace/bootstrap",
                "/api/v1/novels/n%2F1/workspace/planning",
                "/api/v1/novels/n%2F1/versions",
                "/api/v1/novels/n%2F1/versions");

        Files.writeString(directory.resolve("outline.md"), "本地未同步修改", StandardCharsets.UTF_8);
        enqueuePull(api);
        int before = api.calls.size();
        Result dirty = run(
                application,
                "short.pull",
                "{\"novelId\":\"n/1\",\"outputDirectory\":"
                        + json.writeValueAsString(directory.toString()) + "}");
        assertThat(dirty.exit()).isEqualTo(6);
        assertThat(dirty.stdout()).contains("LOCAL_FILE_ERROR");
        assertThat(Files.readString(directory.resolve("outline.md")))
                .isEqualTo("本地未同步修改");
        assertThat(api.calls).hasSize(before + 4);
    }

    @Test
    void DraftSave按Manifest执行CAS并原子推进本地哈希(@TempDir Path directory) throws Exception {
        Path manifest = cleanSnapshot(directory, "n1", "旧大纲", "旧正文");
        Path outline = directory.resolve("outline.md");
        Path manuscript = directory.resolve("manuscript.txt");
        Files.writeString(outline, "新大纲\r\n尾部😀", StandardCharsets.UTF_8);
        Files.writeString(manuscript, "新正文", StandardCharsets.UTF_8);
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);

        api.enqueue(json.readTree("{\"updatedAt\":\"v2\"}"));
        assertRequest(
                application,
                api,
                "short.draft.save",
                "{\"novelId\":\"n1\",\"documentType\":\"outline\",\"filePath\":"
                        + json.writeValueAsString(outline.toString()) + ",\"manifestPath\":"
                        + json.writeValueAsString(manifest.toString()) + "}",
                "PUT",
                "/api/v1/novels/n1/outline",
                "{\"content\":\"新大纲\\r\\n尾部😀\",\"expectedUpdatedAt\":\"v1\"}");
        api.enqueue(json.readTree("{\"updatedAt\":\"v3\"}"));
        assertRequest(
                application,
                api,
                "short.draft.save",
                "{\"novelId\":\"n1\",\"documentType\":\"manuscript\",\"filePath\":"
                        + json.writeValueAsString(manuscript.toString()) + ",\"manifestPath\":"
                        + json.writeValueAsString(manifest.toString()) + ",\"title\":\"全文\"}",
                "PATCH",
                "/api/v1/chapters/c1",
                "{\"title\":\"全文\",\"content\":\"新正文\",\"expectedUpdatedAt\":\"v1\"}");
        JsonNode updated = json.readTree(Files.readString(manifest));
        assertThat(updated.get("outlineUpdatedAt").textValue()).isEqualTo("v2");
        assertThat(updated.get("manuscriptUpdatedAt").textValue()).isEqualTo("v3");
        assertThat(updated.at("/documents/outline/contentHash").textValue())
                .hasSize(64);
        assertThat(updated.at("/documents/manuscript/contentHash").textValue())
                .hasSize(64);
    }

    @Test
    void 七个版本命令保持路由查询确认哈希与完整文件输出(@TempDir Path directory) throws Exception {
        Path manifest = cleanSnapshot(directory.resolve("snapshot"), "n1", "大纲", "正文");
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);

        Path previewFile = directory.resolve("preview.json");
        api.enqueue(json.readTree("{\"id\":\"p1\",\"diff\":{\"tail\":\"差异尾部😀\"}}"));
        Result preview = run(
                application,
                "short.version.preview",
                "{\"novelId\":\"n1\",\"documentType\":\"outline\",\"outputFile\":"
                        + json.writeValueAsString(previewFile.toString()) + "}");
        assertThat(preview.exit()).as(preview.stdout()).isZero();
        assertThat(Files.readString(previewFile)).contains("差异尾部😀");
        assertThat(json.readTree(preview.stdout()).at("/data/diffFile/contentHash").textValue())
                .hasSize(64);

        api.enqueue(json.createObjectNode().put("id", "v2"));
        assertRequest(
                application,
                api,
                "short.version.submit",
                writePayload("n1", manifest, null),
                "POST",
                "/api/v1/novels/n1/versions",
                "{\"clientRequestId\":\"short-version-0001\",\"documentType\":\"outline\","
                        + "\"confirmationHash\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\"}");

        api.enqueue(json.readTree("[{\"id\":\"v1\"}]"));
        Result list = run(
                application,
                "short.version.list",
                "{\"novelId\":\"n1\",\"documentType\":\"outline\",\"chapterId\":null}");
        assertThat(list.exit()).as(list.stdout()).isZero();
        assertThat(api.calls.getLast().query())
                .containsEntry("documentType", List.of("outline"))
                .containsEntry("chapterId", List.of(""));

        Path diffFile = directory.resolve("diff.json");
        api.enqueue(json.readTree("{\"blocks\":[{\"text\":\"尾部😀\"}]}"));
        Result diff = run(
                application,
                "short.version.diff",
                "{\"novelId\":\"n1\",\"fromVersionId\":\"v/1\",\"toVersionId\":\"v2\",\"outputFile\":"
                        + json.writeValueAsString(diffFile.toString()) + "}");
        assertThat(diff.exit()).as(diff.stdout()).isZero();
        assertThat(Files.readString(diffFile)).contains("尾部😀");
        assertThat(api.calls.getLast().query())
                .containsEntry("fromVersionId", List.of("v/1"))
                .containsEntry("toVersionId", List.of("v2"));

        Path contentFile = directory.resolve("version.txt");
        api.enqueue(json.readTree("{\"id\":\"v/1\",\"content\":\"正文\\r\\n尾部😀\"}"));
        Result get = run(
                application,
                "short.version.get",
                "{\"novelId\":\"n1\",\"versionId\":\"v/1\",\"outputFile\":"
                        + json.writeValueAsString(contentFile.toString()) + "}");
        assertThat(get.exit()).as(get.stdout()).isZero();
        assertThat(Files.readString(contentFile)).isEqualTo("正文\r\n尾部😀");
        assertThat(api.calls.getLast().path())
                .isEqualTo("/api/v1/novels/n1/versions/v%2F1");

        for (String action : List.of("adopt", "restore")) {
            api.enqueue(json.createObjectNode().put("id", "ok"));
            assertRequest(
                    application,
                    api,
                    "short.version." + action,
                    writePayload("n1", manifest, "v/1"),
                    "POST",
                    "/api/v1/novels/n1/versions/v%2F1/" + action,
                    "{\"clientRequestId\":\"short-version-0001\",\"documentType\":\"outline\","
                            + "\"confirmationHash\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\"}");
        }
    }

    @Test
    void 受保护写操作在网络前拒绝脏快照与非法确认哈希(@TempDir Path directory) throws Exception {
        Path manifest = cleanSnapshot(directory, "n1", "大纲", "正文");
        Files.writeString(directory.resolve("outline.md"), "脏修改", StandardCharsets.UTF_8);
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);
        Result dirty = run(application, "short.version.submit", writePayload("n1", manifest, null));
        assertThat(dirty.exit()).isEqualTo(6);
        assertThat(api.calls).isEmpty();

        Result hash = run(
                application,
                "short.version.adopt",
                "{\"novelId\":\"n1\",\"versionId\":\"v1\",\"clientRequestId\":\"short-version-0001\","
                        + "\"documentType\":\"outline\",\"confirmationHash\":\"Aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\","
                        + "\"manifestPath\":" + json.writeValueAsString(manifest.toString()) + "}");
        assertThat(hash.exit()).isEqualTo(2);
        assertThat(api.calls).isEmpty();
    }

    private void enqueuePull(RecordingApi api) {
        api.enqueue(json.readTree("{\"currentChapter\":{\"id\":\"c1\",\"content\":\"完整正文\\r\\n尾部😀\",\"updatedAt\":\"m1\"}}"));
        api.enqueue(json.readTree("{\"outline\":{\"content\":\"完整大纲\\r\\n尾部😀\",\"updatedAt\":\"o1\"}}"));
        api.enqueue(json.readTree("[{\"id\":\"ov1\"}]"));
        api.enqueue(json.readTree("[{\"id\":\"mv1\"}]"));
    }

    private Path cleanSnapshot(Path directory, String novelId, String outline, String manuscript)
            throws Exception {
        Files.createDirectories(directory);
        Path outlinePath = directory.resolve("outline.md").toAbsolutePath().normalize();
        Path manuscriptPath = directory.resolve("manuscript.txt").toAbsolutePath().normalize();
        Files.writeString(outlinePath, outline, StandardCharsets.UTF_8);
        Files.writeString(manuscriptPath, manuscript, StandardCharsets.UTF_8);
        String outlineHash = sha256(outline.getBytes(StandardCharsets.UTF_8));
        String manuscriptHash = sha256(manuscript.getBytes(StandardCharsets.UTF_8));
        JsonNode manifest = json.readTree(
                "{\"schemaVersion\":1,\"novelId\":" + json.writeValueAsString(novelId)
                        + ",\"chapterId\":\"c1\",\"outlineUpdatedAt\":\"v1\",\"manuscriptUpdatedAt\":\"v1\","
                        + "\"documents\":{\"outline\":{\"path\":" + json.writeValueAsString(outlinePath.toString())
                        + ",\"contentHash\":\"" + outlineHash + "\"},\"manuscript\":{\"path\":"
                        + json.writeValueAsString(manuscriptPath.toString()) + ",\"contentHash\":\"" + manuscriptHash + "\"}}}");
        Path manifestPath = directory.resolve("manifest.json").toAbsolutePath().normalize();
        Files.writeString(
                manifestPath,
                StableJson.pretty(json, manifest),
                StandardCharsets.UTF_8);
        return manifestPath;
    }

    private String writePayload(String novelId, Path manifest, String versionId) {
        String version = versionId == null ? "" : ",\"versionId\":" + quote(versionId);
        return "{\"novelId\":" + quote(novelId) + version
                + ",\"clientRequestId\":\"short-version-0001\",\"documentType\":\"outline\","
                + "\"confirmationHash\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\","
                + "\"manifestPath\":" + quote(manifest.toString()) + "}";
    }

    private String quote(String value) {
        return json.writeValueAsString(value);
    }

    private static String sha256(byte[] value) throws Exception {
        return java.util.HexFormat.of().formatHex(
                java.security.MessageDigest.getInstance("SHA-256").digest(value));
    }

    private void assertRequest(
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
        private final Deque<JsonNode> responses = new ArrayDeque<>();
        private final List<Call> calls = new ArrayList<>();

        private RecordingApi(JsonMapper json) {
            this.json = json;
        }

        private void enqueue(JsonNode response) {
            responses.addLast(response);
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
            calls.add(new Call(method, path, new LinkedHashMap<>(query), body));
            return responses.isEmpty()
                    ? json.createObjectNode().put("id", "ok")
                    : responses.removeFirst();
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
