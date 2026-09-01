package cn.inkforge.core.workflows.protocol;

import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import java.math.BigDecimal;
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Pattern;
import java.util.regex.PatternSyntaxException;

/** 对冻结 Output Registry 的 JSON Schema 子集做 Core 侧 fail-closed 校验。 */
public final class WorkflowOutputValidator {

    private static final Set<String> SUPPORTED_KEYWORDS = Set.of(
            "$schema",
            "type",
            "additionalProperties",
            "required",
            "properties",
            "pattern",
            "enum",
            "const",
            "minLength",
            "maxLength",
            "minItems",
            "maxItems",
            "minimum",
            "maximum",
            "items",
            "anyOf",
            "allOf",
            "if",
            "then",
            "else");
    private static final Set<String> FORBIDDEN_DIAGNOSTIC_KEYS = Set.of(
            "chainofthought",
            "cot",
            "logs",
            "providerresponse",
            "rawlog",
            "rawproviderresponse",
            "reasoning",
            "reasoningcontent");

    private WorkflowOutputValidator() {}

    public static void validate(ExecutionRegistry.OutputSchema outputSchema, Object value) {
        Objects.requireNonNull(outputSchema, "输出 Schema 不能为空");
        if (!outputSchema.supported()) {
            throw new IllegalArgumentException("输出 Schema 尚未启用");
        }
        validate(outputSchema.jsonSchema(), value);
    }

    /** 校验 Run 内已经过 canonical hash 复验的不可变 Schema，不重新查询当前 Registry。 */
    public static void validate(Map<String, Object> jsonSchema, Object value) {
        Objects.requireNonNull(jsonSchema, "输出 Schema 不能为空");
        validateSchemaDefinition(jsonSchema, "$");
        if (containsForbiddenDiagnostic(value)) {
            throw new IllegalArgumentException("结构化输出包含禁止持久化的诊断或推理字段");
        }
        List<String> violations = new ArrayList<>();
        validateValue(jsonSchema, value, "$", violations);
        if (!violations.isEmpty()) {
            throw new IllegalArgumentException("结构化输出不符合冻结 Schema：" + violations.getFirst());
        }
    }

    private static void validateSchemaDefinition(Map<String, Object> schema, String path) {
        Set<String> unknown = new HashSet<>(schema.keySet());
        unknown.removeAll(SUPPORTED_KEYWORDS);
        if (!unknown.isEmpty()) {
            throw new IllegalArgumentException("输出 Schema 包含未实现关键字：" + unknown);
        }
        nestedSchemas(schema.get("properties"), path + ".properties");
        nestedSchema(schema.get("items"), path + ".items");
        nestedSchemaList(schema.get("anyOf"), path + ".anyOf");
        nestedSchemaList(schema.get("allOf"), path + ".allOf");
        nestedSchema(schema.get("if"), path + ".if");
        nestedSchema(schema.get("then"), path + ".then");
        nestedSchema(schema.get("else"), path + ".else");
        if (schema.containsKey("pattern")) {
            try {
                Pattern.compile(string(schema.get("pattern"), path + ".pattern"));
            } catch (PatternSyntaxException exception) {
                throw new IllegalArgumentException("输出 Schema pattern 无效", exception);
            }
        }
    }

    private static void nestedSchemas(Object value, String path) {
        if (value == null) return;
        Map<?, ?> properties = map(value, path);
        for (Map.Entry<?, ?> entry : properties.entrySet()) {
            if (!(entry.getKey() instanceof String key)) {
                throw new IllegalArgumentException(path + " key 必须是字符串");
            }
            validateSchemaDefinition(stringMap(entry.getValue(), path + "." + key), path + "." + key);
        }
    }

    private static void nestedSchema(Object value, String path) {
        if (value != null) validateSchemaDefinition(stringMap(value, path), path);
    }

    private static void nestedSchemaList(Object value, String path) {
        if (value == null) return;
        List<?> schemas = list(value, path);
        if (schemas.isEmpty()) throw new IllegalArgumentException(path + " 不能为空");
        for (int index = 0; index < schemas.size(); index++) {
            validateSchemaDefinition(
                    stringMap(schemas.get(index), path + "[" + index + "]"),
                    path + "[" + index + "]");
        }
    }

