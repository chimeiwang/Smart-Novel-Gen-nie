package cn.inkforge.cli.runtime;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.cli.config.MemoryConfigStore;
import cn.inkforge.cli.config.MemoryCredentialStore;
import cn.inkforge.cli.config.ProfileConfig;
import cn.inkforge.cli.registry.CommandCatalog;
import cn.inkforge.cli.transport.AtomicFiles;
import cn.inkforge.cli.transport.CoreApi;
import cn.inkforge.cli.transport.CoreApiException;
import cn.inkforge.cli.transport.FileDescriptor;
import cn.inkforge.cli.transport.LoginResult;
import cn.inkforge.cli.transport.SseStream;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Base64;
import java.util.Deque;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

class CrossLanguageCliInputParityTest {

    private static final byte[] DOWNLOAD_CONTENT =
            "完整二进制😀".getBytes(StandardCharsets.UTF_8);

    private final JsonMapper json = JsonMapper.builder().build();

    @TempDir
    private Path temporaryDirectory;

    @Test
    void 全部一百二十五个命令的最小输入与错误边界必须和Python一致() throws Exception {
        List<String> commands = commandNames();
        assertThat(commands).hasSize(125);

        ArrayNode cases = json.createArrayNode();
        commands.forEach(command -> {
            ObjectNode item = cases.addObject();
            item.put("command", command);
            item.set("arguments", json.createArrayNode());
            item.set("payload", json.createObjectNode());
        });
        JsonNode python = runPythonProbe(cases);
        assertThat(python.isArray()).isTrue();
        assertThat(python.size()).isEqualTo(commands.size());

        for (int index = 0; index < commands.size(); index++) {
            String command = commands.get(index);
            assertThat(runJava(command)).as(command).isEqualTo(python.get(index));
        }
    }

    @Test
    void 三十条代表成功链路的输出与公共请求映射必须和Python一致() throws Exception {
        ObjectNode fixture;
        try (InputStream source = getClass().getResourceAsStream(
                "/cli-contracts/parity-success-cases.json")) {
            if (source == null) throw new IllegalStateException("缺少 CLI 成功差异 fixture");
            fixture = (ObjectNode) json.readTree(source);
        }
        assertThat(fixture.get("schemaVersion").textValue())
                .isEqualTo("inkforge-cli-parity-success/1.0");
        ArrayNode sourceCases = (ArrayNode) fixture.get("cases");
        assertThat(sourceCases.size()).isEqualTo(30);

        ArrayNode probeCases = json.createArrayNode();
        sourceCases.forEach(value -> {
            ObjectNode item = (ObjectNode) value.deepCopy();
            item.put("mode", "scripted");
            item.put("captureCalls", true);
            probeCases.add(item);
        });
        JsonNode python = runPythonProbe(probeCases);
        assertThat(python.isArray()).isTrue();
        assertThat(python.size()).isEqualTo(probeCases.size());

        for (int index = 0; index < probeCases.size(); index++) {
            ObjectNode item = (ObjectNode) probeCases.get(index);
            String command = item.get("command").textValue();
            assertThat(runJavaCase(item)).as(command).isEqualTo(python.get(index));
        }
    }

    @Test
    void 五个观察命令的七条JSONL场景请求顺序和终态退出码必须和Python一致() throws Exception {
        ObjectNode fixture;
        try (InputStream source = getClass().getResourceAsStream(
                "/cli-contracts/parity-watch-cases.json")) {
            if (source == null) throw new IllegalStateException("缺少 CLI watcher 差异 fixture");
            fixture = (ObjectNode) json.readTree(source);
        }
        assertThat(fixture.get("schemaVersion").textValue())
                .isEqualTo("inkforge-cli-parity-watch/1.0");
        ArrayNode sourceCases = (ArrayNode) fixture.get("cases");
        assertThat(sourceCases.size()).isEqualTo(7);

        ArrayNode probeCases = json.createArrayNode();
        sourceCases.forEach(value -> {
            ObjectNode item = (ObjectNode) value.deepCopy();
            item.put("mode", "scripted");
            item.put("captureCalls", true);
            probeCases.add(item);
        });
        JsonNode python = runPythonProbe(probeCases);
        assertThat(python.isArray()).isTrue();
        assertThat(python.size()).isEqualTo(probeCases.size());
        for (int index = 0; index < probeCases.size(); index++) {
            ObjectNode item = (ObjectNode) probeCases.get(index);
            String command = item.get("command").textValue();
            assertThat(runJavaCase(item)).as(command).isEqualTo(python.get(index));
        }
    }

