package cn.inkforge.core.styles.infrastructure;

import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.styles.domain.PortraitSection;
import cn.inkforge.core.styles.domain.PortraitTaskSnapshot;
import java.time.LocalDateTime;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.jooq.DSLContext;
import org.jooq.Record;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** 已冻结的用户级画像 Run 身份与原公开任务投影；不复制执行状态。 */
record DurableStylePortraitRun(String id, String userId, String styleId, String mode, PortraitSection section,
        String status, String evidenceBundleId, LocalDateTime createdAt, LocalDateTime updatedAt) {
    static final String SOURCE_TYPE = "style_portrait_v2";

    static DurableStylePortraitRun load(DSLContext transaction, ObjectMapper json, String runId) {
        Record run = transaction.fetchOne("""
                SELECT id, "userId", "novelId", "chapterId", workflow, operation,
                       "sourceType", "sourceId", "targetType", "targetId", input,
                       status::text AS "runStatus", "currentEvidenceBundleId", "createdAt", "updatedAt"
                FROM public."WorkflowRun" WHERE id = ? AND "engineVersion" = 2
                """, runId);
        return run == null ? null : from(run, json);
    }

    static DurableStylePortraitRun from(Record run, ObjectMapper json) {
        if (!"style".equals(run.get("workflow", String.class))
                || !"portrait".equals(run.get("operation", String.class))
                || !SOURCE_TYPE.equals(run.get("sourceType", String.class))
                || !"style_profile".equals(run.get("targetType", String.class))
                || !Objects.equals(run.get("sourceId", String.class), run.get("targetId", String.class))
                || run.get("novelId") != null || run.get("chapterId") != null) {
            throw new IllegalArgumentException("文风画像 V2 Run 身份不匹配");
        }
        Map<String, Object> input = json.readValue(run.get("input", String.class), new TypeReference<>() {});
        if (!Set.of("mode", "section").equals(input.keySet())) {
            throw new IllegalArgumentException("文风画像 V2 Run 输入无效");
        }
        PortraitSection section = input.get("section") instanceof String value ? PortraitSection.from(value) : null;
        boolean full = "full".equals(input.get("mode")) && input.get("section") == null;
        boolean single = "section".equals(input.get("mode")) && section != null;
        if (!full && !single) throw new IllegalArgumentException("文风画像 V2 Run 范围无效");
        return new DurableStylePortraitRun(run.get("id", String.class), run.get("userId", String.class),
                run.get("sourceId", String.class), (String) input.get("mode"), section,
                run.get("runStatus", String.class), run.get("currentEvidenceBundleId", String.class),
                run.get("createdAt", LocalDateTime.class), run.get("updatedAt", LocalDateTime.class));
    }

    PortraitTaskSnapshot snapshot() {
        String publicStatus = switch (status) {
            case "pending" -> "pending";
            case "running" -> "processing";
            case "completed" -> "success";
            case "failed", "cancelled" -> "error";
            default -> throw new IllegalArgumentException("文风画像 V2 Run 不能投影该状态");
        };
        return new PortraitTaskSnapshot(id, styleId, section, publicStatus,
                "error".equals(publicStatus) ? "画像生成失败" : null,
                DatabaseTimestamp.api(createdAt), DatabaseTimestamp.api(updatedAt));
    }
}
