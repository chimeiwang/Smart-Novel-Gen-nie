package cn.inkforge.core.platform.idempotency;

import java.math.BigDecimal;
import java.math.BigInteger;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;
import tools.jackson.databind.ObjectMapper;

/** 写命令的跨语言幂等规范；输出必须与 Python Core 的 canonical JSON 完全一致。 */
public final class CommandIdempotency {

    private static final DateTimeFormatter UTC_MICROSECONDS =
            DateTimeFormatter.ofPattern("uuuu-MM-dd'T'HH:mm:ss.SSSSSS'Z'");

    private CommandIdempotency() {}

    public static String requestFingerprint(
            String commandKind,
            Map<String, Object> resourceIdentity,
            Map<String, Object> body,
            ObjectMapper json) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("commandKind", Objects.requireNonNull(commandKind));
        value.put("resourceIdentity", Objects.requireNonNull(resourceIdentity));
        value.put("body", Objects.requireNonNull(body));
        return sha256(canonicalJsonBytes(value, json));
    }

    public static byte[] canonicalJsonBytes(Object value, ObjectMapper json) {
        Objects.requireNonNull(json);
        return json.writeValueAsBytes(normalize(value));
    }

    public static long advisoryLockKey(String userId, String clientRequestId) {
        byte[] digest = digest(requireIdentity(userId, clientRequestId));
        return ByteBuffer.wrap(digest, 0, Long.BYTES).getLong();
    }

    public static String envelopedKey(String userId, String clientRequestId) {
        requireIdentity(userId, clientRequestId);
        return "v1:" + userId + ":" + clientRequestId;
    }

    public static String legacyKey(String userId, String clientRequestId) {
        requireIdentity(userId, clientRequestId);
        return userId + ":" + clientRequestId;
    }

    private static Object normalize(Object value) {
        if (value == null || value instanceof String || value instanceof Boolean) {
            return value;
        }
        if (value instanceof Byte
                || value instanceof Short
                || value instanceof Integer
                || value instanceof Long
                || value instanceof BigInteger
                || value instanceof BigDecimal) {
            return value;
        }
        if (value instanceof Double number) {
            if (!Double.isFinite(number)) throw nonFinite();
            return number;
        }
        if (value instanceof Float number) {
            if (!Float.isFinite(number)) throw nonFinite();
            return number;
        }
        if (value instanceof OffsetDateTime timestamp) {
            return UTC_MICROSECONDS.format(timestamp
                    .withOffsetSameInstant(ZoneOffset.UTC)
                    .truncatedTo(ChronoUnit.MICROS));
        }
        if (value instanceof Instant timestamp) {
            return UTC_MICROSECONDS.format(timestamp
                    .atOffset(ZoneOffset.UTC)
                    .truncatedTo(ChronoUnit.MICROS));
        }
        if (value instanceof List<?> values) {
            List<Object> normalized = new ArrayList<>(values.size());
            for (Object item : values) normalized.add(normalize(item));
            return Collections.unmodifiableList(normalized);
        }
        if (value instanceof Map<?, ?> values) {
            Map<String, Object> normalized = new TreeMap<>();
            for (Map.Entry<?, ?> entry : values.entrySet()) {
                if (!(entry.getKey() instanceof String key)) {
                    throw new IllegalArgumentException("指纹 JSON 对象 key 必须是字符串");
                }
                normalized.put(key, normalize(entry.getValue()));
            }
            return normalized;
        }
        throw new IllegalArgumentException(
                "指纹 JSON 不支持类型：" + value.getClass().getSimpleName());
    }

    private static String requireIdentity(String userId, String clientRequestId) {
        if (userId == null || userId.isEmpty() || clientRequestId == null || clientRequestId.isEmpty()) {
            throw new IllegalArgumentException("幂等身份不能为空");
        }
        return userId + '\0' + clientRequestId;
    }

    public static String sha256(byte[] value) {
        return HexFormat.of().formatHex(digest(value));
    }

    private static byte[] digest(String value) {
        return digest(value.getBytes(StandardCharsets.UTF_8));
    }

    private static byte[] digest(byte[] value) {
        try {
            return MessageDigest.getInstance("SHA-256").digest(value);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("运行环境缺少 SHA-256", exception);
        }
    }

    private static IllegalArgumentException nonFinite() {
        return new IllegalArgumentException("指纹 JSON 不允许 NaN 或 Infinity");
    }
}