    @Test
    void V2非法问答与观察响应的退出帧和API调用必须和Python一致() throws Exception {
        ObjectNode fixture;
        try (InputStream source = getClass().getResourceAsStream(
                "/cli-contracts/parity-v2-contract-error-cases.json")) {
            if (source == null) throw new IllegalStateException("缺少 CLI V2 契约错误差异 fixture");
            fixture = (ObjectNode) json.readTree(source);
        }
        assertThat(fixture.get("schemaVersion").textValue())
                .isEqualTo("inkforge-cli-parity-v2-contract-errors/1.0");
        ArrayNode sourceCases = (ArrayNode) fixture.get("cases");
        assertThat(sourceCases.size()).isEqualTo(16);

        ArrayNode probeCases = json.createArrayNode();
        sourceCases.forEach(value -> {
            ObjectNode item = (ObjectNode) value.deepCopy();
            item.put("mode", "scripted");
            item.put("captureCalls", true);
            probeCases.add(item);
        });
        JsonNode python = runPythonProbe(probeCases);
        assertThat(python.isArray()).isTrue();
        assertThat(python.size()).isEqualTo(probeCases.size());

        for (int index = 0; index < probeCases.size(); index++) {
            ObjectNode item = (ObjectNode) probeCases.get(index);
            String caseId = item.get("caseId").textValue();
            ObjectNode javaResult = runJavaCase(item);
            assertThat(javaResult).as(caseId).isEqualTo(python.get(index));
            assertThat(javaResult.get("exitCode").intValue())
                    .as(caseId)
                    .isEqualTo(item.get("expectedExitCode").intValue());
            JsonNode frames = javaResult.get("frames");
            assertThat(frames.isArray()).as(caseId).isTrue();
            assertThat(frames.size()).as(caseId).isEqualTo(1);
            assertThat(frames.get(0).at("/error/code").textValue())
                    .as(caseId)
                    .isEqualTo(item.get("expectedErrorCode").textValue());
            assertThat(javaResult.get("calls"))
                    .as(caseId)
                    .isEqualTo(item.get("expectedCalls"));
        }
    }

    @Test
    void 十条文件链路的输入输出字节描述符和传输映射必须和Python一致() throws Exception {
        ObjectNode fixture;
        try (InputStream source = getClass().getResourceAsStream(
                "/cli-contracts/parity-file-cases.json")) {
            if (source == null) throw new IllegalStateException("缺少 CLI 文件差异 fixture");
            fixture = (ObjectNode) json.readTree(source);
        }
        assertThat(fixture.get("schemaVersion").textValue())
                .isEqualTo("inkforge-cli-parity-file/1.0");
        ArrayNode sourceCases = (ArrayNode) fixture.get("cases");
        assertThat(sourceCases.size()).isEqualTo(10);

        ArrayNode probeCases = json.createArrayNode();
        sourceCases.forEach(value -> {
            ObjectNode item = (ObjectNode) value.deepCopy();
            item.put("mode", "scripted");
            item.put("captureCalls", true);
            probeCases.add(item);
        });
        JsonNode python = runPythonProbe(probeCases);
        assertThat(python.isArray()).isTrue();
        assertThat(python.size()).isEqualTo(probeCases.size());
        for (int index = 0; index < probeCases.size(); index++) {
            ObjectNode item = (ObjectNode) probeCases.get(index);
            String command = item.get("command").textValue();
            Path caseDirectory = temporaryDirectory
                    .resolve("case-" + index)
                    .toAbsolutePath()
                    .normalize();
            Files.createDirectories(caseDirectory);
            assertThat(runJavaFileCase(item, caseDirectory))
                    .as(command)
                    .isEqualTo(python.get(index));
        }
    }

    private List<String> commandNames() throws Exception {
        try (InputStream source = getClass().getResourceAsStream(
                "/cli-contracts/command-registry.json")) {
            if (source == null) throw new IllegalStateException("缺少 CLI registry");
            return new ArrayList<>(CommandCatalog.load(source, json).specs().keySet());
        }
    }

