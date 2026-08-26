package cn.inkforge.core.writing.application;

/** 工具网关只通过该端口确认任务归属和写命令活性。 */
public interface WritingToolAuthorizer {

    void requireBinding(String userId, String novelId, String taskId);

    void requireWritingJob(String userId, String novelId, String taskId, String jobId);
}
