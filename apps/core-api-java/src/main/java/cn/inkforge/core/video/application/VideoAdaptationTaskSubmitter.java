package cn.inkforge.core.video.application;

/** Java Core 到 Python Agent 共享 video 队列的唯一提交端口。 */
@FunctionalInterface
public interface VideoAdaptationTaskSubmitter {

    VideoAdaptationAgentStatus submit(VideoAdaptationTaskDispatch task);
}
