package cn.inkforge.cli.commands;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.cli.config.MemoryConfigStore;
import cn.inkforge.cli.config.MemoryCredentialStore;
import cn.inkforge.cli.config.ProfileConfig;
import cn.inkforge.cli.runtime.CliApplication;
import cn.inkforge.cli.runtime.CliDependencies;
import cn.inkforge.cli.transport.CoreApi;
import cn.inkforge.cli.transport.CoreSseConnectionException;
import cn.inkforge.cli.transport.CoreTransportException;
import cn.inkforge.cli.transport.FileDescriptor;
import cn.inkforge.cli.transport.LoginResult;
import cn.inkforge.cli.transport.SseStream;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.NoSuchElementException;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

class WatchCommandsTest {

    private final JsonMapper json = JsonMapper.builder().build();

    @Test
    void 短篇Agent观察在SSE断线后携带游标重连并读取终态() {
        WatchApi api = new WatchApi(json);
        api.stream(
                json.readTree("{\"id\":\"e1\",\"event\":\"progress\",\"data\":{\"step\":1}}"),
                new CoreSseConnectionException());
        api.stream(json.readTree("{\"id\":\"e2\",\"event\":\"done\",\"data\":{\"step\":2}}"));
        api.response(json.readTree("{\"taskId\":\"t/1\",\"phase\":\"completed\",\"commandStatus\":\"succeeded\"}"));
        Invocation result = invoke("short.agent.watch", "{\"taskId\":\"t/1\"}", api, new FakeClock());
        assertThat(result.exit()).isZero();
        assertThat(result.frames()).extracting(frame -> frame.get("type").textValue())
                .containsExactly("event", "event", "terminal");
        assertThat(api.sseCursors).containsExactly(null, "e1");
    }

    @Test
    void 长篇任务观察先读权威outcome再接SSE并返回等待复审Artifact() {
        WatchApi api = new WatchApi(json);
        api.response(status("running", null));
        api.stream(
                json.readTree("{\"id\":\"e1\",\"event\":\"progress\",\"data\":{\"step\":1}}"),
                new CoreSseConnectionException());
        api.response(status("waiting_user", "artifact-1"));
        FakeClock clock = new FakeClock();
        Invocation result = invoke("long.task.watch", "{\"taskId\":\"t/1\"}", api, clock);
        assertThat(result.exit()).isZero();
        assertThat(result.frames()).extracting(frame -> frame.get("type").textValue())
                .containsExactly("snapshot", "event", "waiting_user");
        assertThat(result.frames().getLast().get("artifactId").textValue())
                .isEqualTo("artifact-1");
        assertThat(clock.sleeps).isEmpty();
    }

    @Test
    void 改编观察仅在签名变化时输出进度并由任务状态决定退出码() {
        WatchApi api = new WatchApi(json);
        api.response(adaptation("pending", "none", "v1", "task-1"));
        api.response(adaptation("processing", "dramatic", "v2", "task-1"));
        api.response(adaptation("completed", "completed", "v3", "task-1"));
        FakeClock clock = new FakeClock();
        Invocation result = invoke(
                "long.video.adaptation.watch",
                "{\"adaptationId\":\"ad1\",\"taskId\":\"task-1\"}",
                api,
                clock);
        assertThat(result.exit()).isZero();
        assertThat(result.frames()).extracting(frame -> frame.get("type").textValue())
                .containsExactly("snapshot", "progress", "progress", "terminal");
        assertThat(clock.sleeps).containsExactly(0.5, 1.0);
    }

    @Test
    void 渲染与导出观察输出快照进度终态并保留失败退出码() {
        WatchApi renderApi = new WatchApi(json);
        renderApi.response(json.readTree("{\"id\":\"r1\",\"status\":\"queued\",\"pollCount\":0,\"updatedAt\":\"v1\"}"));
        renderApi.response(json.readTree("{\"id\":\"r1\",\"status\":\"succeeded\",\"pollCount\":1,\"updatedAt\":\"v2\"}"));
        Invocation render = invoke(
                "long.video.render.watch", "{\"taskId\":\"r1\"}", renderApi, new FakeClock());
        assertThat(render.exit()).isZero();
        assertThat(render.frames()).extracting(frame -> frame.get("type").textValue())
                .containsExactly("snapshot", "progress", "terminal");

        WatchApi exportApi = new WatchApi(json);
        exportApi.response(json.readTree("{\"id\":\"e1\",\"status\":\"pending\",\"attemptCount\":0,\"updatedAt\":\"v1\"}"));
        exportApi.response(json.readTree("{\"id\":\"e1\",\"status\":\"failed\",\"attemptCount\":1,\"updatedAt\":\"v2\"}"));
        Invocation export = invoke(
                "long.video.export.watch", "{\"taskId\":\"e1\"}", exportApi, new FakeClock());
        assertThat(export.exit()).isEqualTo(5);
        assertThat(export.frames()).extracting(frame -> frame.get("type").textValue())
                .containsExactly("snapshot", "progress", "terminal");
    }

