package cn.inkforge.core.agentgateway;

import cn.inkforge.contracts.agent.AgentJobAccepted;
import cn.inkforge.contracts.agent.AgentJobRequest;
import cn.inkforge.core.styles.application.PortraitRunSubmitter;
import cn.inkforge.core.styles.application.PortraitSubmissionException;
import cn.inkforge.core.styles.domain.PortraitDispatchStatus;
import cn.inkforge.core.styles.domain.PortraitSection;
import java.util.LinkedHashMap;
import java.util.Map;

/** 把耐久画像任务映射为现有 Python Agent 队列协议。 */
final class PortraitAgentSubmitter implements PortraitRunSubmitter {

    private final AgentServiceClient client;

    PortraitAgentSubmitter(AgentServiceClient client) {
        this.client = java.util.Objects.requireNonNull(client);
    }

    @Override
    public PortraitDispatchStatus submit(
            String userId,
            String styleId,
            String taskId,
            String runId,
            PortraitSection section) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("styleId", styleId);
        payload.put("section", section == null ? null : section.value());
        AgentJobAccepted accepted;
        try {
            accepted = client.submit(new AgentJobRequest(
                    "portrait-" + taskId,
                    AgentJobRequest.KindEnum.PORTRAIT,
                    "style:" + styleId,
                    payload,
                    20,
                    "1.0",
                    runId,
                    taskId,
                    userId));
        } catch (AgentGatewayException exception) {
            throw new PortraitSubmissionException(exception.code());
        }
        return switch (accepted.getStatus()) {
            case QUEUED -> PortraitDispatchStatus.QUEUED;
            case RUNNING -> PortraitDispatchStatus.RUNNING;
            case COMPLETED -> PortraitDispatchStatus.COMPLETED;
            case FAILED -> PortraitDispatchStatus.FAILED;
            case CANCELLED -> PortraitDispatchStatus.CANCELLED;
        };
    }
}
