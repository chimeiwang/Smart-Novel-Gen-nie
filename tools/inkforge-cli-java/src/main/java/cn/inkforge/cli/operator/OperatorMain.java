package cn.inkforge.cli.operator;

import cn.inkforge.cli.config.ConfigStore;
import cn.inkforge.cli.config.CredentialStore;
import cn.inkforge.cli.config.JsonConfigStore;
import cn.inkforge.cli.config.PlatformCredentialStores;
import cn.inkforge.cli.config.ProfileConfig;
import cn.inkforge.cli.config.SecureCredentialBackendException;
import cn.inkforge.cli.runtime.CliApplication;
import cn.inkforge.cli.runtime.CliDependencies;
import cn.inkforge.cli.runtime.CliInputException;
import cn.inkforge.cli.transport.CoreApi;
import cn.inkforge.cli.transport.CoreOrigin;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.function.BooleanSupplier;
import java.util.function.Supplier;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.node.ObjectNode;

/** 已安装 Skill 的固定环境门面，业务行为仍由独立公共 CLI 实现。 */
public final class OperatorMain {
    static final Set<String> ALLOWED_COMMANDS = Set.of(
            "auth.login", "auth.whoami", "auth.logout", "short.list", "short.create",
            "short.pull", "short.draft.save", "short.version.preview", "short.version.submit",
            "short.version.list", "short.version.get", "short.version.diff", "short.version.adopt",
            "short.version.restore", "short.agent.start", "short.agent.watch", "long.novel.list",
            "long.novel.get", "long.chapter.list", "long.chapter.get", "long.session.list",
            "long.session.get", "long.planning.get", "long.lore.get", "long.resources.get",
            "long.outline-node.list", "long.foreshadowing.list", "long.task.list", "long.task.get",
            "long.task.watch", "long.artifact.list", "long.artifact.get", "long.quality.get",
            "long.chapter.save", "long.chapter.status", "long.chapter.progress.save", "long.agent.start",
            "long.task.resume", "long.task.cancel", "long.artifact.approve", "long.artifact.revise",
            "long.artifact.discard", "long.quality.run", "long.quality.skip", "long.quality.reset");
    private static final Set<String> OPERATIONS = Set.of("plan_chapter", "write_chapter", "review_chapter");

    private OperatorMain() {}

    public static void main(String[] arguments) {
        ObjectMapper json = JsonMapper.builder().build();
        int exit;
        try {
            Map<String, String> environment = System.getenv();
            String userHome = System.getProperty("user.home");
            var console = System.console();
            Host host = new Host(json, environment, userHome,
                    Path.of(OperatorMain.class.getProtectionDomain().getCodeSource().getLocation().toURI()),
                    Path.of(System.getProperty("java.home"), "bin", "java"),
                    () -> PlatformCredentialStores.create(System.getProperty("os.name")),
                    new JsonConfigStore(JsonConfigStore.defaultPath(environment, userHome), json),
                    (mode, origin, token) -> OperatorApiFactory.create(mode, environment, json, origin, token),
                    prompt -> console == null ? new char[0] : console.readPassword("%s", prompt),
                    () -> console != null);
            exit = run(List.of(arguments), System.in, System.out, System.err, host);
        } catch (Exception exception) {
            diagnostic(System.err, "OPERATOR_RUNTIME_INVALID", "无法启动 Java 操作员运行时");
            exit = 3;
        }
        System.exit(exit);
    }

