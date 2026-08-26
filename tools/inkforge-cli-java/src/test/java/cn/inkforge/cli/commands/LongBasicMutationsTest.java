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
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

class LongBasicMutationsTest {

    private final JsonMapper json = JsonMapper.builder().build();

    @Test
    void 小说章节规划与文风命令发送精确请求(@TempDir Path directory) throws Exception {
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);

        assertRequest(
                application,
                api,
                "long.novel.create",
                "{\"name\":\"  长篇  \",\"summary\":null,\"targetTotalWordCount\":1000000}",
                "POST",
                "/api/v1/novels",
                "{\"name\":\"长篇\",\"summary\":null,\"targetTotalWordCount\":1000000,\"storyLengthProfile\":\"long_serial\"}");
        assertRequest(
                application,
                api,
                "long.novel.summary.save",
                "{\"novelId\":\"n/1\",\"summary\":\"完整摘要\",\"expectedUpdatedAt\":\"v1\"}",
                "PUT",
                "/api/v1/novels/n%2F1/summary",
                "{\"summary\":\"完整摘要\",\"expectedUpdatedAt\":\"v1\"}");
        assertRequest(
                application,
                api,
                "long.chapter.create",
                "{\"novelId\":\"n1\"}",
                "POST",
                "/api/v1/novels/n1/chapters",
                null);

        Path content = directory.resolve("chapter.txt");
        Files.writeString(content, "正文\r\n末尾", StandardCharsets.UTF_8);
        assertRequest(
                application,
                api,
                "long.chapter.save",
                "{\"chapterId\":\"c1\",\"title\":\"第一章\",\"contentFile\":"
                        + json.writeValueAsString(content.toString())
                        + ",\"expectedUpdatedAt\":\"v2\"}",
                "PATCH",
                "/api/v1/chapters/c1",
                "{\"title\":\"第一章\",\"content\":\"正文\\r\\n末尾\",\"expectedUpdatedAt\":\"v2\"}");
        assertRequest(
                application,
                api,
                "long.chapter.status",
                "{\"chapterId\":\"c1\",\"status\":\"drafting\",\"expectedUpdatedAt\":\"v3\"}",
                "PATCH",
                "/api/v1/chapters/c1/status",
                "{\"status\":\"drafting\",\"expectedUpdatedAt\":\"v3\"}");
        assertRequest(
                application,
                api,
                "long.chapter.progress.save",
                "{\"chapterId\":\"c1\",\"content\":\"进展\",\"expectedUpdatedAt\":null}",
                "PUT",
                "/api/v1/chapters/c1/progress",
                "{\"content\":\"进展\",\"expectedUpdatedAt\":null}");

        for (String[] command : new String[][] {
            {"long.outline.save", "outline"},
            {"long.lore.story-background.save", "story-background"},
            {"long.lore.world-setting.save", "world-setting"},
            {"long.lore.story-progress.save", "story-progress"}
        }) {
            assertRequest(
                    application,
                    api,
                    command[0],
                    "{\"novelId\":\"n1\",\"content\":\"完整内容\",\"expectedUpdatedAt\":\"v4\"}",
                    "PUT",
                    "/api/v1/novels/n1/" + command[1],
                    "{\"content\":\"完整内容\",\"expectedUpdatedAt\":\"v4\"}");
        }
        assertRequest(
                application,
                api,
                "long.lore.writing-bible.save",
                "{\"novelId\":\"n1\",\"expectedUpdatedAt\":null,\"data\":{\"storyLengthProfile\":\"long_serial\",\"genre\":\"悬疑\"}}",
                "PUT",
                "/api/v1/novels/n1/writing-bible",
                "{\"storyLengthProfile\":\"long_serial\",\"genre\":\"悬疑\",\"expectedUpdatedAt\":null}");
        assertRequest(
                application,
                api,
                "long.plot-progress.save",
                "{\"novelId\":\"n1\",\"expectedUpdatedAt\":\"v5\",\"data\":{\"currentStage\":\"第一幕\",\"nextMilestone\":null}}",
                "PUT",
                "/api/v1/novels/n1/plot-progress",
                "{\"currentStage\":\"第一幕\",\"nextMilestone\":null,\"expectedUpdatedAt\":\"v5\"}");
        assertRequest(
                application,
                api,
                "long.style.apply",
                "{\"novelId\":\"n1\",\"styleId\":\"s1\",\"expectedStyleId\":null}",
                "PATCH",
                "/api/v1/novels/n1/applied-style",
                "{\"styleId\":\"s1\",\"expectedStyleId\":null}");
        assertRequest(
                application,
                api,
                "long.style.clear",
                "{\"novelId\":\"n1\",\"expectedStyleId\":\"s1\"}",
                "PATCH",
                "/api/v1/novels/n1/applied-style",
                "{\"styleId\":null,\"expectedStyleId\":\"s1\"}");
    }

    @Test
    void 大纲节点命令保留幂等与CAS且本地预检先于网络() {
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);
        assertRequest(
                application,
                api,
                "long.outline-node.create",
                "{\"novelId\":\"n1\",\"clientRequestId\":\"outline-create-0001\",\"data\":{\"title\":\"第一幕\",\"kind\":\"stage\",\"chapterStartOrder\":1,\"chapterEndOrder\":3}}",
                "POST",
                "/api/v1/novels/n1/outline-nodes",
                "{\"title\":\"第一幕\",\"kind\":\"stage\",\"chapterStartOrder\":1,\"chapterEndOrder\":3,\"clientRequestId\":\"outline-create-0001\"}");
        assertRequest(
                application,
                api,
                "long.outline-node.update",
                "{\"novelId\":\"n1\",\"outlineNodeId\":\"o1\",\"expectedUpdatedAt\":\"v1\",\"data\":{\"status\":\"in_progress\"}}",
                "PATCH",
                "/api/v1/novels/n1/outline-nodes/o1",
                "{\"status\":\"in_progress\",\"expectedUpdatedAt\":\"v1\"}");
        assertRequest(
                application,
                api,
                "long.outline-node.delete",
                "{\"novelId\":\"n1\",\"outlineNodeId\":\"o1\",\"expectedUpdatedAt\":\"v2\"}",
                "DELETE",
                "/api/v1/novels/n1/outline-nodes/o1",
                "{\"expectedUpdatedAt\":\"v2\"}");

        int before = api.calls;
        Result invalid = run(
                application,
                "long.outline-node.create",
                "{\"novelId\":\"n1\",\"clientRequestId\":\"short\",\"data\":{\"title\":\"幕\",\"kind\":\"stage\"}}");
        assertThat(invalid.exit()).isEqualTo(2);
        assertThat(api.calls).isEqualTo(before);
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
        assertThat(api.method).isEqualTo(method);
        assertThat(api.path).isEqualTo(path);
        assertThat(api.body == null ? null : api.body.toString()).isEqualTo(body);
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

    private static final class RecordingApi implements CoreApi {

        private final JsonMapper json;
        private String method;
        private String path;
        private JsonNode body;
        private int calls;

        private RecordingApi(JsonMapper json) {
            this.json = json;
        }

        @Override
        public JsonNode request(String method, String path) {
            return request(method, path, null);
        }

        @Override
        public JsonNode request(String method, String path, JsonNode body) {
            this.method = method;
            this.path = path;
            this.body = body;
            calls++;
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
