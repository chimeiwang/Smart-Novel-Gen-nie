package cn.inkforge.cli;

import cn.inkforge.cli.config.CredentialStore;
import cn.inkforge.cli.config.JsonConfigStore;
import cn.inkforge.cli.config.PlatformCredentialStores;
import cn.inkforge.cli.config.SecureCredentialBackendException;
import cn.inkforge.cli.runtime.CliApplication;
import cn.inkforge.cli.runtime.CliDependencies;
import cn.inkforge.cli.transport.CoreApiClient;
import java.io.Console;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Path;
import java.util.Map;
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.node.ObjectNode;

/** InkForge Java CLI 可执行入口。 */
public final class InkForgeCli {

    private InkForgeCli() {}

    public static void main(String[] arguments) {
        int exitCode = run(
                arguments,
                System.in,
                System.out,
                System.err,
                System.getenv(),
                System.getProperty("os.name"),
                System.getProperty("user.home"),
                System.console());
        System.exit(exitCode);
    }

    static int run(
            String[] arguments,
            InputStream stdin,
            OutputStream stdout,
            OutputStream stderr,
            Map<String, String> environment,
            String operatingSystem,
            String userHome,
            Console console) {
        JsonMapper json = JsonMapper.builder().build();
        CredentialStore credentials;
        try {
            credentials = PlatformCredentialStores.create(operatingSystem);
        } catch (SecureCredentialBackendException exception) {
            ObjectNode error = json.createObjectNode();
            error.put("ok", false);
            error.put("command", arguments.length == 0 ? "" : arguments[0]);
            ObjectNode detail = error.putObject("error");
            detail.put("code", "SECURE_CREDENTIAL_BACKEND_REQUIRED");
            detail.put("message", exception.getMessage());
            try {
                stdout.write(json.writeValueAsBytes(error));
                stdout.write('\n');
                stdout.flush();
            } catch (java.io.IOException ignored) {
                // 输出失败时仍返回安全后端错误码。
            }
            return 3;
        }
        Path configPath = JsonConfigStore.defaultPath(environment, userHome);
        CliDependencies dependencies = new CliDependencies(
                (origin, token) -> new CoreApiClient(origin, token, json),
                new JsonConfigStore(configPath, json),
                credentials,
                prompt -> console == null ? new char[0] : console.readPassword("%s", prompt),
                () -> console != null,
                json);
        return CliApplication.createDefault(dependencies)
                .run(ListSupport.copy(arguments), stdin, stdout, stderr);
    }

    private static final class ListSupport {
        private static java.util.List<String> copy(String[] values) {
            return java.util.List.of(values.clone());
        }
    }
}
