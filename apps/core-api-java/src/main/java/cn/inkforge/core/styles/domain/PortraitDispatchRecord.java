package cn.inkforge.core.styles.domain;

import java.time.OffsetDateTime;

/** 后台对账领取的 pending 或陈旧 processing 画像任务。 */
public record PortraitDispatchRecord(
        String taskId,
        String styleId,
        String userId,
        PortraitSection section,
        String status,
        OffsetDateTime updatedAt) {}
