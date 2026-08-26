package cn.inkforge.cli.commands;

import cn.inkforge.cli.runtime.CliInputException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeSet;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** 命令层共享的本地字段、类型和路径校验；Core 仍是业务 DTO 权威。 */
public final class Payloads {

    private Payloads() {}

    public static String requireString(ObjectNode payload, String name) {
        JsonNode value = payload.get(name);
        if (value == null || !value.isTextual() || value.textValue().isEmpty()) {
            throw new CliInputException("FIELD_REQUIRED", "缺少非空字符串字段 " + name);
        }
        return value.textValue();
    }

    /** 中短篇 CLI 的历史错误文案没有“非空”二字，迁移时必须保持。 */
    public static String requireShortString(ObjectNode payload, String name) {
        JsonNode value = payload.get(name);
        if (value == null || !value.isTextual() || value.textValue().isEmpty()) {
            throw new CliInputException("FIELD_REQUIRED", "缺少字符串字段 " + name);
        }
        return value.textValue();
    }

    public static void validateRead(
            ObjectNode payload,
            List<String> required,
            List<String> optional,
            boolean allowOutputFile) {
        TreeSet<String> allowed = new TreeSet<>(required);
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
        required.forEach(name -> requireString(payload, name));
    }

    public static void validateRead(
            ObjectNode payload, String[] required, String[] optional) {
        validateRead(payload, Arrays.asList(required), Arrays.asList(optional), true);
    }

    public static Map<String, List<String>> query(ObjectNode payload, String... names) {
        LinkedHashMap<String, List<String>> result = new LinkedHashMap<>();
        for (String name : names) {
            JsonNode value = payload.get(name);
            if (value == null) continue;
            if (value.isArray()) {
                List<String> items = new ArrayList<>();
                value.forEach(item -> items.add(queryValue(item)));
                result.put(name, List.copyOf(items));
            } else {
                result.put(name, List.of(queryValue(value)));
            }
        }
        return result;
    }

    public static String segment(String value) {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        StringBuilder encoded = new StringBuilder(bytes.length);
        for (byte raw : bytes) {
            int item = raw & 0xff;
            if (item >= 'A' && item <= 'Z'
                    || item >= 'a' && item <= 'z'
                    || item >= '0' && item <= '9'
                    || item == '-'
                    || item == '.'
                    || item == '_'
                    || item == '~') {
                encoded.append((char) item);
            } else {
                encoded.append('%');
                encoded.append(Character.toUpperCase(Character.forDigit(item >>> 4, 16)));
                encoded.append(Character.toUpperCase(Character.forDigit(item & 0x0f, 16)));
            }
        }
        return encoded.toString();
    }

    private static String queryValue(JsonNode value) {
        if (value == null || value.isNull()) return "";
        if (value.isValueNode()) return value.asText();
        throw new CliInputException("INVALID_QUERY_FIELD", "查询参数必须是标量或标量数组");
    }
}
