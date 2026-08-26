package cn.inkforge.core.references.domain;

import java.time.OffsetDateTime;

/** 确定性创建结果及对应的索引代次。 */
public record ReferenceCreateResult(
        ReferenceSnapshot reference, boolean effective, OffsetDateTime indexGeneration) {}
