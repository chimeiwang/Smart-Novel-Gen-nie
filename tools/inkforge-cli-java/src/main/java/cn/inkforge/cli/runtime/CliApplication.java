package cn.inkforge.cli.runtime;

import cn.inkforge.cli.config.ProfileConfig;
import cn.inkforge.cli.commands.LongReadCommands;
import cn.inkforge.cli.commands.ShortCommands;
import cn.inkforge.cli.commands.VideoCommands;
import cn.inkforge.cli.registry.CommandCatalog;
import cn.inkforge.cli.registry.CommandSpec;
import cn.inkforge.cli.registry.CommandSpec.OutputMode;
import cn.inkforge.cli.transport.CoreApi;
import cn.inkforge.cli.transport.CoreApiException;
import cn.inkforge.cli.transport.CoreTransportException;
import cn.inkforge.cli.transport.AtomicFiles;
import cn.inkforge.cli.transport.FileDescriptor;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.TreeSet;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

/** 顶层运行时只负责输入、身份、分派、输出和错误边界。 */
public final class CliApplication {

    private final CommandCatalog catalog;
    private final Map<String, CommandHandler> handlers;
    private final CliDependencies dependencies;

    public CliApplication(
            CommandCatalog catalog,
            Map<String, CommandHandler> handlers,
            CliDependencies dependencies) {
        this.catalog = catalog;
        this.handlers = Map.copyOf(handlers);
        this.dependencies = dependencies;
    }

    public static CliApplication createDefault(CliDependencies dependencies) {
        try (InputStream source = CliApplication.class
                .getResourceAsStream("/cli-contracts/command-registry.json")) {
            CommandCatalog catalog = CommandCatalog.load(source, dependencies.json());
            Map<String, CommandHandler> handlers = new LinkedHashMap<>();
            handlers.put("auth.login", AuthCommands::login);
            handlers.put("auth.logout", AuthCommands::logout);
            handlers.put("auth.whoami", AuthCommands::whoami);
            ShortCommands.register(handlers);
            LongReadCommands.register(handlers);
            VideoCommands.register(handlers);
            requireCompleteHandlers(catalog, handlers);
            return new CliApplication(catalog, handlers, dependencies);
        } catch (IOException exception) {
            throw new IllegalStateException("CLI 命令基线加载失败", exception);
        }
    }

    private static void requireCompleteHandlers(
            CommandCatalog catalog, Map<String, CommandHandler> handlers) {
        TreeSet<String> missing = new TreeSet<>(catalog.specs().keySet());
        missing.removeAll(handlers.keySet());
        TreeSet<String> unexpected = new TreeSet<>(handlers.keySet());
        unexpected.removeAll(catalog.specs().keySet());
        if (!missing.isEmpty() || !unexpected.isEmpty()) {
            throw new IllegalStateException(
                    "Java CLI 命令注册与基线不一致；缺失="
                            + String.join(",", missing)
                            + "；多余="
                            + String.join(",", unexpected));
        }
    }

    public int run(
            List<String> arguments,
            InputStream stdin,
            OutputStream stdout,
            OutputStream stderr) {
        String command = arguments.isEmpty() ? "" : arguments.getFirst();
        CommandSpec spec = null;
        try {
            if (command.isEmpty()) {
                throw new CliInputException("COMMAND_REQUIRED", "必须提供命令");
            }
            try {
                spec = catalog.require(command);
            } catch (IllegalArgumentException exception) {
                throw new CliInputException("UNKNOWN_COMMAND", "未知命令 " + command);
            }
            CommandHandler handler = handlers.get(command);
            if (handler == null) {
                throw new CliInputException(
                        "COMMAND_NOT_IMPLEMENTED", "Java CLI 尚未实现命令 " + command);
            }
            Prepared prepared = prepare(
                    spec, arguments.subList(1, arguments.size()), stdin);
            CommandResult result = handler.handle(prepared.context(), prepared.payload());
            if (result instanceof CommandResult.JsonlResult jsonlResult) {
                if (spec.outputMode() != OutputMode.JSONL) {
                    throw new IllegalStateException("JSON 命令返回了 JSONL 流");
                }
                return jsonlResult.producer().produce(frame -> write(stdout, frame));
            }
            if (spec.outputMode() != OutputMode.JSON
                    || !(result instanceof CommandResult.JsonResult jsonResult)) {
                throw new IllegalStateException("命令输出模式与处理器结果不匹配");
            }
            JsonNode data = applyFileOutput(spec, prepared.payload(), jsonResult.data());
            write(stdout, success(command, data));
            return 0;
        } catch (CliInputException exception) {
            write(stdout, error(command, exception.code(), exception.getMessage(), null, null));
            return exitCode(spec, exception);
        } catch (CoreApiException exception) {
            write(stdout, error(
                    command,
                    exception.code(),
                    exception.publicMessage(),
                    exception.details(),
                    exception.requestId()));
            return exitCode(spec, exception);
        } catch (CoreTransportException exception) {
            if (spec != null && spec.name().startsWith("long.")) {
                write(stdout, error(
                        command,
                        "CORE_TRANSPORT_ERROR",
                        "Core API 连接失败",
                        null,
                        null));
                return 5;
            }
            writeUnexpectedStderr(stderr);
            write(stdout, error(
                    command,
                    "UNEXPECTED_ERROR",
                    "CLI 遇到未预期错误",
                    null,
                    null));
            return 1;
        } catch (LocalFileException exception) {
            write(stdout, error(command, "LOCAL_FILE_ERROR", exception.getMessage(), null, null));
            return 6;
        } catch (Exception exception) {
            writeUnexpectedStderr(stderr);
            write(stdout, error(
                    command,
                    "UNEXPECTED_ERROR",
                    "CLI 遇到未预期错误",
                    null,
                    null));
            return 1;
        }
    }

