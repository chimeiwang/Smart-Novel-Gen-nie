package cn.inkforge.core.references.domain;

/** 显式删除资料、索引文档和分块后的影响计数。 */
public record ReferenceDeleteImpact(
        String referenceId, int ragDocuments, int ragChunks) {}
