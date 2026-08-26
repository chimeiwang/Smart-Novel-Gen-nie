package cn.inkforge.core.shortmedium.application;

import cn.inkforge.core.shortmedium.domain.DocumentDiff;
import cn.inkforge.core.shortmedium.domain.ShortMediumVersionPayload;

/** 在同一工作稿事务中创建不可变 ReviewArtifact 版本所需的完整事实。 */
public record VersionCreation(
        ShortMediumVersionPayload payload,
        DocumentDiff diff,
        String status,
        String summary,
        String createdByAgent,
        String taskId,
        String jobId) {}
