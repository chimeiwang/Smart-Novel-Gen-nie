package cn.inkforge.core.styles.domain;

import java.time.OffsetDateTime;

/** 文风参考文件的数据库事实；filepath 只供受控存储端口使用。 */
public record StyleReferenceSnapshot(
        String id,
        String styleId,
        String filename,
        String filepath,
        int charCount,
        String status,
        String errorMessage,
        OffsetDateTime createdAt) {}
