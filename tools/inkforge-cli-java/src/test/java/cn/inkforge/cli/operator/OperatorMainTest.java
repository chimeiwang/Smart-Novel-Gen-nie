package cn.inkforge.cli.operator;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.cli.config.CredentialStore;
import cn.inkforge.cli.config.MemoryConfigStore;
import cn.inkforge.cli.config.MemoryCredentialStore;
import cn.inkforge.cli.config.ProfileConfig;
import cn.inkforge.cli.config.SecureCredentialBackendException;
import cn.inkforge.cli.runtime.CliInputException;
import cn.inkforge.cli.transport.CoreApi;
import cn.inkforge.cli.transport.CoreTransportException;
import cn.inkforge.cli.transport.FileDescriptor;
import cn.inkforge.cli.transport.LoginResult;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.node.ObjectNode;

class OperatorMainTest {
    private final JsonMapper json = JsonMapper.builder().build();
    @TempDir Path directory;
    private Path repository;
    private Path sourceJar;
    private Path java;
    private Path state;
    private Path installedJar;
    private MemoryConfigStore configs;
    private CredentialStore credentials;
    private final List<String> calls = new ArrayList<>();
    private JsonNode lastBody;
    private String mode;
    private String username = "作者";
    private boolean tty;
    private boolean unavailable;
    private boolean backendLoadFailure;
    private boolean completedV2;
    private String responseText = "完整正文😀\n尾行";
    private int passwordPrompts;

    @BeforeEach
    void prepare() throws Exception {
        directory = directory.toRealPath();
        repository = directory.resolve("source");
        Files.createDirectories(repository.resolve("tools/inkforge-cli-java"));
        Files.writeString(repository.resolve("tools/inkforge-cli-java/pom.xml"), "fixture");
        git("init", "-q");
        git("-c", "user.name=测试", "-c", "user.email=test@example.invalid", "commit", "-q", "--allow-empty", "-m", "测试基线");
        sourceJar = directory.resolve("source.jar");
        Files.writeString(sourceJar, "只供离线测试的运行包");
        java = Path.of(System.getProperty("java.home"), "bin", "java").toRealPath();
        install("local", "作者");
    }

    @AfterEach
    void removeOnlyTestRuntimeLinks() throws Exception {
        // JUnit 不跟随链接；主动回收本次测试的链接，避免外部目标警告淹没有效诊断。
        try (var paths = Files.walk(directory)) {
            for (Path path : paths.filter(Files::isSymbolicLink).toList()) Files.delete(path);
        }
    }

    private void install(String environment, String expectedUsername) throws Exception {
        mode = environment;
        state = directory.resolve(environment);
        new OperatorInstallation(state, json).install(mode, repository, sourceJar, java, expectedUsername);
        installedJar = state.resolve("runtime/inkforge-cli.jar");
        configs = new MemoryConfigStore();
        configs.save(OperatorInstallation.profile(mode), new ProfileConfig(OperatorInstallation.origin(mode), "作者"));
        credentials = new MemoryCredentialStore();
        credentials.set(OperatorInstallation.profile(mode), OperatorInstallation.origin(mode), "仅测试会话");
    }

    @Test
    void 安装记录实际包和dirty但不依赖旧运行仓库() throws Exception {
        var config = new OperatorInstallation(state, json).load(mode, installedJar, java);
        assertThat(config.repositoryDirty()).isTrue();
        assertThat(config.jarSha256()).isEqualTo(OperatorInstallation.sha256(sourceJar));
        assertThat(Files.readSymbolicLink(state.resolve("runtime/java"))).isEqualTo(java);
        assertThat(Files.getPosixFilePermissions(state)).isEqualTo(PosixFilePermissions.fromString("rwx------"));
        assertThat(Files.getPosixFilePermissions(state.resolve("config.json"))).isEqualTo(PosixFilePermissions.fromString("rw-------"));
        Files.move(repository, directory.resolve("source-moved"));
        assertThat(invoke("auth.whoami", "{}").exit()).isZero();
    }

