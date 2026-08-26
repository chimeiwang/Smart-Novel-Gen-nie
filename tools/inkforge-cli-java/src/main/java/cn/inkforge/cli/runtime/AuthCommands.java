package cn.inkforge.cli.runtime;

import cn.inkforge.cli.config.ProfileConfig;
import cn.inkforge.cli.transport.CoreOrigin;
import cn.inkforge.cli.transport.LoginResult;
import java.util.Arrays;
import picocli.CommandLine;
import picocli.CommandLine.Option;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

final class AuthCommands {

    private AuthCommands() {}

    static CommandResult login(CommandContext context, ObjectNode payload) {
        LoginOptions options = new LoginOptions();
        try {
            new CommandLine(options).parseArgs(context.argv().toArray(String[]::new));
        } catch (CommandLine.ParameterException exception) {
            throw new CliInputException("INVALID_ARGUMENTS", "auth.login 参数无效");
        }
        if (!context.dependencies().stdinIsTty().getAsBoolean()) {
            throw new CliInputException(
                    "TTY_REQUIRED", "auth.login 必须由用户在真实终端中交互执行");
        }
        String origin;
        try {
            origin = CoreOrigin.validate(options.origin);
        } catch (IllegalArgumentException exception) {
            throw new CliInputException("INVALID_ARGUMENTS", exception.getMessage());
        }
        char[] password = context.dependencies().passwordReader().read("InkForge 密码：");
        if (password == null) password = new char[0];
        LoginResult result;
        try {
            result = context.dependencies()
                    .apiFactory()
                    .create(origin, null)
                    .login(options.username, new String(password));
        } finally {
            Arrays.fill(password, '\0');
        }
        context.dependencies()
                .credentialStore()
                .set(options.profile, origin, result.token());
        try {
            context.dependencies()
                    .configStore()
                    .save(options.profile, new ProfileConfig(origin, options.username));
        } catch (RuntimeException exception) {
            context.dependencies().credentialStore().delete(options.profile, origin);
            throw exception;
        }
        return CommandResult.json(result.user());
    }

    static CommandResult logout(CommandContext context, ObjectNode payload) {
        try {
            return CommandResult.json(
                    context.requireApi().request("POST", "/api/v1/auth/logout"));
        } finally {
            context.dependencies()
                    .credentialStore()
                    .delete(context.profile(), context.origin());
        }
    }

    static CommandResult whoami(CommandContext context, ObjectNode payload) {
        JsonNode response = context.requireApi().request("GET", "/api/v1/auth/me");
        JsonNode expected = payload.get("expectedUsername");
        if (expected != null && !expected.isNull()) {
            if (!expected.isTextual() || expected.textValue().isEmpty()) {
                throw new CliInputException(
                        "INVALID_EXPECTED_USERNAME", "expectedUsername 必须是非空字符串");
            }
            JsonNode actual = response == null ? null : response.get("username");
            if (actual == null
                    || !actual.isTextual()
                    || !expected.textValue().equals(actual.textValue())) {
                throw new CliInputException(
                        "IDENTITY_MISMATCH",
                        "当前登录身份与 expectedUsername 不一致",
                        3);
            }
        }
        return CommandResult.json(response);
    }

    private static final class LoginOptions {

        @Option(names = "--origin", required = true)
        private String origin;

        @Option(names = "--username", required = true)
        private String username;

        @Option(names = "--profile", defaultValue = "default")
        private String profile;
    }
}
