package cn.inkforge.core.styles.infrastructure;

import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.jooq.DSLContext;
import org.jooq.Record;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** 完整有序参考正文的冻结快照；不得从当前文件重新取数或把路径交给 Agent。 */
final class DurableStylePortraitEvidence {
    private DurableStylePortraitEvidence() {}

    static Map<String, Object> load(DSLContext transaction, ObjectMapper json, DurableStylePortraitRun run) {
        List<Record> rows = transaction.fetch("""
                SELECT item."resourceType", item."resourceId", item.exists, item."contentType", item."contentJson",
                       item."contentSha256", item."byteCount", item."rangeJson", bundle."policyVersion"
                FROM public."WorkflowEvidenceItem" item
                JOIN public."WorkflowEvidenceBundle" bundle ON bundle.id = item."bundleId"
                WHERE bundle.id = ? AND bundle."runId" = ? ORDER BY item.ordinal
                """, run.evidenceBundleId(), run.id());
        if (rows.size() != 1) throw new IllegalArgumentException("文风画像必须有唯一完整 Evidence");
        Record item = rows.getFirst();
        Map<String, Object> context = json.readValue(item.get("contentJson", String.class), new TypeReference<>() {});
        if (!"style_portrait_context".equals(item.get("resourceType", String.class))
                || !run.styleId().equals(item.get("resourceId", String.class)) || !Boolean.TRUE.equals(item.get("exists", Boolean.class))
                || !"json".equals(item.get("contentType", String.class)) || item.get("rangeJson") != null
                || !"evidence.style.portrait.v1".equals(item.get("policyVersion", String.class))
                || !ExecutionCanonicalJson.sha256(context).equals(item.get("contentSha256", String.class))
                || ExecutionCanonicalJson.bytes(context).length != item.get("byteCount", Long.class)) {
            throw new IllegalArgumentException("文风画像 Evidence 绑定无效");
        }
        validate(context, run.styleId(), run.mode(), run.section() == null ? null : run.section().value());
        return context;
    }

    static void validate(Map<String, Object> context, String styleId, String mode, String section) {
        if (!context.keySet().equals(Set.of("styleId", "mode", "section", "references", "originalCharCount", "sourceTextSha256"))
                || !styleId.equals(context.get("styleId")) || !mode.equals(context.get("mode"))
                || !Objects.equals(section, context.get("section"))
                || !(context.get("references") instanceof List<?> references) || references.isEmpty()) {
            throw new IllegalArgumentException("文风画像冻结上下文无效");
        }
        List<String> parts = new ArrayList<>();
        Set<String> seen = new java.util.HashSet<>();
        int total = 0;
        for (Object value : references) {
            if (!(value instanceof Map<?, ?> reference)
                    || !reference.keySet().equals(Set.of("referenceId", "filename", "charCount", "content", "contentSha256"))
                    || !(reference.get("referenceId") instanceof String id) || id.isEmpty() || !seen.add(id)
                    || !(reference.get("filename") instanceof String filename) || filename.isEmpty()
                    || !(reference.get("content") instanceof String content)
                    || !sha256(content).equals(reference.get("contentSha256"))
                    || !(reference.get("charCount") instanceof Integer count) || count < 0) {
                throw new IllegalArgumentException("文风画像参考资料冻结值无效");
            }
            total = Math.addExact(total, count);
            parts.add("参考资料：" + filename + "\n\n" + content);
        }
        if (!Integer.valueOf(total).equals(context.get("originalCharCount"))
                || !sha256(String.join("\n\n", parts)).equals(context.get("sourceTextSha256"))) {
            throw new IllegalArgumentException("文风画像完整来源计数或摘要不匹配");
        }
    }

    static String sha256(String text) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(text.getBytes(StandardCharsets.UTF_8))); }
        catch (NoSuchAlgorithmException exception) { throw new IllegalStateException(exception); }
    }
}
