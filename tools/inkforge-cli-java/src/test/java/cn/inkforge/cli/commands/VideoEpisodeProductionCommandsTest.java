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

class VideoEpisodeProductionCommandsTest {

    private final JsonMapper json = JsonMapper.builder().build();

    @Test
    void P2查询严格编码剧集基线路径和有界游标() {
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);

        runOk(application, "long.video.episode.storyboard.run.list",
                "{\"episodeId\":\"ep /😀\",\"limit\":50,\"beforeRunId\":\"run /😀\"}");
        assertThat(api.last().path()).isEqualTo(
                "/api/v1/video/episodes/ep%20%2F%F0%9F%98%80/storyboard/runs?limit=50&beforeRunId=run%20%2F%F0%9F%98%80");
        runOk(application, "long.video.episode.take.list",
                "{\"episodeId\":\"ep/1\",\"targetShotVersionId\":\"shot /😀\",\"limit\":7,\"beforeTakeId\":\"take /😀\"}");
        assertThat(api.last().path()).isEqualTo(
                "/api/v1/video/episodes/ep%2F1/takes?targetShotVersionId=shot%20%2F%F0%9F%98%80&limit=7&beforeTakeId=take%20%2F%F0%9F%98%80");
        runOk(application, "long.video.episode.impact.list",
                "{\"episodeId\":\"ep/1\",\"status\":\"pending\",\"limit\":8,\"beforeReviewId\":\"review /😀\"}");
        assertThat(api.last().path()).endsWith(
                "/impact-reviews?status=pending&limit=8&beforeReviewId=review%20%2F%F0%9F%98%80");
        runOk(application, "long.video.episode.edit.get",
                "{\"episodeId\":\"ep/1\",\"baselineId\":\"base/1\",\"versionId\":\"edit/1\"}");
        assertThat(api.last().path()).endsWith(
                "/production-baselines/base%2F1/edit-versions/edit%2F1");
    }

    @Test
    void 分镜采用基线与影响决定保持完整CAS和请求号(@TempDir Path directory) throws Exception {
        Path document = directory.resolve("storyboard.json");
        Files.writeString(document, "{\"schemaVersion\":\"video-episode-storyboard/1.0\",\"shots\":[]}");
        Path decisions = directory.resolve("decisions.json");
        Files.writeString(decisions, "[{\"itemId\":\"item/1\",\"action\":\"revise_target\",\"note\":\"下一版修订\"}]");
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);

        runOk(application, "long.video.episode.storyboard.draft.save",
                "{\"episodeId\":\"ep/1\",\"clientRequestId\":\"storyboard-save-0001\",\"expectedRevision\":2,\"scriptVersionId\":\"script/1\",\"baseStoryboardVersionId\":null,\"documentFile\":" + quote(document.toString()) + "}");
        assertThat(api.last().body().at("/document/schemaVersion").textValue())
                .isEqualTo("video-episode-storyboard/1.0");
        runOk(application, "long.video.episode.adoption.create",
                "{\"episodeId\":\"ep/1\",\"clientRequestId\":\"adoption-create-001\",\"expectedProductionRevision\":3,\"targetShotVersionId\":\"shotv/1\",\"sourceTakeId\":\"take/1\",\"sourceBaselineId\":\"base/0\",\"comparison\":{\"sourceBaselineId\":\"base/0\",\"targetShotVersionId\":\"shotv/1\",\"directInputsUnchanged\":false,\"referenceHashesChecked\":[\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\"],\"summary\":\"人工核对通过\"}}");
        assertThat(api.last().body().at("/comparison/sourceBaselineId").textValue())
                .isEqualTo("base/0");
        runOk(application, "long.video.episode.baseline.create",
                "{\"episodeId\":\"ep/1\",\"clientRequestId\":\"baseline-create-001\",\"expectedEpisodeRevision\":5,\"expectedProductionRevision\":3,\"basedOnBaselineId\":\"base/0\",\"scriptVersionId\":\"script/1\",\"storyboardVersionId\":\"board/1\",\"shotAdoptions\":[{\"shotVersionId\":\"shotv/1\",\"adoptionId\":\"adopt/1\"}],\"keyframes\":[{\"shotVersionId\":\"shotv/1\",\"role\":\"initial_state\",\"assetId\":\"keyframe/1\"}]}");
        assertThat(api.last().body().at("/shotAdoptions/0/adoptionId").textValue())
                .isEqualTo("adopt/1");
        assertThat(api.last().body().at("/keyframes/0/role").textValue())
                .isEqualTo("initial_state");
        int callsBeforeDuplicate = api.calls.size();
        Result duplicateKeyframe = run(application, "long.video.episode.baseline.create",
                "{\"episodeId\":\"ep/1\",\"clientRequestId\":\"baseline-invalid-01\",\"expectedEpisodeRevision\":5,\"expectedProductionRevision\":3,\"basedOnBaselineId\":null,\"scriptVersionId\":\"script/1\",\"storyboardVersionId\":\"board/1\",\"keyframes\":[{\"shotVersionId\":\"shotv/1\",\"role\":\"initial_state\",\"assetId\":\"keyframe/1\"},{\"shotVersionId\":\"shotv/1\",\"role\":\"initial_state\",\"assetId\":\"keyframe/2\"}]}");
        assertThat(duplicateKeyframe.exit()).isEqualTo(2);
        assertThat(api.calls).hasSize(callsBeforeDuplicate);
        runOk(application, "long.video.episode.impact.decide",
                "{\"episodeId\":\"ep/1\",\"reviewId\":\"review/1\",\"clientRequestId\":\"impact-decide-0001\",\"expectedRevision\":1,\"decisionsFile\":" + quote(decisions.toString()) + "}");
        assertThat(api.last().path()).endsWith("/impact-reviews/review%2F1/decisions");
        assertThat(api.last().body().at("/decisions/0/note").textValue()).isEqualTo("下一版修订");
    }

    @Test
    void 渲染粗剪混音导出与交付只使用EpisodeBaseline根(@TempDir Path directory) throws Exception {
        Path edit = directory.resolve("edit.json");
        Files.writeString(edit,
                "{\"clips\":[{\"tempKey\":\"clip-1\",\"adoptionId\":\"adopt/1\",\"takeId\":\"take/1\",\"sourceInMs\":0,\"sourceOutMs\":1000,\"sourceAudioMode\":\"keep\"}],\"omissions\":[]}");
        Path mix = directory.resolve("mix.json");
        Files.writeString(mix, "{\"audioClips\":[],\"subtitleCues\":[]}");
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);
        String root = "/api/v1/video/episodes/ep%2F1/production-baselines/base%2F1";

        runOk(application, "long.video.episode.render.start",
                "{\"episodeId\":\"ep/1\",\"baselineId\":\"base/1\",\"shotId\":\"shot/1\",\"clientRequestId\":\"render-start-0001\",\"feeConfirmed\":false}");
        assertThat(api.last().path()).isEqualTo(root + "/shots/shot%2F1/render-tasks");
        runOk(application, "long.video.episode.edit.create",
                "{\"episodeId\":\"ep/1\",\"baselineId\":\"base/1\",\"clientRequestId\":\"edit-create-00001\",\"expectedHeadRevision\":1,\"basedOnVersionId\":null,\"editFile\":" + quote(edit.toString()) + "}");
        assertThat(api.last().path()).isEqualTo(root + "/edit-versions");
        assertThat(api.last().body().at("/clips/0/adoptionId").textValue()).isEqualTo("adopt/1");
        runOk(application, "long.video.episode.mix.create",
                "{\"episodeId\":\"ep/1\",\"baselineId\":\"base/1\",\"clientRequestId\":\"mix-create-000001\",\"expectedHeadRevision\":1,\"basedOnVersionId\":null,\"editVersionId\":\"edit/1\",\"mixFile\":" + quote(mix.toString()) + "}");
        assertThat(api.last().path()).isEqualTo(root + "/mix-versions");
        runOk(application, "long.video.episode.export.start",
                "{\"episodeId\":\"ep/1\",\"baselineId\":\"base/1\",\"clientRequestId\":\"export-start-0001\",\"editVersionId\":\"edit/1\",\"mixVersionId\":\"mix/1\",\"resolution\":\"1080p\",\"framesPerSecond\":25,\"burnSubtitles\":false}");
        assertThat(api.last().path()).isEqualTo(root + "/export-tasks");
        assertThat(api.last().body().get("framesPerSecond").intValue()).isEqualTo(25);
        runOk(application, "long.video.episode.export.retry",
                "{\"episodeId\":\"ep/1\",\"baselineId\":\"base/1\",\"taskId\":\"task/1\",\"clientRequestId\":\"export-retry-0001\"}");
        assertThat(api.last().path()).isEqualTo(root + "/export-tasks/task%2F1/retry");

        Path take = directory.resolve("take.mp4");
        runOk(application, "long.video.episode.take.download",
                "{\"episodeId\":\"ep/1\",\"takeId\":\"take/1\",\"outputFile\":" + quote(take.toString()) + "}");
        assertThat(Files.readAllBytes(take)).isEqualTo(api.binary);
        assertThat(api.last().path()).endsWith("/episodes/ep%2F1/takes/take%2F1/content");
        Path delivery = directory.resolve("delivery.mp4");
        runOk(application, "long.video.episode.delivery.download",
                "{\"episodeId\":\"ep/1\",\"baselineId\":\"base/1\",\"exportId\":\"export/1\",\"outputFile\":" + quote(delivery.toString()) + "}");
        assertThat(Files.readAllBytes(delivery)).isEqualTo(api.binary);
        assertThat(api.last().path()).isEqualTo(root + "/exports/export%2F1/content");
    }

    @Test
    void 响应未知后只用同一请求号读取Episode命令回执() {
        RecordingApi api = new RecordingApi(json);
        api.enqueue(new CoreTransportException());
        api.enqueue(json.createObjectNode().put("operation", "episode.export-task.start"));
        CliApplication application = application(api);

        Result unknown = run(application, "long.video.episode.export.start",
                "{\"episodeId\":\"ep-1\",\"baselineId\":\"base-1\",\"clientRequestId\":\"export-unknown-001\",\"editVersionId\":\"edit-1\",\"mixVersionId\":\"mix-1\"}");
        assertThat(unknown.exit()).isEqualTo(5);
        runOk(application, "long.video.episode.command.get",
                "{\"episodeId\":\"ep-1\",\"clientRequestId\":\"export-unknown-001\"}");
        assertThat(api.calls).hasSize(2);
        assertThat(api.last().path()).isEqualTo(
                "/api/v1/video/episodes/ep-1/commands/export-unknown-001");
    }

    private String quote(String value) {
        return json.writeValueAsString(value);
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

    private void runOk(CliApplication application, String command, String input) {
        Result result = run(application, command, input);
        assertThat(result.exit()).as(command + " " + result.stdout()).isZero();
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
        private final Deque<Object> responses = new ArrayDeque<>();
        private final List<Call> calls = new ArrayList<>();
        private final byte[] binary = "完整视频😀".getBytes(StandardCharsets.UTF_8);

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
        public FileDescriptor download(String method, String path, Path target)
                throws java.io.IOException {
            calls.add(new Call(method, path, null));
            Files.write(target, binary);
            return new FileDescriptor(
                    target.toAbsolutePath().normalize().toString(),
                    binary.length,
                    "a".repeat(64),
                    "video/mp4");
        }

        @Override
        public LoginResult login(String username, String password) {
            throw new UnsupportedOperationException();
        }
    }
}