    private static void validateValue(
            Map<String, Object> schema, Object value, String path, List<String> violations) {
        if (schema.containsKey("anyOf")) {
            int matches = 0;
            for (Object branch : list(schema.get("anyOf"), path + ".anyOf")) {
                if (matches(stringMap(branch, path + ".anyOf"), value, path)) matches++;
            }
            if (matches == 0) violations.add(path + " 不匹配 anyOf 的任何分支");
        }
        if (schema.containsKey("allOf")) {
            for (Object branch : list(schema.get("allOf"), path + ".allOf")) {
                validateValue(stringMap(branch, path + ".allOf"), value, path, violations);
            }
        }
        if (schema.containsKey("if")) {
            Map<String, Object> condition = stringMap(schema.get("if"), path + ".if");
            Object selected = matches(condition, value, path) ? schema.get("then") : schema.get("else");
            if (selected != null) {
                validateValue(stringMap(selected, path + ".conditional"), value, path, violations);
            }
        }
        if (schema.containsKey("const") && !jsonEquals(schema.get("const"), value)) {
            violations.add(path + " 不等于 const");
        }
        if (schema.containsKey("enum")) {
            boolean found = list(schema.get("enum"), path + ".enum").stream()
                    .anyMatch(candidate -> jsonEquals(candidate, value));
            if (!found) violations.add(path + " 不属于枚举");
        }
        if (schema.containsKey("type")
                && !matchesType(string(schema.get("type"), path + ".type"), value)) {
            violations.add(path + " 类型不匹配");
            return;
        }
        if (value instanceof Map<?, ?> object) validateObject(schema, object, path, violations);
        if (value instanceof List<?> array) validateArray(schema, array, path, violations);
        if (value instanceof String text) validateString(schema, text, path, violations);
        if (value instanceof Number number) validateNumber(schema, number, path, violations);
    }

    private static void validateObject(
            Map<String, Object> schema,
            Map<?, ?> value,
            String path,
            List<String> violations) {
        Map<?, ?> properties = schema.containsKey("properties")
                ? map(schema.get("properties"), path + ".properties")
                : Map.of();
        if (schema.containsKey("required")) {
            for (Object field : list(schema.get("required"), path + ".required")) {
                String name = string(field, path + ".required");
                if (!value.containsKey(name)) violations.add(path + " 缺少字段 " + name);
            }
        }
        if (Boolean.FALSE.equals(schema.get("additionalProperties"))) {
            for (Object key : value.keySet()) {
                if (!(key instanceof String text) || !properties.containsKey(text)) {
                    violations.add(path + " 包含未知字段 " + key);
                }
            }
        }
        for (Map.Entry<?, ?> entry : value.entrySet()) {
            if (entry.getKey() instanceof String key && properties.containsKey(key)) {
                validateValue(
                        stringMap(properties.get(key), path + "." + key),
                        entry.getValue(),
                        path + "." + key,
                        violations);
            }
        }
    }

    private static void validateArray(
            Map<String, Object> schema,
            List<?> value,
            String path,
            List<String> violations) {
        if (schema.containsKey("minItems")
                && value.size() < integer(schema.get("minItems"), path + ".minItems")) {
            violations.add(path + " 项数小于下限");
        }
        if (schema.containsKey("maxItems")
                && value.size() > integer(schema.get("maxItems"), path + ".maxItems")) {
            violations.add(path + " 项数超过上限");
        }
        if (schema.containsKey("items")) {
            Map<String, Object> itemSchema = stringMap(schema.get("items"), path + ".items");
            for (int index = 0; index < value.size(); index++) {
                validateValue(itemSchema, value.get(index), path + "[" + index + "]", violations);
            }
        }
    }

    private static void validateString(
            Map<String, Object> schema,
            String value,
            String path,
            List<String> violations) {
        int length = value.codePointCount(0, value.length());
        if (schema.containsKey("minLength")
                && length < integer(schema.get("minLength"), path + ".minLength")) {
            violations.add(path + " 长度小于下限");
        }
        if (schema.containsKey("maxLength")
                && length > integer(schema.get("maxLength"), path + ".maxLength")) {
            violations.add(path + " 长度超过上限");
        }
        if (schema.containsKey("pattern")
                && !Pattern.compile(string(schema.get("pattern"), path + ".pattern"))
                        .matcher(value)
                        .find()) {
            violations.add(path + " 不匹配 pattern");
        }
    }

