package cn.inkforge.cli.commands;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.cli.config.MemoryConfigStore;
import cn.inkforge.cli.config.MemoryCredentialStore;
import cn.inkforge.cli.config.ProfileConfig;
import cn.inkforge.cli.runtime.CliApplication;
import cn.inkforge.cli.runtime.CliDependencies;
import cn.inkforge.cli.transport.AtomicFiles;
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

class VideoCommandsTest {

    private final JsonMapper json = JsonMapper.builder().build();

    @Test
    void 项目与素材七个命令保持严格公共路由和完整二进制(@TempDir Path directory) throws Exception {
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);
        runOk(application, "long.video.project.list", "{\"novelId\":\"n /?#\"}");
        assertThat(api.last().path()).isEqualTo("/api/v1/video/novels/n%20%2F%3F%23/projects");
        runOk(application, "long.video.project.get", "{\"projectId\":\"p /?#\"}");
        assertThat(api.last().path()).isEqualTo("/api/v1/video/projects/p%20%2F%3F%23");
        runOk(application, "long.video.project.create", "{\"novelId\":\"n1\",\"title\":\"第一章影视化\"}");
        assertThat(api.last().body().toString()).isEqualTo(
                "{\"title\":\"第一章影视化\",\"mode\":\"highlight\",\"targetAspectRatio\":\"16:9\",\"targetLanguage\":\"zh-CN\"}");

        Path source = directory.resolve("角色.png");
        byte[] original = new byte[] {(byte) 0x89, 0x50, 0x4e, 0x47, 0, (byte) 0xff};
        Files.write(source, original);
        runOk(application, "long.video.asset.upload",
                "{\"projectId\":\"p1\",\"filePath\":" + quote(source.toString())
                        + ",\"name\":\"角色身份图\",\"modality\":\"image\",\"duty\":\"identity\"}");
        assertThat(api.last().uploadBytes()).isEqualTo(original);
        assertThat(api.last().form()).containsEntry("sourceKind", "user_upload");
        runOk(application, "long.video.asset.rights", "{\"assetId\":\"a/1\",\"rightsStatus\":\"confirmed\"}");
        assertThat(api.last().path()).isEqualTo("/api/v1/video/assets/a%2F1/rights");