    @Test
    void schema四升级保留用户名且不读取失效旧仓库() throws Exception {
        Path upgraded = directory.resolve("upgrade");
        Files.createDirectory(upgraded);
        ObjectNode old = json.createObjectNode();
        old.put("schemaVersion", 4);
        old.put("repositoryRoot", "/不存在的旧运行副本");
        old.put("repositoryRevision", "旧revision");
        old.put("uvPath", "/不存在的uv");
        old.put("origin", OperatorInstallation.origin(mode));
        old.put("profile", OperatorInstallation.profile(mode));
        old.put("expectedUsername", "作者");
        Files.writeString(upgraded.resolve("config.json"), json.writeValueAsString(old));
        var config = new OperatorInstallation(upgraded, json).install(mode, repository, sourceJar, java, null);
        assertThat(config.expectedUsername()).isEqualTo("作者");
        assertThat(json.readTree(Files.readString(upgraded.resolve("config.json"))).path("schemaVersion").intValue()).isEqualTo(5);
        var explicitlyRebound = new OperatorInstallation(upgraded, json)
                .install(mode, repository, sourceJar, java, "其他作者");
        assertThat(explicitlyRebound.expectedUsername()).isEqualTo("其他作者");
        assertThat(calls).isEmpty();
    }

    @Test
    void configure不初始化安全凭据或访问Core() {
        credentials = null;
        Result result = invokeArguments(List.of(mode, "configure", "--repository-root", repository.toString(),
                "--state-root", directory.resolve("fresh").toString()), "{}", sourceJar);
        assertThat(result.exit()).isZero();
        assertThat(result.output()).contains("来源工作区存在未提交变更：true");
        assertThat(calls).isEmpty();
    }

    @Test
    void 精确四十五命令拒绝其他写入口() {
        assertThat(OperatorMain.ALLOWED_COMMANDS).hasSize(45);
        for (String command : List.of("long.novel.create", "long.video.project.create", "deploy", "configure-any")) {
            Result result = invoke(command, "{}");
            assertThat(result.exit()).isEqualTo(2);
            assertThat(result.error()).contains("OPERATOR_COMMAND_NOT_ALLOWED");
        }
        assertThat(calls).isEmpty();
    }

    @ParameterizedTest
    @ValueSource(strings = {"local", "production"})
    void 双环境业务前身份预检成功且完整保留正文(String environment) throws Exception {
        install(environment, "作者");
        Result result = invoke("long.chapter.get", "{\"chapterId\":\"章一\"}");
        assertThat(result.exit()).isZero();
        assertThat(calls).containsExactly("GET /api/v1/auth/me", "GET /api/v1/chapters/%E7%AB%A0%E4%B8%80");
        assertThat(result.output()).contains("完整正文😀\\n尾行");
        assertThat(result.error()).isEmpty();
    }

    @Test
    void 大Unicode正文不截断且预检不混入业务stdout() {
        responseText = "  中文😀\n\r\n尾行\u2028".repeat(30000) + "完整结尾";
        Result result = invoke("long.chapter.get", "{\"chapterId\":\"c1\"}");
        assertThat(result.exit()).isZero();
        assertThat(json.readTree(result.output()).path("data").path("content").textValue()).isEqualTo(responseText);
        assertThat(result.output().lines().count()).isEqualTo(1);
    }

    @Test
    void V2终态JSONL保持snapshot和terminal顺序() {
        completedV2 = true;
        Result result = invoke("long.task.watch", "{\"taskId\":\"run1\"}");
        assertThat(result.exit()).isZero();
        List<JsonNode> frames = result.output().lines().map(json::readTree).toList();
        assertThat(frames).extracting(frame -> frame.path("type").textValue()).containsExactly("snapshot", "terminal");
        for (JsonNode frame : frames) {
            assertThat(frame.path("data").path("engineVersion").intValue()).isEqualTo(2);
            assertThat(frame.path("data").path("status").textValue()).isEqualTo("completed");
        }
        assertThat(calls).containsExactly("GET /api/v1/auth/me", "GET /api/v1/writing/runs/run1");
    }

