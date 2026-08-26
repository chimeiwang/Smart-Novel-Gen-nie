package cn.inkforge.core.outlines.domain;

/** 新建伏笔的完整字段。 */
public record ForeshadowingData(
        String name,
        String plantedAt,
        String plantedContent,
        String expectedPayoff,
        String payoffAt,
        String status) {}
