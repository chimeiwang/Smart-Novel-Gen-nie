package cn.inkforge.core.video.application;

/** 浏览器启动请求已经耐久化后的改编根和任务身份。 */
public record VideoAdaptationTaskAcceptance(String adaptationId, String taskId) {}
