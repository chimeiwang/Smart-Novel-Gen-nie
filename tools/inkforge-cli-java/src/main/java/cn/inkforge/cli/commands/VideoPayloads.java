package cn.inkforge.cli.commands;

import cn.inkforge.cli.runtime.CliInputException;
import cn.inkforge.cli.runtime.CommandContext;
import cn.inkforge.cli.runtime.CommandResult;
import cn.inkforge.cli.runtime.LocalFileException;
import cn.inkforge.cli.transport.CoreResponseContractException;
import cn.inkforge.cli.transport.FileDescriptor;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.TreeSet;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

/** 视频 CLI 的严格输入、小文件来源与公共响应辅助。 */
final class VideoPayloads {

    private VideoPayloads() {}

    static void fields(
            ObjectNode payload,
            Set<String> required,
            Set<String> optional,
            boolean allowOutputFile) {
        Set<String> allowed = new HashSet<>(required);
        allowed.addAll(optional);
        allowed.add("profile");
        if (allowOutputFile) allowed.add("outputFile");
        TreeSet<String> unknown = new TreeSet<>();
        payload.propertyNames().forEach(name -> {
            if (!allowed.contains(name)) unknown.add(name);
        });
        if (!unknown.isEmpty()) {
            throw new CliInputException(
                    "UNEXPECTED_FIELDS",
                    "命令包含不支持的字段：" + String.join(", ", unknown));
        }
        TreeSet<String> missing = new TreeSet<>();
        required.forEach(name -> {
            if (!payload.has(name)) missing.add(name);
        });
        if (!missing.isEmpty()) {
            throw new CliInputException(
                    "FIELD_REQUIRED",
                    "命令缺少字段：" + String.join(", ", missing));
        }
    }

    static void fields(ObjectNode payload, Set<String> required) {
        fields(payload, required, Set.of(), false);
    }

    static String string(ObjectNode payload, String name) {
        return string(payload, name, 1, null);
    }

    static String string(
            ObjectNode payload, String name, int minimum, Integer maximum) {
        JsonNode value = payload.get(name);
        if (value == null || !value.isTextual() || value.textValue().trim().isEmpty()) {
            throw new CliInputException(
                    "FIELD_REQUIRED", "缺少非空字符串字段：" + name);
        }
        int length = codePoints(value.textValue());
        if (length < minimum) {
            throw new CliInputException(
                    "INVALID_FIELD", name + " 长度不能小于 " + minimum);
        }
        if (maximum != null && length > maximum) {
            throw new CliInputException(
                    "INVALID_FIELD", name + " 长度不能超过 " + maximum);
        }
        return value.textValue();
    }

    static String optionalString(ObjectNode payload, String name, Integer maximum) {
        JsonNode value = payload.get(name);
        if (value == null || value.isNull()) return null;
        if (!value.isTextual() || value.textValue().trim().isEmpty()) {
            throw new CliInputException(
                    "INVALID_FIELD", name + " 必须是非空字符串或 null");
        }
        if (maximum != null && codePoints(value.textValue()) > maximum) {
            throw new CliInputException(
                    "INVALID_FIELD", name + " 长度不能超过 " + maximum);
        }
        return value.textValue();
    }

    static String clientRequestId(ObjectNode payload) {
        String value = string(payload, "clientRequestId", 1, 128);
        int trimmedLength = codePoints(value.trim());
        if (trimmedLength < 16) {
            throw new CliInputException(
                    "CLIENT_REQUEST_ID_REQUIRED",
                    "clientRequestId 长度必须为 16 到 128 个字符");
        }
        return value;
    }

    static int integer(
            ObjectNode payload, String name, Integer minimum, Integer maximum) {
        JsonNode value = payload.get(name);
        if (value == null || !value.isIntegralNumber() || !value.canConvertToInt()) {
            throw new CliInputException("INVALID_FIELD", name + " 必须是整数");
        }
        int result = value.intValue();
        if (minimum != null && result < minimum) {
            throw new CliInputException(
                    "INVALID_FIELD", name + " 不能小于 " + minimum);
        }
        if (maximum != null && result > maximum) {
            throw new CliInputException(
                    "INVALID_FIELD", name + " 不能大于 " + maximum);
        }
        return result;
    }

    static Integer optionalInteger(ObjectNode payload, String name, Integer minimum) {
        JsonNode value = payload.get(name);
        if (value == null || value.isNull()) return null;
        return integer(payload, name, minimum, null);
    }

    static int enumInteger(
            ObjectNode payload, String name, Set<Integer> allowed, int defaultValue) {
        if (!payload.has(name)) return defaultValue;
        int value = integer(payload, name, null, null);
        if (!allowed.contains(value)) {
            throw new CliInputException("INVALID_FIELD", name + " 不是受支持的整数选项");
        }
        return value;
    }

    static String enumeration(
            ObjectNode payload,
            String name,
            Set<String> allowed,
            String defaultValue) {
        JsonNode value = payload.get(name);
        String result = value == null ? defaultValue : value.isTextual() ? value.textValue() : null;
        if (result == null || !allowed.contains(result)) {
            throw new CliInputException(
                    "INVALID_FIELD", name + " 不是受支持的选项");
        }
        return result;
    }

    static boolean optionalBoolean(ObjectNode payload, String name, boolean defaultValue) {
        JsonNode value = payload.get(name);
        if (value == null) return defaultValue;
        if (!value.isBoolean()) {
            throw new CliInputException("INVALID_FIELD", name + " 必须是布尔值");
        }
        return value.booleanValue();
    }

