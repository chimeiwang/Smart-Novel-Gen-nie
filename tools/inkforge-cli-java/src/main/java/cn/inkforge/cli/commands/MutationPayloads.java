package cn.inkforge.cli.commands;

import cn.inkforge.cli.runtime.CliInputException;
import cn.inkforge.cli.runtime.LocalFileException;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** 长篇写命令共享的外层字段、CAS、data 与完整文件输入校验。 */
final class MutationPayloads {

    private MutationPayloads() {}

    static void requireFields(
            ObjectNode payload, Set<String> required, Set<String> optional) {
        Set<String> allowed = new HashSet<>(required);
        allowed.addAll(optional);
        allowed.add("profile");
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
                    "FIELD_REQUIRED", "命令缺少字段：" + String.join(", ", missing));
        }
    }

    static void requireFields(ObjectNode payload, Set<String> required) {
        requireFields(payload, required, Set.of());
    }

    static String requireString(ObjectNode payload, String name) {
        return requireString(payload, name, false);
    }

    static String requireString(ObjectNode payload, String name, boolean allowEmpty) {
        JsonNode value = payload.get(name);
        if (value == null
                || !value.isTextual()
                || (!allowEmpty && value.textValue().isEmpty())) {
            throw new CliInputException("FIELD_REQUIRED", "缺少字符串字段 " + name);
        }
        return value.textValue();
    }

    static String expectedUpdatedAt(ObjectNode payload, boolean nullable) {
        if (!payload.has("expectedUpdatedAt")) {
            throw new CliInputException("FIELD_REQUIRED", "缺少字段 expectedUpdatedAt");
        }
        JsonNode value = payload.get("expectedUpdatedAt");
        if (nullable && value.isNull()) return null;
        if (!value.isTextual() || value.textValue().isEmpty()) {
            throw new CliInputException(
                    "INVALID_EXPECTED_UPDATED_AT",
                    "expectedUpdatedAt 必须是非空字符串"
                            + (nullable ? "或显式 null" : ""));
        }
        return value.textValue();
    }

    static String contentSource(ObjectNode payload) {
        boolean hasText = payload.has("content");
        boolean hasFile = payload.has("contentFile");
        if (hasText == hasFile) {
            throw new CliInputException(
                    "CONTENT_SOURCE_REQUIRED", "content 与 contentFile 必须且只能提供一个");
        }
        if (hasText) return requireString(payload, "content", true);
        return readUtf8(requireString(payload, "contentFile"));
    }

    static ObjectNode data(ObjectNode payload, Set<String> allowed) {
        JsonNode value = payload.get("data");
        if (!(value instanceof ObjectNode object)) {
            throw new CliInputException("OBJECT_REQUIRED", "字段 data 必须是 JSON 对象");
        }
        TreeSet<String> unknown = new TreeSet<>();
        object.propertyNames().forEach(name -> {
            if (!allowed.contains(name)) unknown.add(name);
        });
        if (!unknown.isEmpty()) {
            throw new CliInputException(
                    "UNEXPECTED_DATA_FIELDS",
                    "data 包含不支持的字段：" + String.join(", ", unknown));
        }
        if (object.isEmpty()) {
            throw new CliInputException("DATA_REQUIRED", "data 至少包含一个业务字段");
        }
        return object.deepCopy();
    }

    static String clientRequestId(ObjectNode payload, int maximum) {
        String value = requireString(payload, "clientRequestId");
        if (value.length() < 16 || value.length() > maximum) {
            throw new CliInputException(
                    "CLIENT_REQUEST_ID_REQUIRED",
                    "clientRequestId 长度必须在 16 到 " + maximum + " 个字符之间");
        }
        return value;
    }

    static String readUtf8(String source) {
        try {
            return Files.readString(Path.of(source), StandardCharsets.UTF_8);
        } catch (IOException exception) {
            throw new LocalFileException("输入文件读取失败", exception);
        }
    }
}
