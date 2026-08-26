package cn.inkforge.core.references.domain;

import java.time.OffsetDateTime;

/** 更新结果；标题变化不会把 indexRefreshRequired 置为 true。 */
public record ReferenceUpdateResult(
        ReferenceSnapshot reference,
        boolean indexRefreshRequired,
        OffsetDateTime indexGeneration) {}
