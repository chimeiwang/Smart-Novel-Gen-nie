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
import java.util.stream.Stream;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.junit.jupiter.params.provider.ValueSource;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

class LongChapterEditUnicodeTest {
    private final JsonMapper json = JsonMapper.builder().build();
    @TempDir Path directory;

    @ParameterizedTest
    @MethodSource("blankEdits")
    void 正文V2编辑拒绝仅BOM和空白混合BOM且不发送决定(String field, String content) throws Exception {
        RecordingApi api = new RecordingApi();
        Result result = execute(api, field, content);
        assertThat(result.exit()).as(result.output()).isEqualTo(2);
        assertThat(result.output()).contains("INVALID_EDITED_CONTENT");
        assertThat(api.methods).containsExactly("GET");
    }

    @ParameterizedTest
    @ValueSource(strings = {"editedContent", "editedContentFile"})
    void 有效完整正文的BOM空白换行和Unicode必须原样保留(String field) throws Exception {
        String content = "\uFEFF  正文😀e\u0301\r\n\uFEFF";
        RecordingApi api = new RecordingApi();
        Result result = execute(api, field, content);
        assertThat(result.exit()).as(result.output()).isZero();
        assertThat(api.methods).containsExactly("GET", "POST");
        assertThat(api.body.path("editedContent").textValue()).isEqualTo(content);
    }

    private static Stream<Arguments> blankEdits() {
        return Stream.of("editedContent", "editedContentFile").flatMap(field ->
                Stream.of("\uFEFF", " \n\t\u0085\u00a0\uFEFF\u3000").map(content -> Arguments.of(field, content)));
    }

    @ParameterizedTest
    @ValueSource(ints = {0x1c, 0x1d, 0x1e, 0x1f})
    void 正文判空使用契约空白集合而非Java广义空白(int codepoint) throws Exception {
        String content = Character.toString(codepoint);
        RecordingApi api = new RecordingApi();
        Result result = execute(api, "editedContent", content);
        assertThat(result.exit()).as(result.output()).isZero();
        assertThat(api.body.path("editedContent").textValue()).isEqualTo(content);
    }

    private Result execute(RecordingApi api, String field, String content) throws Exception {
        Path source = directory.resolve("完整正文.txt");
        Files.writeString(source, content, StandardCharsets.UTF_8);
        var payload = json.createObjectNode().put("artifactId", "draft-1").put("engineVersion", 2)
                .put("expectedRevision", 7).put("clientRequestId", "unicode-chapter-edit-0001")
                .put(field, field.endsWith("File") ? source.toString() : content);
        MemoryConfigStore configs = new MemoryConfigStore();
        MemoryCredentialStore credentials = new MemoryCredentialStore();
        configs.save("default", new ProfileConfig("http://127.0.0.1:8000", "test"));
        credentials.set("default", "http://127.0.0.1:8000", "test-only-token");
        CliApplication application = CliApplication.createDefault(new CliDependencies(
                (origin, token) -> api, configs, credentials, prompt -> new char[0], () -> false, json));
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        int exit = application.run(List.of("long.artifact.approve"),
                new ByteArrayInputStream(payload.toString().getBytes(StandardCharsets.UTF_8)), output,
                new ByteArrayOutputStream());
        return new Result(exit, output.toString(StandardCharsets.UTF_8));
    }

    private record Result(int exit, String output) {}

    private final class RecordingApi implements CoreApi {
        private final List<String> methods = new ArrayList<>();
        private JsonNode body;
        @Override public JsonNode request(String method, String path) { return request(method, path, null); }
        @Override public JsonNode request(String method, String path, JsonNode value) {
            return request(method, path, Map.of(), value);
        }
        @Override public JsonNode request(String method, String path, Map<String, List<String>> query, JsonNode value) {
            methods.add(method);
            if (method.equals("GET")) {
                assertThat(query).isEqualTo(Map.of("revision", List.of("7")));
                return json.readTree("""
                        {"id":"draft-1","revision":7,"engineVersion":2,"sourceBindingStatus":"verified",
                         "kind":"chapter_draft","payload":{"operation":"write_chapter","target":{"mode":"existing_chapter"}}}
                        """);
            }
            body = value;
            return json.createObjectNode().put("runId", "run-1").put("status", "completed");
        }
        @Override public LoginResult login(String username, String password) { throw new UnsupportedOperationException(); }
        @Override public FileDescriptor download(String method, String path, Path target) { throw new UnsupportedOperationException(); }
    }
}
