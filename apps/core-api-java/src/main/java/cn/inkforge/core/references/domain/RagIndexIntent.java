package cn.inkforge.core.references.domain;

import java.time.OffsetDateTime;

/** 已耐久保存、可安全重复投递的 RAG 索引意图。 */
public record RagIndexIntent(String contentHash, OffsetDateTime indexGeneration) {}
