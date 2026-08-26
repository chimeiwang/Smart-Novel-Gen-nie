package cn.inkforge.core.platform.db;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.List;
import java.util.Objects;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

/**
 * 已冻结 PostgreSQL 结构契约。
 *
 * <p>指纹算法必须与 Python Core 的 {@code canonical_fingerprint()} 完全一致，确保迁移期间两套实现判断的是同一份数据库结构，
 * 而不是各自维护一份近似定义。
 */
public final class SchemaContract {

    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();
    private static final List<String> NON_STRUCTURAL_ROOT_FIELDS = List.of("fingerprint", "source");

    private final JsonNode document;
    private final String fingerprint;

    private SchemaContract(JsonNode document, String fingerprint) {
        this.document = document;
        this.fingerprint = fingerprint;
    }

    /** 加载契约副本，并拒绝内容与内嵌指纹不一致的文件。 */
    public static SchemaContract load(JsonNode source) {
        Objects.requireNonNull(source, "数据库结构契约不能为空");
        if (!source.isObject()) {
            throw new IllegalArgumentException("数据库结构契约顶层必须是对象");
        }

        ObjectNode document = source.deepCopy().asObject();
        String expected = document.path("fingerprint").asString(null);
        String actual = canonicalFingerprint(document);
        if (expected == null || !expected.equals(actual)) {
            throw new IllegalArgumentException("数据库结构契约指纹不自洽");
        }
        return new SchemaContract(document, actual);
    }

    /** 返回与 Python {@code json.dumps(sort_keys=True, separators=(",", ":"))} 一致的 SHA-256。 */
    static String canonicalFingerprint(JsonNode source) {
        ObjectNode structuralDocument = source.deepCopy().asObject();
        structuralDocument.remove(NON_STRUCTURAL_ROOT_FIELDS);
        byte[] canonical = canonicalJson(structuralDocument).getBytes(StandardCharsets.UTF_8);
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(canonical));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("当前 JVM 不支持 SHA-256", exception);
        }
    }

    public String fingerprint() {
        return fingerprint;
    }

    /** 防止调用方修改已经校验过的契约。 */
    public JsonNode document() {
        return document.deepCopy();
    }

    private static String canonicalJson(JsonNode node) {
        if (node.isObject()) {
            StringBuilder builder = new StringBuilder("{");
            boolean first = true;
            for (String propertyName : node.propertyNames().stream().sorted().toList()) {
                if (!first) {
                    builder.append(',');
                }
                first = false;
                builder.append(OBJECT_MAPPER.writeValueAsString(propertyName));
                builder.append(':');
                builder.append(canonicalJson(node.get(propertyName)));
            }
            return builder.append('}').toString();
        }
        if (node.isArray()) {
            StringBuilder builder = new StringBuilder("[");
            boolean first = true;
            for (JsonNode child : node) {
                if (!first) {
                    builder.append(',');
                }
                first = false;
                builder.append(canonicalJson(child));
            }
            return builder.append(']').toString();
        }
        if (node.isString()) {
            return OBJECT_MAPPER.writeValueAsString(node.asString());
        }
        return node.toString();
    }
}