    private static void writeUnexpectedStderr(OutputStream stderr) {
        try {
            stderr.write("InkForge CLI 遇到未预期错误。\n".getBytes(StandardCharsets.UTF_8));
            stderr.flush();
        } catch (IOException ignored) {
            // stderr 失败时仍尝试输出稳定 JSON 错误。
        }
    }

    private Prepared prepare(
            CommandSpec spec, List<String> commandArguments, InputStream stdin) throws IOException {
        if (spec.inputMode() == CommandSpec.InputMode.ARGV_TTY) {
            return new Prepared(
                    new CommandContext(
                            spec,
                            List.copyOf(commandArguments),
                            dependencies,
                            null,
                            null,
                            null),
                    dependencies.json().createObjectNode());
        }
        if (!commandArguments.isEmpty()) {
            throw new CliInputException("INVALID_ARGUMENTS", "非登录命令不接受命令行参数");
        }
        ObjectNode payload = readPayload(stdin, dependencies.json());
        CoreApi api = null;
        String profile = null;
        String origin = null;
        if (spec.requiresIdentity()) {
            profile = profile(payload);
            Optional<ProfileConfig> config = dependencies.configStore().get(profile);
            if (config.isEmpty()) {
                throw new CliInputException(
                        "AUTH_REQUIRED", "尚未登录，请在真实终端执行 auth.login", 3);
            }
            origin = config.get().origin();
            Optional<String> token = dependencies.credentialStore().get(profile, origin);
            if (token.isEmpty()) {
                throw new CliInputException(
                        "AUTH_REQUIRED", "安全凭据中没有有效会话，请在真实终端重新登录", 3);
            }
            api = dependencies.apiFactory().create(origin, token.get());
        }
        if (spec.requiresClientRequestId()) requireClientRequestId(payload);
        return new Prepared(
                new CommandContext(
                        spec,
                        List.of(),
                        dependencies,
                        api,
                        profile,
                        origin),
                payload);
    }