    private static void validateNumber(
            Map<String, Object> schema,
            Number value,
            String path,
            List<String> violations) {
        BigDecimal decimal = decimal(value, path);
        if (schema.containsKey("minimum")
                && decimal.compareTo(decimal((Number) schema.get("minimum"), path + ".minimum")) < 0) {
            violations.add(path + " 小于最小值");
        }
        if (schema.containsKey("maximum")
                && decimal.compareTo(decimal((Number) schema.get("maximum"), path + ".maximum")) > 0) {
            violations.add(path + " 大于最大值");
        }
    }

    private static boolean matches(Map<String, Object> schema, Object value, String path) {
        List<String> violations = new ArrayList<>();
        validateValue(schema, value, path, violations);
        return violations.isEmpty();
    }

    private static boolean matchesType(String type, Object value) {
        return switch (type) {
            case "null" -> value == null;
            case "object" -> value instanceof Map<?, ?>;
            case "array" -> value instanceof List<?>;
            case "string" -> value instanceof String;
            case "boolean" -> value instanceof Boolean;
            case "number" -> value instanceof Number && finite((Number) value);
            case "integer" -> value instanceof Number number && finite(number) && integerNumber(number);
            default -> throw new IllegalArgumentException("输出 Schema type 尚未实现：" + type);
        };
    }

    private static boolean containsForbiddenDiagnostic(Object value) {
        if (value instanceof Map<?, ?> map) {
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                if (entry.getKey() instanceof String key
                        && FORBIDDEN_DIAGNOSTIC_KEYS.contains(normalizedKey(key))) {
                    return true;
                }
                if (containsForbiddenDiagnostic(entry.getValue())) return true;
            }
        } else if (value instanceof List<?> list) {
            for (Object nested : list) {
                if (containsForbiddenDiagnostic(nested)) return true;
            }
        }
        return false;
    }

    private static String normalizedKey(String value) {
        return value.toLowerCase(java.util.Locale.ROOT).replace("_", "").replace("-", "");
    }

    private static boolean jsonEquals(Object left, Object right) {
        if (left instanceof Number leftNumber && right instanceof Number rightNumber) {
            return decimal(leftNumber, "enum").compareTo(decimal(rightNumber, "value")) == 0;
        }
        return Objects.equals(left, right);
    }

    private static boolean integerNumber(Number value) {
        return decimal(value, "integer").stripTrailingZeros().scale() <= 0;
    }

    private static boolean finite(Number value) {
        return !(value instanceof Double number && !Double.isFinite(number))
                && !(value instanceof Float floatNumber && !Float.isFinite(floatNumber));
    }

    private static BigDecimal decimal(Number value, String path) {
        if (!finite(value)) throw new IllegalArgumentException(path + " 不能是 NaN 或 Infinity");
        if (value instanceof BigDecimal decimal) return decimal;
        if (value instanceof BigInteger integer) return new BigDecimal(integer);
        return new BigDecimal(value.toString());
    }

    private static int integer(Object value, String path) {
        if (!(value instanceof Number number) || !integerNumber(number)) {
            throw new IllegalArgumentException(path + " 必须是整数");
        }
        return decimal(number, path).intValueExact();
    }

    private static String string(Object value, String path) {
        if (!(value instanceof String text)) throw new IllegalArgumentException(path + " 必须是字符串");
        return text;
    }

    private static List<?> list(Object value, String path) {
        if (!(value instanceof List<?> result)) throw new IllegalArgumentException(path + " 必须是数组");
        return result;
    }

    private static Map<?, ?> map(Object value, String path) {
        if (!(value instanceof Map<?, ?> result)) throw new IllegalArgumentException(path + " 必须是对象");
        return result;
    }

    private static Map<String, Object> stringMap(Object value, String path) {
        Map<?, ?> raw = map(value, path);
        java.util.LinkedHashMap<String, Object> result = new java.util.LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : raw.entrySet()) {
            if (!(entry.getKey() instanceof String key)) {
                throw new IllegalArgumentException(path + " key 必须是字符串");
            }
            result.put(key, entry.getValue());
        }
        return Map.copyOf(result);
    }
}
