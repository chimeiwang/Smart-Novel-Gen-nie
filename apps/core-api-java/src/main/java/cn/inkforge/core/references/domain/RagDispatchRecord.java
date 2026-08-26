package cn.inkforge.core.references.domain;

import java.time.OffsetDateTime;

/** 后台索引投递器领取的当前代次。 */
public record RagDispatchRecord(
        String userId,
        String novelId,
        String referenceId,
        String contentHash,
        OffsetDateTime generation) {}