        Path downloaded = directory.resolve("下载.bin");
        runOk(application, "long.video.asset.download", "{\"assetId\":\"a/1\",\"outputFile\":" + quote(downloaded.toString()) + "}");
        assertThat(Files.readAllBytes(downloaded)).isEqualTo(api.binary);
        Path preview = directory.resolve("预览.bin");
        runOk(application, "long.video.asset.preview", "{\"assetId\":\"a/1\",\"outputFile\":" + quote(preview.toString()) + "}");
        assertThat(api.last().path()).isEqualTo("/api/v1/video/assets/a%2F1/preview");
        assertThat(Files.readAllBytes(preview)).isEqualTo(api.binary);
    }

    @Test
    void 章节改编九个非流式命令保持候选预检CAS和完整文件输入(@TempDir Path directory) throws Exception {
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);
        runOk(application, "long.video.adaptation.list", "{\"projectId\":\"p/1\"}");
        assertThat(api.last().path()).isEqualTo("/api/v1/video/projects/p%2F1/chapter-adaptations");
        runOk(application, "long.video.adaptation.get", "{\"adaptationId\":\"ad/1\"}");
        assertThat(api.last().path()).isEqualTo("/api/v1/video/chapter-adaptations/ad%2F1");
        runOk(application, "long.video.adaptation.create",
                "{\"projectId\":\"p1\",\"chapterId\":\"c1\",\"expectedChapterUpdatedAt\":\"v1\",\"clientRequestId\":\"video-adapt-00001\"}");
        assertThat(api.last().body().toString()).isEqualTo(
                "{\"clientRequestId\":\"video-adapt-00001\",\"chapterId\":\"c1\",\"expectedChapterUpdatedAt\":\"v1\"}");
        runOk(application, "long.video.plan.start",
                "{\"adaptationId\":\"ad1\",\"clientRequestId\":\"video-plan-start01\",\"pacingPreset\":\"cinematic\",\"targetEpisodeSeconds\":120,\"baseShotPlanVersionId\":\"pv1\",\"revisionBrief\":\"减少机械对白\"}");
        assertThat(api.last().body().get("targetEpisodeSeconds").intValue()).isEqualTo(120);

        Path plan = directory.resolve("plan.json");
        Files.writeString(plan, "{\"scenes\":[{\"sceneKey\":\"SC01\",\"尾部\":\"完整😀\"}]}", StandardCharsets.UTF_8);
        api.enqueue(candidate());
        api.enqueue(json.createObjectNode().put("state", "approved"));
        runOk(application, "long.video.plan.confirm",
                "{\"adaptationId\":\"ad/1\",\"clientRequestId\":\"video-plan-confirm1\",\"expectedArtifactRevision\":2,\"expectedAdaptationRevision\":3,\"planFile\":" + quote(plan.toString()) + "}");
        assertThat(api.calls.get(api.calls.size() - 2).method()).isEqualTo("GET");
        assertThat(api.last().body().at("/plan/scenes/0/尾部").textValue()).isEqualTo("完整😀");

        api.enqueue(candidate());
        api.enqueue(json.createObjectNode());
        runOk(application, "long.video.plan.discard",
                "{\"adaptationId\":\"ad1\",\"clientRequestId\":\"video-plan-discard1\",\"expectedArtifactRevision\":2,\"expectedAdaptationRevision\":3}");
        assertThat(api.last().path()).endsWith("/candidate/discard");
        runOk(application, "long.video.episode.save",
                "{\"adaptationId\":\"ad1\",\"clientRequestId\":\"video-episode-0001\",\"expectedAdaptationRevision\":4,\"shotPlanVersionId\":\"pv1\",\"breakAfterShotIds\":[\"s2\",\"s5\"]}");
        assertThat(api.last().body().get("breakAfterShotIds")).hasSize(2);
        runOk(application, "long.video.prompt.start",
                "{\"adaptationId\":\"ad1\",\"clientRequestId\":\"video-prompt-start1\",\"expectedAdaptationRevision\":4,\"shotPlanVersionId\":\"pv1\",\"shotIds\":[\"s1\"]}");
        Path prompt = directory.resolve("prompt.txt");
        Files.writeString(prompt, "第一行\r\n尾部😀", StandardCharsets.UTF_8);
        runOk(application, "long.video.prompt.save",
                "{\"adaptationId\":\"ad1\",\"shotId\":\"s/1\",\"expectedPromptRevision\":2,\"candidateTaskId\":null,\"currentPromptFile\":" + quote(prompt.toString()) + "}");
        assertThat(api.last().body().get("currentPrompt").textValue()).isEqualTo("第一行\r\n尾部😀");
    }

    @Test
    void 视觉一致性四个命令保持设定职责和逐镜版本强度() {
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);
        runOk(application, "long.video.canon.list", "{\"projectId\":\"p1\"}");
        runOk(application, "long.video.canon.candidate.set",
                "{\"projectId\":\"p1\",\"clientRequestId\":\"video-canon-set-01\",\"settingKind\":\"character\",\"settingId\":\"c1\",\"duty\":\"identity\",\"variantKey\":\"default\",\"label\":\"林默身份\",\"candidateAssetId\":\"a1\",\"includeFeatures\":[\"黑发\"],\"excludeFeatures\":[],\"defaultStrength\":72}");
        assertThat(api.last().body().get("defaultStrength").intValue()).isEqualTo(72);
        runOk(application, "long.video.canon.approve",
                "{\"canonId\":\"ca/1\",\"clientRequestId\":\"video-canon-ok-001\",\"expectedRevision\":2,\"candidateAssetId\":\"a1\"}");
        runOk(application, "long.video.reference.save",
                "{\"adaptationId\":\"ad1\",\"shotId\":\"s1\",\"expectedRevision\":0,\"references\":[{\"canonVersionId\":\"cv1\",\"strength\":72},{\"canonVersionId\":\"cv2\",\"strength\":65}]}");
        assertThat(api.last().body().get("references")).hasSize(2);

        int before = api.calls.size();
        Result duplicate = run(application, "long.video.reference.save",
                "{\"adaptationId\":\"ad1\",\"shotId\":\"s1\",\"expectedRevision\":0,\"references\":[{\"canonVersionId\":\"cv1\",\"strength\":72},{\"canonVersionId\":\"cv1\",\"strength\":65}]}");
        assertThat(duplicate.exit()).isEqualTo(2);
        assertThat(api.calls).hasSize(before);
    }

    @Test
    void 逐镜渲染六个非流式命令保持Seedance任务Take确认与下载(@TempDir Path directory) throws Exception {
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);
        runOk(application, "long.video.render.list", "{\"adaptationId\":\"ad/1\"}");
        runOk(application, "long.video.render.start",
                "{\"adaptationId\":\"ad/1\",\"shotId\":\"s/1\",\"clientRequestId\":\"video-render-00001\",\"expectedPromptRevision\":3,\"durationSeconds\":5,\"resolution\":\"1080p\",\"generateAudio\":false,\"watermark\":true}");
        assertThat(api.last().body().toString()).isEqualTo(
                "{\"clientRequestId\":\"video-render-00001\",\"expectedPromptRevision\":3,\"durationSeconds\":5,\"resolution\":\"1080p\",\"generateAudio\":false,\"watermark\":true}");
        runOk(application, "long.video.render.get", "{\"taskId\":\"t/1\"}");
        runOk(application, "long.video.render.retry", "{\"taskId\":\"t/1\",\"clientRequestId\":\"video-retry-000001\"}");
        runOk(application, "long.video.take.confirm",
                "{\"adaptationId\":\"ad/1\",\"shotId\":\"s/1\",\"takeId\":\"tk/1\",\"clientRequestId\":\"video-take-ok-0001\",\"expectedTakeRevision\":2}");
        assertThat(api.last().path()).endsWith("/takes/tk%2F1/confirm");
        Path take = directory.resolve("take.mp4");
        runOk(application, "long.video.take.download", "{\"takeId\":\"tk/1\",\"outputFile\":" + quote(take.toString()) + "}");
        assertThat(Files.readAllBytes(take)).isEqualTo(api.binary);
    }

    @Test
    void 后期十二个非流式命令保持关键帧粗剪混音导出版本链(@TempDir Path directory) throws Exception {
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);
        runOk(application, "long.video.post.show", "{\"adaptationId\":\"ad1\"}");
        runOk(application, "long.video.keyframe.set",
                "{\"adaptationId\":\"ad1\",\"shotId\":\"s1\",\"role\":\"initial_state\",\"assetId\":\"a1\",\"sourceTakeId\":\"tk1\",\"sourceTimeMs\":1200,\"clientRequestId\":\"video-keyframe-001\",\"expectedRevision\":1}");
        assertThat(api.last().body().get("sourceTimeMs").intValue()).isEqualTo(1200);
        runOk(application, "long.video.keyframe.clear",
                "{\"adaptationId\":\"ad1\",\"shotId\":\"s1\",\"role\":\"initial_state\",\"clientRequestId\":\"video-keyclear-0001\",\"expectedRevision\":2}");
        assertThat(api.last().body().get("assetId").isNull()).isTrue();
        runOk(application, "long.video.keyframe.extract",
                "{\"takeId\":\"tk/1\",\"clientRequestId\":\"video-extract-0001\",\"timestampMs\":1200,\"name\":\"第一镜首帧\"}");

        Path edit = directory.resolve("edit.json");
        Files.writeString(edit, "{\"clips\":[{\"shotId\":\"s1\",\"outputDurationMs\":1500}]}");
        runOk(application, "long.video.edit.save",
                "{\"adaptationId\":\"ad1\",\"episodeNo\":1,\"clientRequestId\":\"video-edit-save001\",\"expectedRevision\":1,\"basedOnVersionId\":null,\"editFile\":" + quote(edit.toString()) + "}");
        assertThat(api.last().body().get("clips")).hasSize(1);
        runOk(application, "long.video.edit.get", "{\"versionId\":\"ev/1\"}");

        Path mix = directory.resolve("mix.json");
        Files.writeString(mix, "{\"audioClips\":[],\"subtitleCues\":[{\"text\":\"完整对白\"}]}");
        runOk(application, "long.video.mix.save",
                "{\"adaptationId\":\"ad1\",\"episodeNo\":1,\"clientRequestId\":\"video-mix-save0001\",\"expectedRevision\":1,\"editVersionId\":\"ev1\",\"mixFile\":" + quote(mix.toString()) + "}");
        assertThat(api.last().body().at("/subtitleCues/0/text").textValue()).isEqualTo("完整对白");
        runOk(application, "long.video.mix.get", "{\"versionId\":\"mv/1\"}");
        runOk(application, "long.video.export.start",
                "{\"adaptationId\":\"ad/1\",\"episodeNo\":2,\"editVersionId\":\"ev1\",\"mixVersionId\":\"mv1\",\"clientRequestId\":\"video-export-0001\",\"resolution\":\"1080p\",\"framesPerSecond\":25,\"burnSubtitles\":false}");
        assertThat(api.last().body().get("framesPerSecond").intValue()).isEqualTo(25);
        runOk(application, "long.video.export.get", "{\"taskId\":\"et/1\"}");
        runOk(application, "long.video.export.retry", "{\"taskId\":\"et/1\",\"clientRequestId\":\"video-export-retry1\"}");
        Path exported = directory.resolve("episode.mp4");
        runOk(application, "long.video.export.download", "{\"exportId\":\"ex/1\",\"outputFile\":" + quote(exported.toString()) + "}");
        assertThat(Files.readAllBytes(exported)).isEqualTo(api.binary);
    }

    @Test
    void 视频严格字段枚举和候选revision冲突均在写请求前拒绝() {
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);
        Result unknown = run(application, "long.video.project.get", "{\"projectId\":\"p1\",\"unknown\":true}");
        assertThat(unknown.exit()).isEqualTo(2);
        assertThat(api.calls).isEmpty();

        api.enqueue(json.readTree("{\"headRevision\":4,\"candidatePlan\":{},\"reviewArtifact\":{\"status\":\"awaiting_user\",\"revision\":2}}"));
        int before = api.calls.size();
        Result conflict = run(application, "long.video.plan.confirm",
                "{\"adaptationId\":\"ad1\",\"clientRequestId\":\"video-plan-confirm1\",\"expectedArtifactRevision\":2,\"expectedAdaptationRevision\":3,\"plan\":{\"scenes\":[]}}");
        assertThat(conflict.exit()).isEqualTo(4);
        assertThat(api.calls).hasSize(before + 1);
    }

    private ObjectNodeCandidate candidate() {
        return new ObjectNodeCandidate(json.readTree(
                "{\"headRevision\":3,\"candidatePlan\":{\"scenes\":[]},\"reviewArtifact\":{\"status\":\"awaiting_user\",\"revision\":2}}"));
    }

    private String quote(String value) {
        return json.writeValueAsString(value);
    }

    private void runOk(CliApplication application, String command, String payload) {
        Result result = run(application, command, payload);
        assertThat(result.exit()).as(command + " " + result.stdout()).isZero();
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
            JsonNode body,
            Map<String, String> form,
            byte[] uploadBytes) {}

    /** 用包装类型避免测试队列把候选对象误当作普通默认值。 */
    private record ObjectNodeCandidate(JsonNode value) {}

    private static final class RecordingApi implements CoreApi {
        private final JsonMapper json;
        private final Deque<Object> responses = new ArrayDeque<>();
        private final List<Call> calls = new ArrayList<>();
        private final byte[] binary = "完整视频😀".getBytes(StandardCharsets.UTF_8);

        private RecordingApi(JsonMapper json) {
            this.json = json;
        }

        private void enqueue(Object value) {
            responses.addLast(value);
        }

        private Call last() {
            return calls.getLast();
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
            calls.add(new Call(method, path, new LinkedHashMap<>(query), body, Map.of(), null));
            if (responses.isEmpty()) return json.createObjectNode().put("id", "ok");
            Object next = responses.removeFirst();
            return next instanceof ObjectNodeCandidate candidate
                    ? candidate.value()
                    : (JsonNode) next;
        }

        @Override
        public JsonNode upload(String path, Path file, String mediaType, Map<String, String> fields)
                throws java.io.IOException {
            byte[] bytes = Files.readAllBytes(file);
            calls.add(new Call("POST", path, Map.of(), null, new LinkedHashMap<>(fields), bytes));
            return json.createObjectNode().put("id", "asset-1");
        }

        @Override
        public FileDescriptor download(String method, String path, Path target)
                throws java.io.IOException {
            calls.add(new Call(method, path, Map.of(), null, Map.of(), null));
            return AtomicFiles.write(
                    target,
                    new ByteArrayInputStream(binary),
                    "video/mp4");
        }

        @Override
        public LoginResult login(String username, String password) {
            throw new UnsupportedOperationException();
        }
    }
}