    private ObjectNode runJava(String command) {
        MemoryConfigStore configs = new MemoryConfigStore();
        MemoryCredentialStore credentials = new MemoryCredentialStore();
        configs.save(
                "default",
                new ProfileConfig("http://127.0.0.1:8000", "parity-user"));
        credentials.set("default", "http://127.0.0.1:8000", "parity-token");
        CliApplication application = CliApplication.createDefault(new CliDependencies(
                (origin, token) -> new FailingApi(),
                configs,
                credentials,
                prompt -> new char[0],
                () -> false,
                json));
        ByteArrayOutputStream stdout = new ByteArrayOutputStream();
        ByteArrayOutputStream stderr = new ByteArrayOutputStream();
        int exitCode = application.run(
                List.of(command),
                new ByteArrayInputStream("{}".getBytes(StandardCharsets.UTF_8)),
                stdout,
                stderr);

        ObjectNode result = json.createObjectNode();
        result.put("command", command);
        result.put("exitCode", exitCode);
        ArrayNode frames = result.putArray("frames");
        stdout.toString(StandardCharsets.UTF_8).lines()
                .map(json::readTree)
                .forEach(frames::add);
        result.put("stderr", stderr.toString(StandardCharsets.UTF_8));
        return result;
    }

    private ObjectNode runJavaCase(ObjectNode item) {
        String command = item.get("command").textValue();
        MemoryConfigStore configs = new MemoryConfigStore();
        MemoryCredentialStore credentials = new MemoryCredentialStore();
        configs.save(
                "default",
                new ProfileConfig("http://127.0.0.1:8000", "parity-user"));
        credentials.set("default", "http://127.0.0.1:8000", "parity-token");
        RecordingApi api = new RecordingApi(item);
        boolean tty = item.path("tty").asBoolean(false);
        double[] now = {0.0};
        CliDependencies dependencies = item.path("fakeClock").asBoolean(false)
                ? new CliDependencies(
                        (origin, token) -> api,
                        configs,
                        credentials,
                        prompt -> "parity-password".toCharArray(),
                        () -> tty,
                        json,
                        () -> now[0],
                        seconds -> now[0] += seconds)
                : new CliDependencies(
                        (origin, token) -> api,
                        configs,
                        credentials,
                        prompt -> "parity-password".toCharArray(),
                        () -> tty,
                        json);
        CliApplication application = CliApplication.createDefault(dependencies);
        List<String> arguments = new ArrayList<>();
        arguments.add(command);
        JsonNode commandArguments = item.get("arguments");
        if (commandArguments != null && commandArguments.isArray()) {
            commandArguments.forEach(value -> arguments.add(value.textValue()));
        }
        ByteArrayOutputStream stdout = new ByteArrayOutputStream();
        ByteArrayOutputStream stderr = new ByteArrayOutputStream();
        JsonNode payload = item.has("payload") ? item.get("payload") : json.createObjectNode();
        int exitCode = application.run(
                arguments,
                new ByteArrayInputStream(json.writeValueAsBytes(payload)),
                stdout,
                stderr);

        ObjectNode result = json.createObjectNode();
        result.put("command", command);
        result.put("exitCode", exitCode);
        ArrayNode frames = result.putArray("frames");
        stdout.toString(StandardCharsets.UTF_8).lines()
                .map(json::readTree)
                .forEach(frames::add);
        result.put("stderr", stderr.toString(StandardCharsets.UTF_8));
        result.set("calls", api.calls);
        return result;
    }

    private ObjectNode runJavaFileCase(ObjectNode source, Path temporary) throws Exception {
        ObjectNode expanded = (ObjectNode) replaceToken(source, "${TMP}", temporary.toString());
        materializeFiles(expanded, temporary);
        ObjectNode result = runJavaCase(expanded);
        JsonNode captureNames = expanded.get("captureFiles");
        if (captureNames != null) {
            ObjectNode captures = json.createObjectNode();
            captureNames.forEach(value -> {
                String name = value.textValue();
                Path target = temporary.resolve(name).normalize();
                if (!target.startsWith(temporary) || !Files.isRegularFile(target)) {
                    throw new IllegalStateException("预期输出文件不存在：" + name);
                }
                try {
                    byte[] content = Files.readAllBytes(target);
                    ObjectNode descriptor = captures.putObject(name);
                    descriptor.put("bytes", content.length);
                    descriptor.put("sha256", sha256(content));
                } catch (java.io.IOException exception) {
                    throw new IllegalStateException("读取差异输出文件失败：" + name, exception);
                }
            });
            result.set("files", captures);
        }
        return (ObjectNode) replaceToken(result, temporary.toString(), "${TMP}");
    }

