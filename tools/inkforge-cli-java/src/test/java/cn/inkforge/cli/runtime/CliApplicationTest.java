package cn.inkforge.cli.runtime;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.cli.config.MemoryConfigStore;
import cn.inkforge.cli.config.MemoryCredentialStore;
import cn.inkforge.cli.transport.CoreApi;
import cn.inkforge.cli.transport.FileDescriptor;
import cn.inkforge.cli.transport.LoginResult;
import cn.inkforge.cli.transport.CoreTransportException;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

class CliApplicationTest {

    private final JsonMapper json = JsonMapper.builder().build();

    @Test
    void 登录必须使用TTY且会话不会进入输出() {
        MemoryConfigStore configs = new MemoryConfigStore();
        MemoryCredentialStore credentials = new MemoryCredentialStore();
        FakeApi api = new FakeApi(json);
        CliDependencies dependencies = new CliDependencies(
                (origin, token) -> api,
                configs,
                credentials,
                prompt -> "pw".toCharArray(),
                () -> true,
                json);
        ByteArrayOutputStream output = new ByteArrayOutputStream();

        int exit = CliApplication.createDefault(dependencies).run(
                List.of(
                        "auth.login",
                        "--origin", "http://127.0.0.1:8000",
                        "--username", "nie"),
                new ByteArrayInputStream(new byte[0]),
                output,
                new ByteArrayOutputStream());

        assertThat(exit).isZero();
        assertThat(output.toString(StandardCharsets.UTF_8))
                .isEqualTo("{\"ok\":true,\"command\":\"auth.login\","
                        + "\"data\":{\"id\":\"u1\",\"username\":\"nie\"}}\n")
                .doesNotContain("session-secret", "pw");
        assertThat(configs.get("default")).isPresent();
        assertThat(credentials.get("default", "http://127.0.0.1:8000"))
                .contains("session-secret");
    }

    @Test
    void 非登录命令严格读取单个JSON对象并绑定已保存身份() {
        MemoryConfigStore configs = new MemoryConfigStore();
        MemoryCredentialStore credentials = new MemoryCredentialStore();
        configs.save("default", new cn.inkforge.cli.config.ProfileConfig(
                "http://127.0.0.1:8000", "nie"));
        credentials.set("default", "http://127.0.0.1:8000", "session-secret");
        FakeApi api = new FakeApi(json);
        CliDependencies dependencies = new CliDependencies(
                (origin, token) -> {
                    assertThat(token).isEqualTo("session-secret");
                    return api;
                },
                configs,
                credentials,
                prompt -> new char[0],
                () -> false,
                json);
        ByteArrayOutputStream output = new ByteArrayOutputStream();

        int exit = CliApplication.createDefault(dependencies).run(
                List.of("auth.whoami"),
                bytes("\ufeff{\"expectedUsername\":\"nie\"}"),
                output,
                new ByteArrayOutputStream());

        assertThat(exit).isZero();
        assertThat(output.toString(StandardCharsets.UTF_8))
                .contains("\"ok\":true", "\"username\":\"nie\"");
        assertThat(api.lastMethod).isEqualTo("GET");
        assertThat(api.lastPath).isEqualTo("/api/v1/auth/me");
    }

    @Test
    void 输入与身份错误保持稳定信封和退出码() {
        CliDependencies dependencies = new CliDependencies(
                (origin, token) -> new FakeApi(json),
                new MemoryConfigStore(),
                new MemoryCredentialStore(),
                prompt -> new char[0],
                () -> false,
                json);
        CliApplication application = CliApplication.createDefault(dependencies);

        Result missingCommand = run(application, List.of(), "");
        assertThat(missingCommand.exit()).isEqualTo(2);
        assertThat(missingCommand.stdout()).contains("\"code\":\"COMMAND_REQUIRED\"");

        Result invalidJson = run(application, List.of("auth.whoami"), "[]");
        assertThat(invalidJson.exit()).isEqualTo(2);
        assertThat(invalidJson.stdout()).contains("\"code\":\"JSON_OBJECT_REQUIRED\"");

        Result authRequired = run(application, List.of("auth.whoami"), "{}");
        assertThat(authRequired.exit()).isEqualTo(3);
        assertThat(authRequired.stdout()).contains("\"code\":\"AUTH_REQUIRED\"");

        Result ttyRequired = run(
                application,
                List.of(
                        "auth.login",
                        "--origin", "http://127.0.0.1:8000",
                        "--username", "nie"),
                "");
        assertThat(ttyRequired.exit()).isEqualTo(2);
        assertThat(ttyRequired.stdout()).contains("\"code\":\"TTY_REQUIRED\"");
    }

