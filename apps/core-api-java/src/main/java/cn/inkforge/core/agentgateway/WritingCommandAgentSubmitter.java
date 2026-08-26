package cn.inkforge.core.agentgateway;

import cn.inkforge.contracts.agent.AgentJobAccepted;
import cn.inkforge.contracts.agent.AgentJobCancelRequest;
import cn.inkforge.contracts.agent.AgentJobRequest;
import cn.inkforge.core.writing.application.WritingCommandSubmitter;
import cn.inkforge.core.writing.application.WritingSubmissionException;
import cn.inkforge.core.writing.domain.WritingAgentJobStatus;
import cn.inkforge.core.writing.domain.WritingDispatchRecord;
import java.util.Objects;

/** 把耐久写作命令一比一映射为 Python Agent job。 */
final class WritingCommandAgentSubmitter implements WritingCommandSubmitter {

    private final AgentServiceClient client;

    WritingCommandAgentSubmitter(AgentServiceClient client) {
        this.client = Objects.requireNonNull(client);
    }

    @Override
    public WritingAgentJobStatus submit(WritingDispatchRecord command) {
        AgentJobAccepted accepted;
        try {
            accepted = client.submit(new AgentJobRequest(
                    command.id(),
                    AgentJobRequest.KindEnum.WRITING,
                    command.novelId(),
                    command.job(),
                    10,
                    "1.0",
                    command.taskId(),
                    command.taskId(),
                    command.userId())
                    .force(Boolean.TRUE.equals(command.job().get("force"))));
        } catch (AgentGatewayException exception) {
            throw new WritingSubmissionException(exception.code());
        }
        return status(accepted.getStatus());
    }

    @Override
    public void cancel(WritingDispatchRecord command) {
        if (!"cancel".equals(command.kind())) {
            throw new IllegalArgumentException("只有取消命令可以调用取消投递");
        }
        Object cancelledJobId = command.job().get("cancelledJobId");
        if (!(cancelledJobId instanceof String jobId)) {
            throw new IllegalArgumentException("取消命令缺少被取消的 job 标识");
        }
        try {
            client.cancel(
                    jobId,
                    new AgentJobCancelRequest(
                            command.novelId(),
                            "1.0",
                            command.taskId(),
                            command.taskId()));
        } catch (AgentGatewayException exception) {
            throw new WritingSubmissionException(exception.code());
        }
    }

    private static WritingAgentJobStatus status(AgentJobAccepted.StatusEnum value) {
        return switch (value) {
            case QUEUED -> WritingAgentJobStatus.QUEUED;
            case RUNNING -> WritingAgentJobStatus.RUNNING;
            case COMPLETED -> WritingAgentJobStatus.COMPLETED;
            case FAILED -> WritingAgentJobStatus.FAILED;
            case CANCELLED -> WritingAgentJobStatus.CANCELLED;
        };
    }
}
