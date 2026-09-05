package cn.inkforge.core.workflows.catalog;

import java.io.IOException;
import java.io.InputStream;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** 只供跨 Registry 升级 PostgreSQL 测试使用的内存契约夹具。 */
public final class ExecutionRegistryFixtures {

    private static final ObjectMapper JSON = new ObjectMapper();

    private ExecutionRegistryFixtures() {}

    public static ExecutionRegistry selectionOperationDownlined(
            ExecutionRegistry.Environment environment) {
        return modifiedSelectionOperation(environment, operation -> operation.put("v2Enabled", false));
    }

    public static ExecutionRegistry selectionOperationWithLane(
            ExecutionRegistry.Environment environment, String lane) {
        return modifiedSelectionOperation(environment, operation -> operation.put("lane", lane));
    }

    /** 只在内存启用一致性终检，仍要求当前真实执行资产及一次纠正依赖完整。 */
    public static ExecutionRegistry qualityOperationEnabled(ExecutionRegistry.Environment environment) {
        return modifiedOperation(environment, "quality.consistency", operation -> operation.put("v2Enabled", true));
    }

    private static ExecutionRegistry modifiedSelectionOperation(
            ExecutionRegistry.Environment environment,
            Consumer<Map<String, Object>> modification) {
        return modifiedOperation(environment, "long_serial.rewrite_chapter_selection", modification);
    }

    /** 只在内存打开指定结构化操作，完整复用当前真实 Profile/Prompt/Schema/预算。 */
    public static ExecutionRegistry structuredOperationEnabled(ExecutionRegistry.Environment environment, String key) {
        return structuredOperationEnabled(environment, key, false);
    }

    public static ExecutionRegistry structuredOperationEnabled(ExecutionRegistry.Environment environment, String key,
            boolean legacyReviewPolicy) {
        if (!java.util.Set.of("long_serial.create_lore", "long_serial.revise_lore", "long_serial.create_outline",
                "long_serial.revise_outline", "long_serial.manage_foreshadowing").contains(key)) {
            throw new IllegalArgumentException("测试夹具只允许指定结构化操作");
        }
        return modifiedOperation(environment, key, operation -> {
            operation.put("v2Enabled", true);
            if (legacyReviewPolicy) object(operation.get("reviewPolicy")).put("mergePolicy", "review.merge_all_pass_else_author.v1");
        });
    }

    private static ExecutionRegistry modifiedOperation(ExecutionRegistry.Environment environment, String key,
            Consumer<Map<String, Object>> modification) {
        Map<String, byte[]> documents = new HashMap<>();
        Map<String, Object> manifest = readObject(read("manifest.json"));
        for (Map.Entry<String, Object> entry : manifest.entrySet()) {
            if (!(entry.getValue() instanceof Map<?, ?> raw)
                    || !(raw.get("path") instanceof String path)) {
                continue;
            }
            documents.put(path, read(path));
        }
        Map<String, Object> catalogEntry = object(manifest.get("catalog"));
        String catalogPath = (String) catalogEntry.get("path");
        Map<String, Object> catalog = readObject(documents.get(catalogPath));
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> operations =
                (List<Map<String, Object>>) catalog.get("operations");
        Map<String, Object> selected = operations.stream()
                .filter(operation -> key.equals(operation.get("key"))).findFirst()
                .orElseThrow(() -> new IllegalArgumentException("测试夹具引用未知操作"));
        modification.accept(selected);
        byte[] changedCatalog = JSON.writeValueAsBytes(catalog);
        documents.put(catalogPath, changedCatalog);
        catalogEntry.put("sha256", sha256(changedCatalog));
        documents.put("manifest.json", JSON.writeValueAsBytes(manifest));
        return ExecutionRegistry.load(documents::get, environment);
    }

    private static byte[] read(String path) {
        try (InputStream input = ExecutionRegistryFixtures.class
                .getResourceAsStream("/agent-execution/" + path)) {
            if (input == null) throw new IllegalStateException("测试契约资源不存在：" + path);
            return input.readAllBytes();
        } catch (IOException exception) {
            throw new IllegalStateException("读取测试契约资源失败", exception);
        }
    }

    private static Map<String, Object> readObject(byte[] value) {
        return JSON.readValue(value, new TypeReference<>() {});
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> object(Object value) {
        return (Map<String, Object>) value;
    }

    private static String sha256(byte[] value) {
        try {
            return HexFormat.of()
                    .formatHex(MessageDigest.getInstance("SHA-256").digest(value));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("JVM 缺少 SHA-256", exception);
        }
    }
}
