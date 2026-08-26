package cn.inkforge.core.reviews.domain;

import java.time.OffsetDateTime;

/** 创建选区草案时由数据库锁定并读出的权威来源。 */
public record SelectionSource(
        String resourceType,
        String resourceId,
        String content,
        OffsetDateTime updatedAt) {}