    @Test
    void 身份不匹配只做一次预检() {
        username = "其他作者";
        Result result = invoke("long.chapter.get", "{\"chapterId\":\"c1\"}");
        assertThat(result.exit()).isEqualTo(3);
        assertThat(result.output()).contains("IDENTITY_MISMATCH");
        assertThat(calls).containsExactly("GET /api/v1/auth/me");
    }

    @ParameterizedTest
    @ValueSource(strings = {"{\"Origin\":\"https://example.invalid\"}", "{\"PROFILE\":\"other\"}",
            "{\"profile\":\"default\",\"Profile\":\"default\"}", "{\"expectedUsername\":\"作者\"}"})
    void 输入不能覆盖环境与业务身份(String payload) {
        assertThat(invoke("short.list", payload).exit()).isIn(2, 3);
        assertThat(calls).isEmpty();
    }

    @Test
    void 保存的CLI配置漂移在任何网络前拒绝() {
        configs.save("default", new ProfileConfig("https://example.invalid", "作者"));
        Result result = invoke("short.list", "{}");
        assertThat(result.exit()).isEqualTo(3);
        assertThat(result.output()).contains("ORIGIN_MISMATCH");
        assertThat(calls).isEmpty();
    }

    @ParameterizedTest
    @ValueSource(strings = {"answer_question", "rewrite_chapter_selection", "", "PLAN_CHAPTER"})
    void 未开放Operation在身份预检后拒绝(String operation) {
        Result result = invoke("long.agent.start", "{\"operation\":\"" + operation + "\"}");
        assertThat(result.exit()).isEqualTo(2);
        assertThat(result.error()).contains("OPERATOR_OPERATION_NOT_ALLOWED");
        assertThat(calls).containsExactly("GET /api/v1/auth/me");
    }

    @ParameterizedTest
    @ValueSource(strings = {"plan_chapter", "write_chapter", "review_chapter"})
    void 三种已有Operation完整透传(String operation) {
        String payload = "{\"clientRequestId\":\"operator-test-0001\",\"novelId\":\"n1\",\"chapterId\":\"c1\","
                + "\"operation\":\"" + operation + "\",\"target\":{\"type\":\"chapter\",\"id\":\"c1\"},"
                + "\"scope\":{\"kind\":\"chapter\",\"chapterId\":\"c1\"},\"userInstruction\":\"  完整😀\\n文本  \"}";
        Result result = invoke("long.agent.start", payload);
        assertThat(result.exit()).isZero();
        ObjectNode expected = (ObjectNode) json.readTree(payload);
        expected.put("workflow", "long_serial");
        assertThat(lastBody).isEqualTo(expected);
        assertThat(calls).containsExactly("GET /api/v1/auth/me", "POST /api/v1/writing/runs");
    }

    @ParameterizedTest
    @ValueSource(strings = {"local", "production"})
    void 受限Skill不因既有命令名而开放自然启动或澄清(String environment) throws Exception {
        install(environment, "作者");
        for (String command : List.of("long.agent.start", "long.task.resume")) {
            calls.clear();
            String inputMode = command.equals("long.agent.start") ? "natural" : "clarification";
            Result result = invoke(command,
                    "{\"inputMode\":\"" + inputMode + "\",\"operation\":\"plan_chapter\"}");
            assertThat(result.exit()).isEqualTo(2);
            assertThat(result.error()).contains("OPERATOR_INPUT_MODE_NOT_ALLOWED");
            assertThat(calls).containsExactly("GET /api/v1/auth/me");
        }
    }

