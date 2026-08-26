package cn.inkforge.core.outlines.domain;

/** 用于验证三层树与章节闭区间的最小节点快照。 */
public record OutlineNodeSnapshot(
        String id, String kind, String parentId, Integer start, Integer end) {}
