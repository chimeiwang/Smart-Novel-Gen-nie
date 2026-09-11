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
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

class VideoEpisodeCommandsTest {

    private final JsonMapper json = JsonMapper.builder().build();

    @Test
    void 二十个独立分集命令映射严格公共路由和完整CAS请求() {
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);

        runOk(application, "long.video.episode.list", "{\"projectId\":\"project /😀\"}");
        assertThat(api.last().path())
                .isEqualTo("/api/v1/video/projects/project%20%2F%F0%9F%98%80/episodes");
        runOk(application, "long.video.episode.get", "{\"episodeId\":\"episode/1\"}");
        runOk(application, "long.video.episode.create",
                "{\"projectId\":\"project/1\",\"clientRequestId\":\"episode-create-0001\",\"title\":\"  第一集😀  \",\"creativeIntent\":\"保留换行\\r\\n与空白  \",\"targetDurationSeconds\":90}");
        assertThat(api.last().body().get("title").textValue()).isEqualTo("  第一集😀  ");
        runOk(application, "long.video.episode.update",
                "{\"episodeId\":\"episode/1\",\"clientRequestId\":\"episode-update-0001\",\"expectedRevision\":2,\"title\":\"第二版\",\"creativeIntent\":null,\"targetDurationSeconds\":null}");
        assertThat(api.last().body().get("creativeIntent").isNull()).isTrue();
        runOk(application, "long.video.episode.reorder",
                "{\"projectId\":\"project/1\",\"clientRequestId\":\"episode-reorder-001\",\"expectedProjectRevision\":3,\"episodeIds\":[\"episode/2\",\"episode/1\"]}");

        runOk(application, "long.video.episode.source.create",
                "{\"episodeId\":\"episode/1\",\"clientRequestId\":\"source-create-00001\",\"expectedRevision\":3,\"basedOnVersionId\":null,\"sources\":[{\"chapterId\":\"chapter/1\",\"expectedUpdatedAt\":\"2026-09-10T00:00:00Z\",\"sourceHash\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"ranges\":[{\"start\":0,\"end\":12}]}]}");
        runOk(application, "long.video.episode.source.list", "{\"episodeId\":\"episode/1\"}");
        runOk(application, "long.video.episode.source.get",
                "{\"episodeId\":\"episode/1\",\"versionId\":\"source/1\"}");