    @Test
    void 本地登录先ready再读取密码并绑定用户名() throws Exception {
        install("production", null);
        mode = "local";
        state = directory.resolve("local-new");
        new OperatorInstallation(state, json).install(mode, repository, sourceJar, java, null);
        installedJar = state.resolve("runtime/inkforge-cli.jar");
        tty = true;
        Result result = invokeArguments(List.of(mode, "--state-root", state.toString(), "auth.login", "--username", "作者"), "", installedJar);
        assertThat(result.exit()).isZero();
        assertThat(calls).containsExactly("GET /api/v1/health/ready", "密码提示", "登录");
        assertThat(new OperatorInstallation(state, json).load(mode, installedJar, java).expectedUsername()).isEqualTo("作者");
        assertThat(result.output()).doesNotContain("仅测试会话", "仅测试密码");
    }

    @Test
    void 登录无TTY或ready失败都不读密码() {
        Result noTty = invokeArguments(List.of(mode, "--state-root", state.toString(), "auth.login", "--username", "作者"), "", installedJar);
        assertThat(noTty.exit()).isEqualTo(2);
        assertThat(passwordPrompts).isZero();
        assertThat(calls).isEmpty();
        tty = true;
        unavailable = true;
        Result notReady = invokeArguments(List.of(mode, "--state-root", state.toString(), "auth.login", "--username", "作者"), "", installedJar);
        assertThat(notReady.exit()).isEqualTo(5);
        assertThat(notReady.output()).contains("CORE_TRANSPORT_ERROR");
        assertThat(passwordPrompts).isZero();
    }

    @Test
    void 登录不能更换账号或增加origin参数() {
        tty = true;
        for (List<String> arguments : List.of(List.of("--username", "其他作者"), List.of("--origin", "https://example.invalid"))) {
            List<String> command = new ArrayList<>(List.of(mode, "--state-root", state.toString(), "auth.login"));
            command.addAll(arguments);
            assertThat(invokeArguments(command, "", installedJar).exit()).isIn(2, 3);
        }
        assertThat(calls).isEmpty();
    }

    @Test
    void 认证和短篇传输失败保留五号退出() {
        unavailable = true;
        for (String command : List.of("auth.whoami", "short.list")) {
            Result result = invoke(command, "{}");
            assertThat(result.exit()).isEqualTo(5);
            assertThat(result.output()).contains("CORE_TRANSPORT_ERROR").doesNotContain("UNEXPECTED_ERROR");
        }
    }

    @Test
    void 运行期凭据故障不泄露详情且零网络() {
        credentials = new CredentialStore() {
            public Optional<String> get(String profile, String origin) { throw new SecureCredentialBackendException("不可展示的底层原文"); }
            public void set(String profile, String origin, String token) { throw new AssertionError(); }
            public void delete(String profile, String origin) { throw new AssertionError(); }
        };
        Result result = invoke("short.list", "{}");
        assertThat(result.exit()).isEqualTo(3);
        assertThat(result.output()).contains("SECURE_CREDENTIAL_BACKEND_REQUIRED").doesNotContain("不可展示的底层原文");
        assertThat(calls).isEmpty();
    }

    @Test
    void 原生后端加载失败也是结构化stdout并且零网络() {
        backendLoadFailure = true;
        Result result = invoke("auth.whoami", "{}");
        assertThat(result.exit()).isEqualTo(3);
        assertThat(result.output()).contains("SECURE_CREDENTIAL_BACKEND_REQUIRED", "auth.whoami")
                .doesNotContain("不应显示的原生加载原文");
        assertThat(result.error()).isEmpty();
        assertThat(calls).isEmpty();
    }

    @Test
    void 包被修改或权限被放宽时零网络() throws Exception {
        Files.writeString(installedJar, "被替换");
        assertThat(invoke("short.list", "{}").exit()).isEqualTo(3);
        Files.copy(sourceJar, installedJar, StandardCopyOption.REPLACE_EXISTING);
        Files.setPosixFilePermissions(installedJar, PosixFilePermissions.fromString("rw-r--r--"));
        assertThat(invoke("short.list", "{}").exit()).isEqualTo(3);
        assertThat(calls).isEmpty();
    }