    private static ObjectNode readPayload(InputStream input, ObjectMapper json) throws IOException {
        byte[] bytes = input.readAllBytes();
        String raw;
        try {
            raw = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(bytes))
                    .toString();
        } catch (CharacterCodingException exception) {
            throw new CliInputException("INVALID_JSON", "stdin 不是有效的单个 JSON 对象");
        }
        if (raw.startsWith("\ufeff")) raw = raw.substring(1);
        if (raw.isBlank()) {
            throw new CliInputException("JSON_REQUIRED", "stdin 必须包含一个 UTF-8 JSON 对象");
        }
        JsonNode parsed;
        try {
            parsed = json.readTree(raw);
        } catch (RuntimeException exception) {
            throw new CliInputException("INVALID_JSON", "stdin 不是有效的单个 JSON 对象");
        }
        if (parsed == null || !parsed.isObject()) {
            throw new CliInputException("JSON_OBJECT_REQUIRED", "stdin 顶层必须是 JSON 对象");
        }
        return (ObjectNode) parsed;
    }

    private static String profile(ObjectNode payload) {
        JsonNode value = payload.get("profile");
        if (value == null) return "default";
        if (!value.isTextual() || value.textValue().isEmpty()) {
            throw new CliInputException("INVALID_PROFILE", "profile 必须是非空字符串");
        }
        return value.textValue();
    }

    private static void requireClientRequestId(ObjectNode payload) {
        JsonNode value = payload.get("clientRequestId");
        if (value == null || !value.isTextual() || value.textValue().length() < 16) {
            throw new CliInputException(
                    "CLIENT_REQUEST_ID_REQUIRED",
                    "写请求必须由调用方提供长度至少 16 的稳定 clientRequestId");
        }
    }

    private ObjectNode success(String command, JsonNode data) {
        ObjectNode result = dependencies.json().createObjectNode();
        result.put("ok", true);
        result.put("command", command);
        result.set("data", data);
        return result;
    }

    private JsonNode applyFileOutput(
            CommandSpec spec, ObjectNode payload, JsonNode data) {
        if (!spec.name().startsWith("long.")
                || spec.fileOutput().kind() == CommandSpec.FileOutputKind.NONE) {
            return data;
        }
        JsonNode output = payload.get("outputFile");
        if (output == null || output.isNull()) return data;
        if (!output.isTextual() || output.textValue().isEmpty()) {
            throw new CliInputException("INVALID_OUTPUT_FILE", "outputFile 必须是非空字符串");
        }
        Path target = Path.of(output.textValue());
        try {
            if (spec.fileOutput().kind() == CommandSpec.FileOutputKind.DATA_JSON) {
                byte[] bytes = StableJson.pretty(dependencies.json(), data)
                        .getBytes(StandardCharsets.UTF_8);
                FileDescriptor descriptor = AtomicFiles.write(
                        target,
                        new ByteArrayInputStream(bytes),
                        "application/json; charset=utf-8");
                ObjectNode result = dependencies.json().createObjectNode();
                result.set("resultFile", descriptor(descriptor));
                return result;
            }
            String field = spec.fileOutput().field();
            if (data == null || !data.isObject() || field == null) {
                throw new cn.inkforge.cli.transport.CoreResponseContractException(
                        "远端响应不是可提取主文本的 JSON 对象");
            }
            JsonNode content = data.get(field);
            if (content == null || !content.isTextual()) {
                throw new cn.inkforge.cli.transport.CoreResponseContractException(
                        "响应缺少文本字段：" + field);
            }
            FileDescriptor descriptor = AtomicFiles.write(
                    target,
                    new ByteArrayInputStream(content.textValue().getBytes(StandardCharsets.UTF_8)),
                    spec.fileOutput().mediaType());
            ObjectNode transformed = ((ObjectNode) data).deepCopy();
            transformed.remove(field);
            transformed.set(field + "File", descriptor(descriptor));
            return transformed;
        } catch (IOException exception) {
            throw new LocalFileException("输出文件写入失败", exception);
        }
    }

    private ObjectNode descriptor(FileDescriptor descriptor) {
        ObjectNode result = dependencies.json().createObjectNode();
        result.put("path", descriptor.path());
        result.put("bytes", descriptor.bytes());
        result.put("sha256", descriptor.sha256());
        result.put("mediaType", descriptor.mediaType());
        return result;
    }

    private ObjectNode error(
            String command,
            String code,
            String message,
            JsonNode details,
            String requestId) {
        ObjectNode error = dependencies.json().createObjectNode();
        error.put("code", code);
        error.put("message", message);
        if (details != null) error.set("details", details);
        if (requestId != null) error.put("requestId", requestId);
        ObjectNode result = dependencies.json().createObjectNode();
        result.put("ok", false);
        result.put("command", command);
        result.set("error", error);
        return result;
    }

    private void write(OutputStream output, JsonNode value) {
        try {
            output.write(dependencies.json().writeValueAsBytes(value));
            output.write('\n');
            output.flush();
        } catch (IOException exception) {
            throw new IllegalStateException("CLI 输出失败", exception);
        }
    }

    private static int exitCode(CommandSpec spec, Exception error) {
        boolean longCommand = spec != null && spec.name().startsWith("long.");
        if (error instanceof CliInputException input) {
            return longCommand && input.exitCode() != 3 ? 2 : input.exitCode();
        }
        if (error instanceof CoreApiException api) {
            if (!longCommand) return api.statusCode() == 401 ? 3 : api.statusCode() == 409 ? 4 : 5;
            if (api.statusCode() == 422) return 2;
            if (api.statusCode() == 401) return 3;
            if (api.statusCode() == 409) return 4;
            return 5;
        }
        return 1;
    }

    private record Prepared(CommandContext context, ObjectNode payload) {}
}