    private void materializeFiles(ObjectNode item, Path temporary) throws Exception {
        JsonNode files = item.get("files");
        if (files == null) return;
        if (!files.isObject()) throw new IllegalArgumentException("files 必须是 JSON 对象");
        files.properties().forEach(entry -> {
            Path target = temporary.resolve(entry.getKey()).normalize();
            if (!target.startsWith(temporary)) {
                throw new IllegalArgumentException("fixture 文件不能逃逸临时目录");
            }
            JsonNode specification = entry.getValue();
            String encoding = specification.path("encoding").textValue();
            String content = specification.path("content").textValue();
            byte[] bytes = switch (encoding) {
                case "utf8" -> content.getBytes(StandardCharsets.UTF_8);
                case "base64" -> Base64.getDecoder().decode(content);
                default -> throw new IllegalArgumentException("fixture 文件编码无效：" + encoding);
            };
            try {
                Files.createDirectories(target.getParent());
                Files.write(target, bytes);
            } catch (java.io.IOException exception) {
                throw new IllegalStateException("创建差异输入文件失败", exception);
            }
        });
    }

    private JsonNode replaceToken(JsonNode value, String token, String replacement) {
        if (value.isTextual()) {
            return json.getNodeFactory()
                    .textNode(value.textValue().replace(token, replacement));
        }
        if (value.isArray()) {
            ArrayNode result = json.createArrayNode();
            value.forEach(item -> result.add(replaceToken(item, token, replacement)));
            return result;
        }
        if (value.isObject()) {
            ObjectNode result = json.createObjectNode();
            value.properties().forEach(entry -> result.set(
                    entry.getKey(), replaceToken(entry.getValue(), token, replacement)));
            return result;
        }
        return value.deepCopy();
    }

    private static String sha256(byte[] content) {
        try {
            return HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256").digest(content));
        } catch (java.security.NoSuchAlgorithmException exception) {
            throw new IllegalStateException("当前 JRE 缺少 SHA-256", exception);
        }
    }

    private JsonNode runPythonProbe(ArrayNode cases) throws Exception {
        Path root = repositoryRoot();
        Path virtualEnvironmentPython = root.resolve(".venv/bin/python");
        List<String> command = Files.isExecutable(virtualEnvironmentPython)
                ? List.of(
                        virtualEnvironmentPython.toString(),
                        "tools/inkforge-cli/tests/support/cli_parity_probe.py")
                : List.of(
                        "uv",
                        "run",
                        "python",
                        "tools/inkforge-cli/tests/support/cli_parity_probe.py");
        Process process = new ProcessBuilder(command)
                .directory(root.toFile())
                .start();
        process.getOutputStream().write(json.writeValueAsBytes(cases));
        process.getOutputStream().close();
        boolean completed = process.waitFor(Duration.ofSeconds(30).toMillis(), TimeUnit.MILLISECONDS);
        if (!completed) {
            process.destroyForcibly();
            throw new IllegalStateException("Python CLI 差异探针超时");
        }
        String stdout = new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
        String stderr = new String(process.getErrorStream().readAllBytes(), StandardCharsets.UTF_8);
        assertThat(process.exitValue()).as(stderr).isZero();
        return json.readTree(stdout);
    }

    private Path repositoryRoot() {
        Path current = Path.of(System.getProperty("user.dir")).toAbsolutePath().normalize();
        if (Files.isRegularFile(current.resolve("contracts/cli/command-registry.json"))) {
            return current;
        }
        Path root = current.resolve("../..").normalize();
        if (!Files.isRegularFile(root.resolve("contracts/cli/command-registry.json"))) {
            throw new IllegalStateException("无法定位仓库根目录");
        }
        return root;
    }

    private final class FailingApi implements CoreApi {

        private CoreApiException failure() {
            ObjectNode details = json.createObjectNode().put("source", "shared-fixture");
            return new CoreApiException(
                    503,
                    "PARITY_CORE_ERROR",
                    "差异测试远端错误",
                    details,
                    "parity-request-1");
        }

        @Override
        public JsonNode request(String method, String path) {
            throw failure();
        }

        @Override
        public JsonNode request(String method, String path, JsonNode body) {
            throw failure();
        }

