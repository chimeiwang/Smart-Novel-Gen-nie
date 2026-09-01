package cn.inkforge.core.workflows.protocol;

import java.math.BigDecimal;
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import tools.jackson.databind.ObjectMapper;

/** `inkforge-canonical-json/1` 的 Java 实现；用于 V2 执行协议全部哈希材料。 */
public final class ExecutionCanonicalJson {

    public static final String ALGORITHM = "inkforge-canonical-json/1";

    private static final ObjectMapper JSON = new ObjectMapper();
    private static final Comparator<String> UNICODE_CODE_POINT_ORDER =
            ExecutionCanonicalJson::compareCodePoints;

    private ExecutionCanonicalJson() {}

    public static byte[] bytes(Object value) {
        StringBuilder output = new StringBuilder();
        append(value, output);
        return output.toString().getBytes(StandardCharsets.UTF_8);
    }

    public static String sha256(Object value) {
        try {
            return HexFormat.of()
                    .formatHex(MessageDigest.getInstance("SHA-256").digest(bytes(value)));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("JVM 缺少 SHA-256", exception);
        }
    }

    private static void append(Object value, StringBuilder output) {
        if (value == null) {
            output.append("null");
        } else if (value instanceof Boolean bool) {
            output.append(bool ? "true" : "false");
        } else if (value instanceof String text) {
            appendString(text, output);
        } else if (value instanceof Number number) {
            output.append(canonicalNumber(number));
        } else if (value instanceof List<?> values) {
            appendList(values, output);
        } else if (value instanceof Map<?, ?> values) {
            appendMap(values, output);
        } else {
            throw new IllegalArgumentException(
                    "执行哈希不支持类型：" + value.getClass().getSimpleName());
        }
    }

    private static void appendString(String value, StringBuilder output) {
        for (int index = 0; index < value.length(); index++) {
            char character = value.charAt(index);
            if (Character.isHighSurrogate(character)) {
                if (index + 1 >= value.length()
                        || !Character.isLowSurrogate(value.charAt(index + 1))) {
                    throw new IllegalArgumentException("执行哈希不允许未配对的 Unicode 代理字符");
                }
                index++;
            } else if (Character.isLowSurrogate(character)) {
                throw new IllegalArgumentException("执行哈希不允许未配对的 Unicode 代理字符");
            }
        }
        output.append(JSON.writeValueAsString(value));
    }

    private static String canonicalNumber(Number value) {
        if (value instanceof Byte
                || value instanceof Short
                || value instanceof Integer
                || value instanceof Long
                || value instanceof BigInteger) {
            return value.toString();
        }
        BigDecimal decimal;
        if (value instanceof BigDecimal exact) {
            decimal = exact;
        } else if (value instanceof Double number) {
            if (!Double.isFinite(number)) throw nonFinite();
            decimal = BigDecimal.valueOf(number);
        } else if (value instanceof Float number) {
            if (!Float.isFinite(number)) throw nonFinite();
            decimal = new BigDecimal(Float.toString(number));
        } else {
            throw new IllegalArgumentException(
                    "执行哈希不支持数值类型：" + value.getClass().getSimpleName());
        }
        if (decimal.signum() == 0) return "0";
        return decimal.stripTrailingZeros().toPlainString();
    }

    private static void appendList(List<?> values, StringBuilder output) {
        output.append('[');
        for (int index = 0; index < values.size(); index++) {
            if (index > 0) output.append(',');
            append(values.get(index), output);
        }
        output.append(']');
    }

    private static void appendMap(Map<?, ?> values, StringBuilder output) {
        List<String> keys = new ArrayList<>(values.size());
        for (Object key : values.keySet()) {
            if (!(key instanceof String text)) {
                throw new IllegalArgumentException("执行哈希 JSON 对象 key 必须是字符串");
            }
            keys.add(text);
        }
        keys.sort(UNICODE_CODE_POINT_ORDER);

        output.append('{');
        for (int index = 0; index < keys.size(); index++) {
            if (index > 0) output.append(',');
            String key = keys.get(index);
            appendString(key, output);
            output.append(':');
            append(values.get(key), output);
        }
        output.append('}');
    }

    private static int compareCodePoints(String left, String right) {
        int leftIndex = 0;
        int rightIndex = 0;
        while (leftIndex < left.length() && rightIndex < right.length()) {
            int leftCodePoint = left.codePointAt(leftIndex);
            int rightCodePoint = right.codePointAt(rightIndex);
            if (leftCodePoint != rightCodePoint) {
                return Integer.compare(leftCodePoint, rightCodePoint);
            }
            leftIndex += Character.charCount(leftCodePoint);
            rightIndex += Character.charCount(rightCodePoint);
        }
        return Integer.compare(left.length() - leftIndex, right.length() - rightIndex);
    }

    private static IllegalArgumentException nonFinite() {
        return new IllegalArgumentException("执行哈希不允许 NaN 或 Infinity");
    }
}