    @Test
    void 配置不能改环境且拒绝符号链接() throws Exception {
        Path configPath = state.resolve("config.json");
        ObjectNode config = (ObjectNode) json.readTree(Files.readString(configPath));
        config.put("origin", "https://example.invalid");
        Files.writeString(configPath, json.writeValueAsString(config));
        assertThat(invoke("short.list", "{}").exit()).isEqualTo(3);
        Files.move(configPath, state.resolve("original.json"));
        Files.createSymbolicLink(configPath, state.resolve("original.json"));
        assertThat(invoke("short.list", "{}").exit()).isEqualTo(3);
        assertThat(calls).isEmpty();
    }

    @ParameterizedTest
    @ValueSource(strings = {"{} {}", "[]", "{", ""})
    void 无效JSON在任何网络前拒绝(String payload) {
        assertThat(invoke("short.list", payload).exit()).isEqualTo(2);
        assertThat(calls).isEmpty();
    }

    private Result invoke(String command, String input) {
        return invokeArguments(List.of(mode, "--state-root", state.toString(), command), input, installedJar);
    }

    private Result invokeArguments(List<String> arguments, String input, Path jar) {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        ByteArrayOutputStream error = new ByteArrayOutputStream();
        OperatorMain.Host host = new OperatorMain.Host(json, Map.of(), directory.toString(), jar, java,
                () -> {
                    if (backendLoadFailure) throw new SecureCredentialBackendException("不应显示的原生加载原文");
                    if (credentials == null) throw new AssertionError("configure 不能读取凭据");
                    return credentials;
                },
                configs, (environment, origin, token) -> {
                    assertThat(origin).isEqualTo(OperatorInstallation.origin(environment));
                    return new FakeApi();
                }, prompt -> { passwordPrompts++; calls.add("密码提示"); return "仅测试密码".toCharArray(); }, () -> tty);
        int exit = OperatorMain.run(arguments, new ByteArrayInputStream(input.getBytes(StandardCharsets.UTF_8)), output, error, host);
        return new Result(exit, output.toString(StandardCharsets.UTF_8), error.toString(StandardCharsets.UTF_8));
    }

    private void git(String... arguments) throws Exception {
        List<String> command = new ArrayList<>(List.of("git", "-C", repository.toString()));
        command.addAll(List.of(arguments));
        Process process = new ProcessBuilder(command).redirectErrorStream(true).start();
        String output = new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
        assertThat(process.waitFor()).as(output).isZero();
    }

    private final class FakeApi implements CoreApi {
        public JsonNode request(String method, String path) { return request(method, path, null); }
        public JsonNode request(String method, String path, JsonNode body) {
            calls.add(method + " " + path);
            if (unavailable) throw new CoreTransportException();
            lastBody = body;
            if (path.equals("/api/v1/auth/me")) return json.createObjectNode().put("username", username);
            if (completedV2 && path.equals("/api/v1/writing/runs/run1")) {
                ObjectNode snapshot = json.createObjectNode().put("engineVersion", 2).put("runId", "run1")
                        .put("taskId", "run1").put("workflow", "long_serial").put("operation", "answer_question")
                        .put("status", "completed").put("lastEventSequence", 9).put("revision", 3);
                snapshot.putArray("activeSteps");
                snapshot.putNull("artifact");
                snapshot.putNull("error");
                return snapshot;
            }
            return json.createObjectNode().put("content", responseText).put("engineVersion", 1).put("runId", "run1");
        }
        public JsonNode request(String method, String path, Map<String, List<String>> query, JsonNode body) {
            return request(method, path, body);
        }
        public LoginResult login(String account, String password) {
            calls.add("登录");
            return new LoginResult(json.createObjectNode().put("username", account), "仅测试会话");
        }
        public FileDescriptor download(String method, String path, Path target) { throw new AssertionError(); }
    }

    private record Result(int exit, String output, String error) {}
}