    @Test
    void 网络失败按既有短篇与长篇错误边界输出() {
        MemoryConfigStore configs = new MemoryConfigStore();
        MemoryCredentialStore credentials = new MemoryCredentialStore();
        configs.save("default", new cn.inkforge.cli.config.ProfileConfig(
                "http://127.0.0.1:8000", "nie"));
        credentials.set("default", "http://127.0.0.1:8000", "session-secret");
        CliApplication application = CliApplication.createDefault(new CliDependencies(
                (origin, token) -> new TransportFailureApi(),
                configs,
                credentials,
                prompt -> new char[0],
                () -> false,
                json));

        DetailedResult shortFailure = runDetailed(application, List.of("short.list"), "{}");
        assertThat(shortFailure.exit()).isEqualTo(1);
        assertThat(shortFailure.stdout()).contains("\"code\":\"UNEXPECTED_ERROR\"");
        assertThat(shortFailure.stderr()).isEqualTo("InkForge CLI 遇到未预期错误。\n");

        DetailedResult longFailure = runDetailed(application, List.of("long.novel.list"), "{}");
        assertThat(longFailure.exit()).isEqualTo(5);
        assertThat(longFailure.stdout()).contains("\"code\":\"CORE_TRANSPORT_ERROR\"");
        assertThat(longFailure.stderr()).isEmpty();
    }

    private Result run(CliApplication application, List<String> arguments, String input) {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        int exit = application.run(
                arguments,
                bytes(input),
                output,
                new ByteArrayOutputStream());
        return new Result(exit, output.toString(StandardCharsets.UTF_8));
    }

    private DetailedResult runDetailed(
            CliApplication application, List<String> arguments, String input) {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        ByteArrayOutputStream error = new ByteArrayOutputStream();
        int exit = application.run(arguments, bytes(input), output, error);
        return new DetailedResult(
                exit,
                output.toString(StandardCharsets.UTF_8),
                error.toString(StandardCharsets.UTF_8));
    }

    private static ByteArrayInputStream bytes(String value) {
        return new ByteArrayInputStream(value.getBytes(StandardCharsets.UTF_8));
    }

    private record Result(int exit, String stdout) {}

    private record DetailedResult(int exit, String stdout, String stderr) {}

    private static final class FakeApi implements CoreApi {

        private final JsonMapper json;
        private String lastMethod;
        private String lastPath;

        private FakeApi(JsonMapper json) {
            this.json = json;
        }

        @Override
        public JsonNode request(String method, String path) {
            lastMethod = method;
            lastPath = path;
            return json.createObjectNode().put("id", "u1").put("username", "nie");
        }

        @Override
        public JsonNode request(String method, String path, JsonNode body) {
            return request(method, path);
        }

        @Override
        public LoginResult login(String username, String password) {
            assertThat(username).isEqualTo("nie");
            assertThat(password).isEqualTo("pw");
            return new LoginResult(
                    json.createObjectNode().put("id", "u1").put("username", username),
                    "session-secret");
        }

        @Override
        public FileDescriptor download(String method, String path, Path target) {
            throw new UnsupportedOperationException();
        }
    }

    private static final class TransportFailureApi implements CoreApi {

        @Override
        public JsonNode request(String method, String path) {
            throw new CoreTransportException();
        }

        @Override
        public JsonNode request(String method, String path, JsonNode body) {
            throw new CoreTransportException();
        }

        @Override
        public JsonNode request(
                String method,
                String path,
                Map<String, List<String>> query,
                JsonNode body) {
            throw new CoreTransportException();
        }

        @Override
        public LoginResult login(String username, String password) {
            throw new CoreTransportException();
        }

        @Override
        public FileDescriptor download(String method, String path, Path target) {
            throw new CoreTransportException();
        }
    }
}