        runOk(application, "long.video.episode.script.draft.get", "{\"episodeId\":\"episode/1\"}");
        runOk(application, "long.video.episode.script.draft.save",
                "{\"episodeId\":\"episode/1\",\"clientRequestId\":\"script-draft-save1\",\"expectedRevision\":4,\"sourceSetVersionId\":\"source/1\",\"baseScriptVersionId\":null,\"document\":{\"schemaVersion\":\"video-episode-script/1.0\",\"overview\":{\"summary\":\"完整😀\",\"creativeIntent\":\"\",\"targetDurationSeconds\":90},\"scenes\":[],\"endingStates\":[],\"dependencies\":[]}}");
        assertThat(api.last().body().at("/document/overview/summary").textValue())
                .isEqualTo("完整😀");
        runOk(application, "long.video.episode.script.run.start",
                "{\"episodeId\":\"episode/1\",\"clientRequestId\":\"script-run-start-01\",\"expectedDraftRevision\":5,\"operation\":\"episode_script_revise\",\"selectedSceneIds\":[\"scene/1\"],\"instruction\":\"减少对白😀\"}");
        runOk(application, "long.video.episode.script.run.get",
                "{\"episodeId\":\"episode/1\",\"runId\":\"run/1\"}");
        runOk(application, "long.video.episode.script.candidate.adopt",
                "{\"episodeId\":\"episode/1\",\"artifactId\":\"artifact/1\",\"clientRequestId\":\"candidate-adopt-001\",\"expectedArtifactRevision\":2,\"expectedDraftRevision\":5}");
        runOk(application, "long.video.episode.script.confirmation.prepare",
                "{\"episodeId\":\"episode/1\",\"clientRequestId\":\"confirm-prepare-001\",\"expectedDraftRevision\":6,\"expectedEpisodeRevision\":4}");
        runOk(application, "long.video.episode.script.confirmation.get",
                "{\"episodeId\":\"episode/1\",\"artifactId\":\"artifact/2\"}");
        runOk(application, "long.video.episode.script.confirmation.approve",
                "{\"episodeId\":\"episode/1\",\"artifactId\":\"artifact/2\",\"clientRequestId\":\"confirm-approve-001\",\"expectedArtifactRevision\":1,\"expectedDraftRevision\":6,\"expectedEpisodeRevision\":4,\"confirmationHash\":\"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\"}");
        runOk(application, "long.video.episode.script.version.list", "{\"episodeId\":\"episode/1\"}");
        runOk(application, "long.video.episode.script.version.get",
                "{\"episodeId\":\"episode/1\",\"versionId\":\"script/1\"}");
        runOk(application, "long.video.episode.command.get",
                "{\"episodeId\":\"episode/1\",\"clientRequestId\":\"episode-command-0001\"}");
        assertThat(api.last().path())
                .isEqualTo("/api/v1/video/episodes/episode%2F1/commands/episode-command-0001");
        runOk(application, "long.video.episode.project-command.get",
                "{\"projectId\":\"project/1\",\"clientRequestId\":\"episode-create-0001\"}");
        assertThat(api.last().path())
                .isEqualTo("/api/v1/video/projects/project%2F1/episode-commands/episode-create-0001");
    }

    @Test
    void 来源集和剧本工作稿从UTF8文件完整读取(@TempDir Path directory) throws Exception {
        Path sources = directory.resolve("sources.json");
        Files.writeString(
                sources,
                "[{\"chapterId\":\"章节😀\",\"expectedUpdatedAt\":\"v1\",\"sourceHash\":\"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc\",\"ranges\":[{\"start\":1,\"end\":9}]}]",
                StandardCharsets.UTF_8);
        Path document = directory.resolve("script.json");
        Files.writeString(
                document,
                "{\"schemaVersion\":\"video-episode-script/1.0\",\"overview\":{\"summary\":\"  完整😀\\r\\n尾行  \",\"creativeIntent\":\"\",\"targetDurationSeconds\":90},\"scenes\":[],\"endingStates\":[],\"dependencies\":[]}",
                StandardCharsets.UTF_8);
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);

        runOk(application, "long.video.episode.source.create",
                "{\"episodeId\":\"episode-1\",\"clientRequestId\":\"source-file-save-01\",\"expectedRevision\":1,\"sourcesFile\":"
                        + json.writeValueAsString(sources.toString()) + "}");
        runOk(application, "long.video.episode.script.draft.save",
                "{\"episodeId\":\"episode-1\",\"clientRequestId\":\"script-file-save-01\",\"expectedRevision\":1,\"sourceSetVersionId\":\"source-1\",\"baseScriptVersionId\":null,\"documentFile\":"
                        + json.writeValueAsString(document.toString()) + "}");

        assertThat(api.calls.get(0).body().at("/sources/0/chapterId").textValue())
                .isEqualTo("章节😀");
        assertThat(api.calls.get(1).body().at("/document/overview/summary").textValue())
                .isEqualTo("  完整😀\r\n尾行  ");
    }

    @Test
    void 未知字段和非法修订范围在网络请求前拒绝() {
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);

        Result unknown = run(application, "long.video.episode.get",
                "{\"episodeId\":\"episode-1\",\"unknown\":true}");
        assertThat(unknown.exit()).isEqualTo(2);
        Result invalidScope = run(application, "long.video.episode.script.run.start",
                "{\"episodeId\":\"episode-1\",\"clientRequestId\":\"script-run-start-01\",\"expectedDraftRevision\":1,\"operation\":\"episode_script_revise\",\"instruction\":\"修订\"}");
        assertThat(invalidScope.exit()).isEqualTo(2);
        assertThat(api.calls).isEmpty();
    }

    @Test
    void 响应未知后只用同一请求号查询项目级回执() {
        RecordingApi api = new RecordingApi(json);
        api.enqueue(new CoreTransportException());
        api.enqueue(json.createObjectNode().put("operation", "episode_create"));
        CliApplication application = application(api);

        Result unknown = run(application, "long.video.episode.create",
                "{\"projectId\":\"project-1\",\"clientRequestId\":\"episode-create-0001\",\"title\":\"第一集\"}");
        assertThat(unknown.exit()).isEqualTo(5);
        runOk(application, "long.video.episode.project-command.get",
                "{\"projectId\":\"project-1\",\"clientRequestId\":\"episode-create-0001\"}");

        assertThat(api.calls).hasSize(2);
        assertThat(api.calls.get(0).method()).isEqualTo("POST");
        assertThat(api.calls.get(1).method()).isEqualTo("GET");
    }

    @Test
    void 三个旧启动命令已从普通CLI退出() {
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);

        for (String command : List.of(
                "long.video.adaptation.create",
                "long.video.plan.start",
                "long.video.prompt.start")) {
            Result result = run(application, command, "{}");
            assertThat(result.exit()).as(command).isEqualTo(2);
            assertThat(result.stdout()).as(command).contains("UNKNOWN_COMMAND");
        }
        assertThat(api.calls).isEmpty();
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

    private void runOk(CliApplication application, String command, String payload) {
        Result result = run(application, command, payload);
        assertThat(result.exit()).as(command + " " + result.stdout()).isZero();
    }

    private Result run(CliApplication application, String command, String payload) {
        ByteArrayOutputStream stdout = new ByteArrayOutputStream();
        int exit = application.run(
                List.of(command),
                new ByteArrayInputStream(payload.getBytes(StandardCharsets.UTF_8)),
                stdout,
                new ByteArrayOutputStream());
        return new Result(exit, stdout.toString(StandardCharsets.UTF_8));
    }

    private record Result(int exit, String stdout) {}

    private record Call(String method, String path, JsonNode body) {}

    private static final class RecordingApi implements CoreApi {
        private final JsonMapper json;
        private final Deque<Object> responses = new ArrayDeque<>();
        private final List<Call> calls = new ArrayList<>();

        private RecordingApi(JsonMapper json) {
            this.json = json;
        }

        private void enqueue(Object response) {
            responses.addLast(response);
        }

        private Call last() {
            return calls.getLast();
        }

        @Override
        public JsonNode request(String method, String path) {
            return request(method, path, null);
        }

        @Override
        public JsonNode request(String method, String path, JsonNode body) {
            calls.add(new Call(method, path, body));
            if (responses.isEmpty()) return json.createObjectNode().put("id", "ok");
            Object next = responses.removeFirst();
            if (next instanceof RuntimeException exception) throw exception;
            return (JsonNode) next;
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