    static ArrayNode stringList(
            CommandContext context,
            ObjectNode payload,
            String name,
            int maximum,
            boolean unique) {
        JsonNode raw = payload.get(name);
        if (raw == null) raw = context.dependencies().json().createArrayNode();
        if (!raw.isArray()) {
            throw new CliInputException("INVALID_FIELD", name + " 必须是非空字符串数组");
        }
        if (raw.size() > maximum) {
            throw new CliInputException(
                    "INVALID_FIELD", name + " 最多包含 " + maximum + " 项");
        }
        LinkedHashSet<String> values = new LinkedHashSet<>();
        ArrayNode result = context.dependencies().json().createArrayNode();
        for (JsonNode item : raw) {
            if (!item.isTextual() || item.textValue().trim().isEmpty()) {
                throw new CliInputException(
                        "INVALID_FIELD", name + " 必须是非空字符串数组");
            }
            if (unique && !values.add(item.textValue())) {
                throw new CliInputException(
                        "INVALID_FIELD", name + " 不能包含重复项");
            }
            result.add(item.textValue());
        }
        return result;
    }

    static ObjectNode jsonSource(
            CommandContext context,
            ObjectNode payload,
            String inlineField,
            String fileField) {
        boolean inline = payload.has(inlineField);
        boolean file = payload.has(fileField);
        if (inline == file) {
            throw new CliInputException(
                    "JSON_SOURCE_REQUIRED",
                    inlineField + " 与 " + fileField + " 必须且只能提供一个");
        }
        JsonNode value;
        if (inline) {
            value = payload.get(inlineField);
        } else {
            String source = MutationPayloads.readUtf8(string(payload, fileField));
            try {
                value = context.dependencies().json().readTree(source);
            } catch (RuntimeException exception) {
                throw new LocalFileException(fileField + " 不是有效 JSON", exception);
            }
        }
        if (!(value instanceof ObjectNode object)) {
            throw new CliInputException(
                    "OBJECT_REQUIRED", inlineField + " 必须是 JSON 对象");
        }
        return object.deepCopy();
    }

    static String textSource(
            ObjectNode payload,
            String inlineField,
            String fileField,
            Integer maximum) {
        boolean inline = payload.has(inlineField);
        boolean file = payload.has(fileField);
        if (inline == file) {
            throw new CliInputException(
                    "TEXT_SOURCE_REQUIRED",
                    inlineField + " 与 " + fileField + " 必须且只能提供一个");
        }
        String value;
        if (inline) {
            JsonNode raw = payload.get(inlineField);
            if (raw == null || !raw.isTextual()) {
                throw new CliInputException(
                        "INVALID_FIELD", inlineField + " 内容不能为空");
            }
            value = raw.textValue();
        } else {
            value = MutationPayloads.readUtf8(string(payload, fileField));
        }
        if (value.trim().isEmpty()) {
            throw new CliInputException(
                    "INVALID_FIELD", inlineField + " 内容不能为空");
        }
        if (maximum != null && codePoints(value) > maximum) {
            throw new CliInputException(
                    "INVALID_FIELD", inlineField + " 长度不能超过 " + maximum);
        }
        return value;
    }

    static CommandResult request(
            CommandContext context, String method, String path, JsonNode body) {
        return CommandResult.json(context.requireApi().request(method, path, body));
    }

    static CommandResult get(CommandContext context, String path) {
        return CommandResult.json(context.requireApi().request("GET", path));
    }

    static ObjectNode object(JsonNode value, String message) {
        if (!(value instanceof ObjectNode object)) {
            throw new CoreResponseContractException(message);
        }
        return object;
    }

    static CommandResult download(
            CommandContext context,
            ObjectNode payload,
            String idField,
            String path) {
        String id = string(payload, idField);
        Path target = Path.of(string(payload, "outputFile"));
        FileDescriptor descriptor;
        try {
            descriptor = context.requireApi().download("GET", path, target);
        } catch (IOException exception) {
            throw new LocalFileException("输出文件写入失败", exception);
        }
        ObjectNode result = context.dependencies().json().createObjectNode();
        result.put(idField, id);
        ObjectNode file = result.putObject("resultFile");
        file.put("path", descriptor.path());
        file.put("bytes", descriptor.bytes());
        file.put("sha256", descriptor.sha256());
        file.put("mediaType", descriptor.mediaType());
        return CommandResult.json(result);
    }

    static Path localPath(String value) {
        if (value.startsWith("~/")) {
            return Path.of(System.getProperty("user.home"), value.substring(2));
        }
        return Path.of(value);
    }

    static String mediaType(Path path) {
        try {
            String detected = Files.probeContentType(path);
            if (detected != null) return detected;
        } catch (IOException ignored) {
            // 扩展名回退仍能提供稳定媒体类型。
        }
        String name = path.getFileName().toString().toLowerCase(java.util.Locale.ROOT);
        if (name.endsWith(".png")) return "image/png";
        if (name.endsWith(".jpg") || name.endsWith(".jpeg")) return "image/jpeg";
        if (name.endsWith(".webp")) return "image/webp";
        if (name.endsWith(".mp4")) return "video/mp4";
        if (name.endsWith(".mp3")) return "audio/mpeg";
        if (name.endsWith(".wav")) return "audio/wav";
        return "application/octet-stream";
    }

    private static int codePoints(String value) {
        return value.codePointCount(0, value.length());
    }
}
