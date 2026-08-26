package cn.inkforge.core.video.infrastructure;

import cn.inkforge.core.video.application.VideoAdaptationSubmissionException;
import cn.inkforge.core.video.application.VideoAdaptationTaskDispatch;
import cn.inkforge.core.video.application.VideoAdaptationTaskSubmitter;
import cn.inkforge.core.video.application.VideoAdaptationAgentStatus;
import java.util.Objects;
import org.springframework.beans.factory.ObjectProvider;

/** 延迟解析 Agent 提交器，避免 Spring 配置扫描顺序决定视频调度器是否存在。 */
final class ProviderVideoAdaptationTaskSubmitter implements VideoAdaptationTaskSubmitter {

    private final ObjectProvider<VideoAdaptationTaskSubmitter> providers;

    ProviderVideoAdaptationTaskSubmitter(
            ObjectProvider<VideoAdaptationTaskSubmitter> providers) {
        this.providers = Objects.requireNonNull(providers);
    }

    @Override
    public VideoAdaptationAgentStatus submit(VideoAdaptationTaskDispatch task) {
        VideoAdaptationTaskSubmitter value = providers.getIfAvailable();
        if (value == null) {
            throw new VideoAdaptationSubmissionException("AGENT_SERVICE_UNAVAILABLE");
        }
        return value.submit(task);
    }
}
