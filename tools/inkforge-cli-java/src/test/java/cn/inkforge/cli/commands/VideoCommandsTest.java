package cn.inkforge.cli.commands;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.cli.config.MemoryConfigStore;
import cn.inkforge.cli.config.MemoryCredentialStore;
import cn.inkforge.cli.config.ProfileConfig;
import cn.inkforge.cli.runtime.CliApplication;
import cn.inkforge.cli.runtime.CliDependencies;
import cn.inkforge.cli.transport.CoreApi;
import cn.inkforge.cli.transport.LoginResult;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

class VideoCommandsTest {

    private final JsonMapper json = JsonMapper.builder().build();

    @Test
    void 旧章节改编与后期命令全部退出普通CLI() {
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);
        List<String> retired = List.of(
                "long.video.adaptation.list",
                "long.video.adaptation.get",
                "long.video.adaptation.watch",
                "long.video.plan.confirm",
                "long.video.plan.discard",
                "long.video.episode.save",
                "long.video.prompt.save",
                "long.video.reference.save",
                "long.video.render.list",
                "long.video.render.start",
                "long.video.render.get",
                "long.video.render.retry",
                "long.video.render.watch",
                "long.video.take.confirm",
                "long.video.take.download",
                "long.video.post.show",
                "long.video.keyframe.set",
                "long.video.keyframe.clear",
                "long.video.keyframe.extract",
                "long.video.edit.save",
                "long.video.edit.get",
                "long.video.mix.save",
                "long.video.mix.get",
                "long.video.export.start",
                "long.video.export.get",
                "long.video.export.retry",
                "long.video.export.watch",
                "long.video.export.download");

        for (String command : retired) {
            Result result = run(application, command, "{}");
            assertThat(result.exit()).as(command).isEqualTo(2);
            assertThat(result.stdout()).as(command).contains("UNKNOWN_COMMAND");
        }
        assertThat(api.calls).isZero();
    }

    @Test
    void 共享ProjectAssetVisualCanon仍由普通CLI提供() {
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);

        assertThat(run(application, "long.video.project.get", "{\"projectId\":\"p /😀\"}").exit())
                .isZero();
        assertThat(api.lastPath).isEqualTo("/api/v1/video/projects/p%20%2F%F0%9F%98%80");
        assertThat(run(application, "long.video.canon.list", "{\"projectId\":\"p/1\"}").exit())
                .isZero();
        assertThat(api.lastPath).isEqualTo("/api/v1/video/projects/p%2F1/visual-canons");
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
        private int calls;
        private String lastPath;

        private RecordingApi(JsonMapper json) {
            this.json = json;
        }

        @Override
        public JsonNode request(String method, String path) {
            calls++;
            lastPath = path;
            return json.createObjectNode().put("id", "ok");
        }

        @Override
        public JsonNode request(String method, String path, JsonNode body) {
            return request(method, path);
        }

        @Override
        public cn.inkforge.cli.transport.FileDescriptor download(
                String method, String path, java.nio.file.Path target) {
            throw new UnsupportedOperationException();
        }

        @Override
        public LoginResult login(String username, String password) {
            throw new UnsupportedOperationException();
        }
    }
}