    @Test
    void 连续不可达超过三百秒只停止观察不取消服务端任务() {
        WatchApi api = new WatchApi(json);
        api.repeatFailure = new CoreTransportException();
        FakeClock clock = new FakeClock();
        Invocation result = invoke(
                "long.video.render.watch", "{\"taskId\":\"r1\"}", api, clock);
        assertThat(result.exit()).isEqualTo(5);
        assertThat(result.frames().getLast().at("/error/code").textValue())
                .isEqualTo("WATCH_CORE_UNREACHABLE");
        assertThat(clock.now).isGreaterThan(300.0);
        assertThat(clock.sleeps).allMatch(value -> value <= 10.0);
    }

    private JsonNode status(String state, String artifactId) {
        String result = artifactId == null
                ? "{\"kind\":\"none\",\"ready\":false,\"id\":null}"
                : "{\"kind\":\"review_artifact\",\"ready\":true,\"id\":\"" + artifactId + "\"}";
        return json.readTree("{\"taskId\":\"t/1\",\"outcome\":{\"state\":\"" + state + "\",\"result\":" + result + "}}");
    }

    private JsonNode adaptation(String status, String checkpoint, String updated, String taskId) {
        return json.readTree("{\"id\":\"ad1\",\"latestTask\":{\"id\":\"" + taskId + "\",\"status\":\"" + status
                + "\",\"checkpointStage\":\"" + checkpoint + "\",\"updatedAt\":\"" + updated
                + "\",\"lastErrorCode\":null,\"lastErrorMessage\":null}}");
    }

    private Invocation invoke(String command, String payload, WatchApi api, FakeClock clock) {
        MemoryConfigStore configs = new MemoryConfigStore();
        MemoryCredentialStore credentials = new MemoryCredentialStore();
        configs.save("default", new ProfileConfig("http://127.0.0.1:8000", "nie"));
        credentials.set("default", "http://127.0.0.1:8000", "token");
        CliDependencies dependencies = new CliDependencies(
                (origin, token) -> api,
                configs,
                credentials,
                prompt -> new char[0],
                () -> false,
                json,
                clock::now,
                clock::sleep);
        CliApplication application = CliApplication.createDefault(dependencies);
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        int exit = application.run(
                List.of(command),
                new ByteArrayInputStream(payload.getBytes(StandardCharsets.UTF_8)),
                output,
                new ByteArrayOutputStream());
        List<JsonNode> frames = output.toString(StandardCharsets.UTF_8).lines()
                .map(json::readTree)
                .toList();
        return new Invocation(exit, frames);
    }

    private record Invocation(int exit, List<JsonNode> frames) {}

    private static final class FakeClock {
        private double now;
        private final List<Double> sleeps = new ArrayList<>();
        private double now() { return now; }
        private void sleep(double seconds) {
            sleeps.add(seconds);
            now += seconds;
        }
    }

    private static final class WatchApi implements CoreApi {
        private final JsonMapper json;
        private final Deque<Object> responses = new ArrayDeque<>();
        private final Deque<List<Object>> streams = new ArrayDeque<>();
        private final List<String> sseCursors = new ArrayList<>();
        private RuntimeException repeatFailure;

        private WatchApi(JsonMapper json) { this.json = json; }
        private void response(Object value) { responses.addLast(value); }
        private void stream(Object... values) { streams.addLast(List.of(values)); }

        @Override public JsonNode request(String method, String path) {
            Object value = responses.isEmpty() ? repeatFailure : responses.removeFirst();
            if (value instanceof RuntimeException error) throw error;
            if (value == null) throw new AssertionError("测试没有配置状态响应");
            return (JsonNode) value;
        }
        @Override public JsonNode request(String method, String path, JsonNode body) {
            return request(method, path);
        }
        @Override public SseStream openSse(String taskId, String lastEventId) {
            sseCursors.add(lastEventId);
            if (streams.isEmpty()) throw new AssertionError("测试没有配置 SSE");
            return new TestSseStream(streams.removeFirst());
        }
        @Override public LoginResult login(String username, String password) {
            throw new UnsupportedOperationException();
        }
        @Override public FileDescriptor download(String method, String path, Path target) {
            throw new UnsupportedOperationException();
        }
    }

    private static final class TestSseStream implements SseStream {
        private final List<Object> values;
        private int index;
        private TestSseStream(List<Object> values) { this.values = values; }
        @Override public boolean hasNext() {
            if (index >= values.size()) return false;
            Object value = values.get(index);
            if (value instanceof RuntimeException error) {
                index++;
                throw error;
            }
            return true;
        }
        @Override public JsonNode next() {
            if (!hasNext()) throw new NoSuchElementException();
            return (JsonNode) values.get(index++);
        }
        @Override public void close() {}
    }
}
