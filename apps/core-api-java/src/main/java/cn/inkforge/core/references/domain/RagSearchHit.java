package cn.inkforge.core.references.domain;

import java.math.BigDecimal;

/** pgvector 余弦检索结果。 */
public record RagSearchHit(
        String title, String sourceId, int chunkIndex, BigDecimal score, String text) {}