    static int run(List<String> arguments, InputStream stdin, OutputStream stdout, OutputStream stderr, Host host) {
        String currentCommand = "";
        try {
            if (arguments.isEmpty()) throw input("OPERATOR_MODE_INVALID", "必须提供 local 或 production");
            String mode = arguments.getFirst();
            OperatorInstallation.origin(mode);
            List<String> args = new ArrayList<>(arguments.subList(1, arguments.size()));
            Path state = OperatorInstallation.defaultState(mode, host.userHome());
            String override = host.environment().get("INKFORGE_OPERATOR_STATE_ROOT");
            if (override != null && !override.isBlank()) state = Path.of(override);
            if (!args.isEmpty() && args.getFirst().equals("configure")) {
                Map<String, String> options = options(args.subList(1, args.size()),
                        Set.of("--repository-root", "--expected-username", "--state-root"));
                if (!options.containsKey("--repository-root")) {
                    throw input("INVALID_ARGUMENTS", "configure 必须提供 --repository-root");
                }
                if (options.containsKey("--state-root")) state = Path.of(options.get("--state-root"));
                OperatorInstallation.Config config = new OperatorInstallation(state, host.json()).install(
                        mode, Path.of(options.get("--repository-root")), host.runningJar(), host.javaExecutable(),
                        options.get("--expected-username"));
                stdout.write(("Java 操作员配置已写入：" + config.stateRoot().resolve("config.json")
                        + "\n来源 revision：" + config.repositoryRevision()
                        + "\n来源工作区存在未提交变更：" + config.repositoryDirty()
                        + "\n运行包 SHA-256：" + config.jarSha256() + "\n").getBytes(StandardCharsets.UTF_8));
                return 0;
            }
            if (!args.isEmpty() && args.getFirst().equals("--state-root")) {
                if (args.size() < 3) throw input("INVALID_ARGUMENTS", "--state-root 必须提供路径和命令");
                state = Path.of(args.get(1));
                args = new ArrayList<>(args.subList(2, args.size()));
            }
            if (args.equals(List.of("--help"))) {
                stdout.write("用法：<local|production> [--state-root 路径] <命令>；登录只接受 --username。\n"
                        .getBytes(StandardCharsets.UTF_8));
                return 0;
            }
            if (args.isEmpty() || !ALLOWED_COMMANDS.contains(args.getFirst())) {
                throw input("OPERATOR_COMMAND_NOT_ALLOWED", "命令不在当前 Skill 的精确允许集合中");
            }
            String command = args.getFirst();
            currentCommand = command;
            OperatorInstallation installation = new OperatorInstallation(state, host.json());
            OperatorInstallation.Config config = installation.load(mode, host.runningJar(), host.javaExecutable());
            ConfigStore configs = boundConfig(host.configs(), config);
            CliDependencies.ApiFactory api = (origin, token) -> {
                if (!config.origin().equals(CoreOrigin.validate(origin))) {
                    throw new CliInputException("ORIGIN_MISMATCH", "拒绝访问当前 Skill 以外的 origin", 3);
                }
                return host.apiFactory().create(mode, origin, token);
            };
            // 工厂延迟到配置与命令门禁之后，configure 完全不实例化凭据后端。
            CliDependencies dependencies = new CliDependencies(api, configs, host.credentials().get(),
                    prompt -> {
                        if (mode.equals("local")) api.create(config.origin(), null)
                                .request("GET", "/api/v1/health/ready");
                        return host.passwordReader().read(prompt);
                    }, host.tty(), host.json());
            CliApplication application = CliApplication.createOperator(dependencies);
            if (command.equals("auth.login")) {
                Map<String, String> options = options(args.subList(1, args.size()), Set.of("--username"));
                String username = options.getOrDefault("--username", config.expectedUsername());
                if (username == null || username.isBlank()) throw input("INVALID_ARGUMENTS", "登录必须提供 --username");
                username = username.strip();
                if (config.expectedUsername() != null && !config.expectedUsername().equals(username)) {
                    throw new CliInputException("IDENTITY_MISMATCH", "登录用户名与已绑定用户名不一致", 3);
                }
                int exit = application.run(List.of(command, "--origin", config.origin(),
                        "--profile", config.profile(), "--username", username), stdin, stdout, stderr);
                if (exit == 0 && config.expectedUsername() == null) installation.bindUsername(config, username);
                return exit;
            }
            if (args.size() != 1) throw input("INVALID_ARGUMENTS", "非登录命令不接受额外命令行参数");
            ObjectNode payload = bind(readPayload(stdin, host.json()), config, command.equals("auth.whoami"));
            if (!command.startsWith("auth.")) {
                ObjectNode identity = bind(host.json().createObjectNode(), config, true);
                ByteArrayOutputStream preflightOut = new ByteArrayOutputStream();
                ByteArrayOutputStream preflightErr = new ByteArrayOutputStream();
                int exit = application.run(List.of("auth.whoami"), bytes(identity, host.json()), preflightOut, preflightErr);
                if (exit != 0) {
                    preflightOut.writeTo(stdout);
                    preflightErr.writeTo(stderr);
                    return exit;
                }
                if (command.equals("long.agent.start")) {
                    if (payload.has("inputMode")) {
                        throw input("OPERATOR_INPUT_MODE_NOT_ALLOWED", "当前 Skill 不开放自然启动或澄清模式");
                    }
                    JsonNode operation = payload.get("operation");
                    if (operation == null || !operation.isTextual() || !OPERATIONS.contains(operation.textValue())) {
                        throw input("OPERATOR_OPERATION_NOT_ALLOWED", "当前 Skill 只允许三种已开放的长篇 operation");
                    }
                }
                if (command.equals("long.task.resume") && payload.has("inputMode")) {
                    throw input("OPERATOR_INPUT_MODE_NOT_ALLOWED", "当前 Skill 不开放自然启动或澄清模式");
                }
            }
            return application.run(List.of(command), bytes(payload, host.json()), stdout, stderr);
        } catch (CliInputException exception) {
            diagnostic(stderr, exception.code(), exception.getMessage());
            return exception.exitCode();
        } catch (SecureCredentialBackendException exception) {
            ObjectNode failure = host.json().createObjectNode();
            failure.put("ok", false);
            failure.put("command", currentCommand);
            failure.putObject("error").put("code", "SECURE_CREDENTIAL_BACKEND_REQUIRED")
                    .put("message", "操作系统安全凭据后端不可用");
            try {
                stdout.write(host.json().writeValueAsBytes(failure));
                stdout.write('\n');
                stdout.flush();
            } catch (IOException ignored) {
                // 输出不可用也不允许回退凭据后端。
            }
            return 3;
        } catch (IOException | RuntimeException exception) {
            diagnostic(stderr, "OPERATOR_RUNTIME_INVALID", "操作员配置、运行包或输入无法安全读取");
            return 3;
        }
    }

