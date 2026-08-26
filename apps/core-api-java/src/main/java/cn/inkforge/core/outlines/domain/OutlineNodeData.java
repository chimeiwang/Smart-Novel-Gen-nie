package cn.inkforge.core.outlines.domain;

/** 新建大纲节点的完整字段快照。 */
public record OutlineNodeData(
        String title,
        String content,
        String kind,
        String status,
        int order,
        String parentId,
        String linkedChapterId,
        Integer estimatedWordCount,
        Integer actualWordCount,
        Integer chapterStartOrder,
        Integer chapterEndOrder) {}
