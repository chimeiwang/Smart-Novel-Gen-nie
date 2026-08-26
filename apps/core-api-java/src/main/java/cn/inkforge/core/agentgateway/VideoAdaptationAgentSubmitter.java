package cn.inkforge.core.agentgateway;

import cn.inkforge.contracts.agent.AgentJobAccepted;
import cn.inkforge.contracts.agent.AgentJobRequest;
import cn.inkforge.core.video.application.VideoAdaptationAgentStatus;
import cn.inkforge.core.video.application.VideoAdaptationSubmissionException;
import cn.inkforge.core.video.application.VideoAdaptationTaskDispatch;
import cn.inkforge.core.video.application.VideoAdaptationTaskSubmitter;
import java.util.Objects;

/** 把章节改编耐久任务一比一映射到 Python Agent 的共享 video 队列。 */
final class VideoAdaptationAgentSubmitter implements VideoAdaptationTaskSubmitter {

    private final AgentServiceClient client;

    VideoAdaptationAgentSubmitter(AgentServiceClient client) {
        this.client = Objects.requireNonNull(client);
    }

    @Override
    public VideoAdaptationAgentStatus submit(VideoAdaptationTaskDispatch task) {
        AgentJobAccepted accepted;
        try {
            accepted = client.submit(new AgentJobRequest(
                    task.jobId(),
                    AgentJobRequest.KindEnum.VIDEO,
                    task.novelId(),
                    task.payload(),
                    15,
                    "1.0",
                    task.taskId(),
                    task.taskId(),
                    task.userId()));
        } catch (AgentGatewayException exception) {
            throw new VideoAdaptationSubmissionException(exception.code());
        }
        return switch (accepted.getStatus()) {
            case QUEUED -> VideoAdaptationAgentStatus.QUEUED;
            case RUNNING -> VideoAdaptationAgentStatus.RUNNING;
            case COMPLETED -> VideoAdaptationAgentStatus.COMPLETED;
            case FAILED -> VideoAdaptationAgentStatus.FAILED;
            case CANCELLED -> VideoAdaptationAgentStatus.CANCELLED;
        };
    }
}