    private static ConfigStore boundConfig(ConfigStore delegate, OperatorInstallation.Config bound) {
        return new ConfigStore() {
            private void check(String profile) {
                if (!bound.profile().equals(profile)) throw new CliInputException("PROFILE_MISMATCH", "profile 与当前 Skill 不匹配", 3);
            }
            private void checkOrigin(ProfileConfig config) {
                if (!bound.origin().equals(config.origin())) throw new CliInputException("ORIGIN_MISMATCH", "已保存 profile 的 origin 与当前 Skill 不匹配", 3);
            }
            public Optional<ProfileConfig> get(String profile) {
                check(profile);
                Optional<ProfileConfig> config = delegate.get(profile);
                config.ifPresent(this::checkOrigin);
                return config;
            }
            public void save(String profile, ProfileConfig config) {
                check(profile);
                checkOrigin(config);
                delegate.save(profile, config);
            }
            public void delete(String profile) {
                get(profile);
                delegate.delete(profile);
            }
        };
    }

    private static ObjectNode bind(ObjectNode original, OperatorInstallation.Config config, boolean whoami) {
        ObjectNode payload = original.deepCopy();
        String origin = reserved(payload, "origin");
        if (origin != null) throw input("ORIGIN_MISMATCH", "调用方不能在 JSON 中指定 origin");
        String profile = reserved(payload, "profile");
        if (profile != null) {
            if (!payload.get(profile).isTextual() || !config.profile().equals(payload.get(profile).textValue())) {
                throw input("PROFILE_MISMATCH", "调用方不能覆盖固定 profile");
            }
            payload.remove(profile);
        }
        String username = reserved(payload, "expectedUsername");
        if (whoami) {
            if (config.expectedUsername() == null) throw new CliInputException("AUTH_REQUIRED", "尚未绑定用户名，请在真实终端登录", 3);
            if (username != null && (!payload.get(username).isTextual()
                    || !config.expectedUsername().equals(payload.get(username).textValue()))) {
                throw new CliInputException("IDENTITY_MISMATCH", "调用方不能覆盖预期用户名", 3);
            }
            if (username != null) payload.remove(username);
            payload.put("expectedUsername", config.expectedUsername());
        } else if (username != null) throw new CliInputException("IDENTITY_MISMATCH", "非身份命令不能携带 expectedUsername", 3);
        payload.put("profile", config.profile());
        return payload;
    }

    private static String reserved(ObjectNode payload, String name) {
        List<String> matches = payload.propertyNames().stream().filter(key -> key.equalsIgnoreCase(name)).toList();
        if (matches.size() > 1) throw input("INVALID_JSON", "JSON 包含重复的保留字段");
        return matches.isEmpty() ? null : matches.getFirst();
    }

    private static ObjectNode readPayload(InputStream stdin, ObjectMapper json) throws IOException {
        String raw;
        try {
            raw = StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(stdin.readAllBytes())).toString();
        } catch (java.nio.charset.CharacterCodingException exception) {
            throw input("INVALID_JSON", "stdin 必须是严格 UTF-8 JSON");
        }
        if (raw.startsWith("\ufeff")) raw = raw.substring(1);
        try (var parser = json.tokenStreamFactory().createParser(raw)) {
            JsonNode node = json.readTree(parser);
            if (!(node instanceof ObjectNode object) || parser.nextToken() != null) {
                throw input("INVALID_JSON", "stdin 必须是单个 JSON 对象");
            }
            return object;
        } catch (CliInputException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw input("INVALID_JSON", "stdin 必须是单个 JSON 对象");
        }
    }

    private static Map<String, String> options(List<String> args, Set<String> allowed) {
        Map<String, String> result = new HashMap<>();
        for (int index = 0; index < args.size(); index += 2) {
            String key = args.get(index);
            if (!allowed.contains(key) || index + 1 >= args.size()
                    || args.get(index + 1).isBlank() || result.putIfAbsent(key, args.get(index + 1)) != null) {
                throw input("INVALID_ARGUMENTS", "存在不受支持、重复或缺少值的命令参数");
            }
        }
        return result;
    }

    private static ByteArrayInputStream bytes(JsonNode value, ObjectMapper json) {
        return new ByteArrayInputStream(json.writeValueAsBytes(value));
    }

    private static CliInputException input(String code, String message) {
        return new CliInputException(code, message);
    }

    private static void diagnostic(OutputStream stderr, String code, String message) {
        try {
            stderr.write((code + "：" + message + "\n").getBytes(StandardCharsets.UTF_8));
            stderr.flush();
        } catch (IOException ignored) {
            // 输出不可用时仍通过退出码失败关闭。
        }
    }

    @FunctionalInterface
    interface ApiFactory {
        CoreApi create(String mode, String origin, String token);
    }

    record Host(ObjectMapper json, Map<String, String> environment, String userHome,
            Path runningJar, Path javaExecutable, Supplier<CredentialStore> credentials,
            ConfigStore configs, ApiFactory apiFactory, CliDependencies.PasswordReader passwordReader,
            BooleanSupplier tty) {}
}
