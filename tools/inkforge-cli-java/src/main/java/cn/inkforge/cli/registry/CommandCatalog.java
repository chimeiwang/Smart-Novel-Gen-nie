package cn.inkforge.cli.registry;

import java.io.IOException;
import java.io.InputStream;
import java.util.LinkedHashMap;
import java.util.Collections;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/** 按基线顺序加载并严格校验 125 个 CLI 命令。 */
public final class CommandCatalog {

    private static final Set<String> ROOT_FIELDS =
            Set.of("schemaVersion", "source", "commands");
    private static final Set<String> COMMAND_FIELDS = Set.of(
            "name",
            "pythonHandler",
            "inputMode",
            "outputMode",
            "fileOutput",
            "mutation",
            "requiresIdentity",
            "requiresClientRequestId");
    private static final Set<String> FILE_FIELDS =
            Set.of("kind", "field", "mediaType");

    private final Map<String, CommandSpec> specs;

    private CommandCatalog(Map<String, CommandSpec> specs) {
        this.specs = Collections.unmodifiableMap(new LinkedHashMap<>(specs));
    }

    public static CommandCatalog load(InputStream source, ObjectMapper json) throws IOException {
        Objects.requireNonNull(source, "CLI 命令基线不能为空");
        JsonNode root = Objects.requireNonNull(json, "JSON 编解码器不能为空").readTree(source);
        requireObject(root, "CLI 命令基线顶层必须是对象");
        requireFields(root, ROOT_FIELDS, "CLI 命令基线字段不完整");
        if (!"inkforge-cli-command-registry/1.0".equals(text(root, "schemaVersion"))) {
            throw new IllegalArgumentException("CLI 命令基线版本不受支持");
        }
        text(root, "source");
        JsonNode commands = root.get("commands");
        if (commands == null || !commands.isArray()) {
            throw new IllegalArgumentException("CLI 命令列表无效");
        }
        LinkedHashMap<String, CommandSpec> result = new LinkedHashMap<>();
        for (JsonNode command : commands) {
            CommandSpec spec = parseCommand(command);
            if (result.putIfAbsent(spec.name(), spec) != null) {
                throw new IllegalArgumentException("CLI 命令名重复：" + spec.name());
            }
        }
        if (result.isEmpty()) throw new IllegalArgumentException("CLI 命令列表不能为空");
        return new CommandCatalog(result);
    }

    public Map<String, CommandSpec> specs() {
        return specs;
    }

    public CommandSpec require(String name) {
        CommandSpec spec = specs.get(name);
        if (spec == null) throw new IllegalArgumentException("未知命令 " + name);
        return spec;
    }

    private static CommandSpec parseCommand(JsonNode value) {
        requireObject(value, "CLI 命令必须是对象");
        requireFields(value, COMMAND_FIELDS, "CLI 命令字段不完整");
        JsonNode output = value.get("fileOutput");
        requireObject(output, "CLI 文件输出声明必须是对象");
        requireFields(output, FILE_FIELDS, "CLI 文件输出字段不完整");
        CommandSpec.FileOutput fileOutput = new CommandSpec.FileOutput(
                CommandSpec.FileOutputKind.fromWire(text(output, "kind")),
                nullableText(output, "field"),
                nullableText(output, "mediaType"));
        return new CommandSpec(
                text(value, "name"),
                text(value, "pythonHandler"),
                CommandSpec.InputMode.fromWire(text(value, "inputMode")),
                CommandSpec.OutputMode.fromWire(text(value, "outputMode")),
                fileOutput,
                bool(value, "mutation"),
                bool(value, "requiresIdentity"),
                bool(value, "requiresClientRequestId"));
    }

    private static void requireObject(JsonNode value, String message) {
        if (value == null || !value.isObject()) throw new IllegalArgumentException(message);
    }

    private static void requireFields(JsonNode value, Set<String> expected, String message) {
        if (!Set.copyOf(value.propertyNames()).equals(expected)) {
            throw new IllegalArgumentException(message);
        }
    }

    private static String text(JsonNode value, String field) {
        JsonNode item = value.get(field);
        if (item == null || !item.isTextual() || item.textValue().isBlank()) {
            throw new IllegalArgumentException("CLI 命令字段 " + field + " 无效");
        }
        return item.textValue();
    }

    private static String nullableText(JsonNode value, String field) {
        JsonNode item = value.get(field);
        if (item == null || item.isNull()) return null;
        if (!item.isTextual() || item.textValue().isBlank()) {
            throw new IllegalArgumentException("CLI 命令字段 " + field + " 无效");
        }
        return item.textValue();
    }

    private static boolean bool(JsonNode value, String field) {
        JsonNode item = value.get(field);
        if (item == null || !item.isBoolean()) {
            throw new IllegalArgumentException("CLI 命令字段 " + field + " 无效");
        }
        return item.booleanValue();
    }
}
