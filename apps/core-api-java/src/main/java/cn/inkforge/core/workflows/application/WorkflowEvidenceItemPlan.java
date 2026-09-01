package cn.inkforge.core.workflows.application;

import java.time.OffsetDateTime;
import java.util.Map;

/** 创建 Run 时由业务域冻结的一项完整证据；text/json 必须且只能提供一种。 */
public record WorkflowEvidenceItemPlan(
        String resourceType,
        String resourceId,
        boolean exists,
        Integer resourceRevision,
        OffsetDateTime resourceUpdatedAt,
        String contentText,
        Object contentJson,
        Integer rangeStartCodePoint,
        Integer rangeEndCodePoint,
        Map<String, Object> metadata) {

    public WorkflowEvidenceItemPlan {
        if (resourceType == null || resourceType.isBlank()) {
            throw new IllegalArgumentException("证据资源类型不能为空");
        }
        if (resourceId == null || resourceId.isBlank()) {
            throw new IllegalArgumentException("证据资源 ID 不能为空");
        }
        metadata = metadata == null ? Map.of() : WorkflowJsonValues.freezeMap(metadata);
        if (!exists) {
            if (resourceRevision != null
                    || resourceUpdatedAt != null
                    || contentText != null
                    || contentJson != null
                    || rangeStartCodePoint != null
                    || rangeEndCodePoint != null) {
                throw new IllegalArgumentException("不存在的证据不能夹带版本、内容或范围");
            }
        } else {
            contentJson = WorkflowJsonValues.freeze(contentJson);
            if ((contentText == null) == (contentJson == null)) {
                throw new IllegalArgumentException("存在的证据必须且只能包含 text 或 JSON");
            }
            if ((rangeStartCodePoint == null) != (rangeEndCodePoint == null)) {
                throw new IllegalArgumentException("证据码点范围必须成对提供");
            }
            if (rangeStartCodePoint != null
                    && (rangeStartCodePoint < 0 || rangeEndCodePoint <= rangeStartCodePoint)) {
                throw new IllegalArgumentException("证据码点范围无效");
            }
            if (resourceRevision != null && resourceRevision < 1) {
                throw new IllegalArgumentException("证据资源 revision 必须为正数");
            }
        }
    }
}
