package cn.inkforge.core.references.domain;

import cn.inkforge.core.platform.http.ApiException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;

/** 与旧 Core 完全一致的 RAG 容量、分块和向量边界。 */
public final class RagRules {

    public static final int MAX_CHUNK_CODE_POINTS = 1_800;
    public static final int MAX_INDEX_CHUNKS = 64;
    public static final int MAX_EMBEDDING_DIMENSION = 4_096;
    public static final int MAX_TOP_K = 20;

    private RagRules() {}

    /** 按 Unicode 码点切分，空白、换行和补充平面字符均不得丢失。 */
    public static List<String> chunks(String content) {
        if (content == null) {
            throw embeddingInvalid();
        }
        int codePointCount = content.codePointCount(0, content.length());
        if (codePointCount > MAX_CHUNK_CODE_POINTS * MAX_INDEX_CHUNKS) {
            throw capacityExceeded();
        }
        List<String> chunks = new ArrayList<>();
        int start = 0;
        while (start < content.length()) {
            int remaining = content.codePointCount(start, content.length());
            int length = Math.min(MAX_CHUNK_CODE_POINTS, remaining);
            int end = content.offsetByCodePoints(start, length);
            chunks.add(content.substring(start, end));
            start = end;
        }
        return List.copyOf(chunks);
    }

    /** 对原始 UTF-8 字节计算哈希，不做 trim、换行或 Unicode 归一化。 */
    public static String sha256(String content) {
        if (content == null) {
            throw new IllegalArgumentException("哈希内容不能为空");
        }
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(digest.digest(content.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("运行环境缺少 SHA-256", exception);
        }
    }

    /** 验证嵌入批次但不转换或截断调用方提供的数值。 */
    public static <T extends Number> List<List<T>> embeddings(List<List<T>> values) {
        if (values == null || values.isEmpty()) {
            throw embeddingInvalid();
        }
        if (values.size() > MAX_INDEX_CHUNKS) {
            throw capacityExceeded();
        }
        Integer dimension = null;
        for (List<T> vector : values) {
            if (vector == null || vector.isEmpty()) {
                throw embeddingInvalid();
            }
            if (vector.size() > MAX_EMBEDDING_DIMENSION) {
                throw capacityExceeded();
            }
            if (dimension == null) {
                dimension = vector.size();
            } else if (dimension != vector.size()) {
                throw embeddingInvalid();
            }
            for (Number value : vector) {
                if (value == null || !finite(value)) {
                    throw embeddingInvalid();
                }
            }
        }
        return values;
    }

    public static int topK(int value) {
        if (value <= 0 || value > MAX_TOP_K) {
            throw new ApiException(422, "RAG_TOP_K_INVALID", "检索结果数量必须在 1 到 20 之间");
        }
        return value;
    }

    private static boolean finite(Number value) {
        return switch (value) {
            case Double doubleValue -> Double.isFinite(doubleValue);
            case Float floatValue -> Float.isFinite(floatValue);
            default -> true;
        };
    }

    private static ApiException embeddingInvalid() {
        return new ApiException(422, "EMBEDDING_INVALID", "嵌入向量必须非空、维度一致且只包含有限数值");
    }

    private static ApiException capacityExceeded() {
        return new ApiException(413, "EMBEDDING_CAPACITY_EXCEEDED", "索引分块或嵌入向量维度超过允许上限");
    }
}
