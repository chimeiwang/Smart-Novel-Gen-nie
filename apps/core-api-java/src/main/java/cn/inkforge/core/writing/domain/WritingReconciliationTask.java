package cn.inkforge.core.writing.domain;

/** 没有活动耐久命令、但数据库任务仍需恢复的旧写作任务快照。 */
public record WritingReconciliationTask(
        String id,
        String userId,
        String novelId,
        String chapterId,
        String writingSessionId,
        String phase,
        String graphStateJson) {}