        @Override
        public JsonNode request(
                String method,
                String path,
                Map<String, List<String>> query,
                JsonNode body) {
            throw failure();
        }

        @Override
        public LoginResult login(String username, String password) {
            throw failure();
        }

        @Override
        public SseStream openSse(String taskId, String lastEventId) {
            throw failure();
        }

        @Override
        public JsonNode upload(
                String path,
                Path file,
                String mediaType,
                Map<String, String> fields) {
            throw failure();
        }

        @Override
        public FileDescriptor download(String method, String path, Path target) {
            throw failure();
        }
    }

    private final class RecordingApi implements CoreApi {

        private final Deque<JsonNode> responses = new ArrayDeque<>();
        private final Deque<List<JsonNode>> streams = new ArrayDeque<>();
        private final ArrayNode calls = json.createArrayNode();

        private RecordingApi(ObjectNode item) {
            JsonNode scriptedResponses = item.get("responses");
            if (scriptedResponses != null && scriptedResponses.isArray()) {
                scriptedResponses.forEach(value -> responses.addLast(value.deepCopy()));
            }
            JsonNode scriptedStreams = item.get("streams");
            if (scriptedStreams != null && scriptedStreams.isArray()) {
                scriptedStreams.forEach(stream -> {
                    List<JsonNode> values = new ArrayList<>();
                    stream.forEach(value -> values.add(value.deepCopy()));
                    streams.addLast(List.copyOf(values));
                });
            }
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
            ObjectNode call = calls.addObject();
            call.put("kind", "request");
            call.put("method", method);
            call.put("path", path);
            ObjectNode normalizedQuery = call.putObject("query");
            query.forEach((name, values) -> {
                ArrayNode items = normalizedQuery.putArray(name);
                values.forEach(items::add);
            });
            if (body == null) call.putNull("body");
            else call.set("body", body.deepCopy());
            return response();
        }

        @Override
        public LoginResult login(String username, String password) {
            ObjectNode call = calls.addObject();
            call.put("kind", "login");
            call.put("method", "POST");
            call.put("path", "/api/v1/auth/login");
            call.set("query", json.createObjectNode());
            call.set("body", json.createObjectNode().put("username", username));
            return new LoginResult(
                    json.createObjectNode()
                            .put("id", "parity-user-id")
                            .put("username", username),
                    "parity-session");
        }

        @Override
        public SseStream openSse(String taskId, String lastEventId) {
            ObjectNode call = calls.addObject();
            call.put("kind", "sse");
            call.put("taskId", taskId);
            if (lastEventId == null) call.putNull("lastEventId");
            else call.put("lastEventId", lastEventId);
            List<JsonNode> values = streams.isEmpty() ? List.of() : streams.removeFirst();
            return new SseStream() {
                private int index;

                @Override
                public boolean hasNext() {
                    return index < values.size();
                }

                @Override
                public JsonNode next() {
                    if (!hasNext()) throw new NoSuchElementException();
                    return values.get(index++);
                }

                @Override
                public void close() {}
            };
        }

        @Override
        public JsonNode upload(
                String path,
                Path file,
                String mediaType,
                Map<String, String> fields)
                throws java.io.IOException {
            byte[] content = Files.readAllBytes(file);
            ObjectNode call = calls.addObject();
            call.put("kind", "upload");
            call.put("method", "POST");
            call.put("path", path);
            call.set("query", json.createObjectNode());
            call.putNull("body");
            ObjectNode normalizedFields = call.putObject("fields");
            fields.forEach(normalizedFields::put);
            ObjectNode uploadedFile = call.putObject("file");
            uploadedFile.put("name", file.getFileName().toString());
            uploadedFile.put("mediaType", mediaType);
            uploadedFile.put("bytes", content.length);
            uploadedFile.put("sha256", sha256(content));
            return response();
        }

        @Override
        public FileDescriptor download(String method, String path, Path target)
                throws java.io.IOException {
            ObjectNode call = calls.addObject();
            call.put("kind", "download");
            call.put("method", method);
            call.put("path", path);
            call.set("query", json.createObjectNode());
            call.putNull("body");
            return AtomicFiles.write(
                    target,
                    new ByteArrayInputStream(DOWNLOAD_CONTENT),
                    "application/octet-stream");
        }

        private JsonNode response() {
            if (!responses.isEmpty()) return responses.removeFirst();
            return json.createObjectNode().put("id", "ok").putNull("nullable");
        }
    }
}
