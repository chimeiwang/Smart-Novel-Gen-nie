package cn.inkforge.core.agentgateway;

import cn.inkforge.contracts.agent.AgentJobAccepted;
import cn.inkforge.contracts.agent.AgentJobRequest;
import cn.inkforge.core.references.application.RagIndexSubmitter;
import cn.inkforge.core.references.application.RagSubmissionException;
import cn.inkforge.core.references.domain.RagDispatchStatus;
import cn.inkforge.core.references.domain.RagJobIdentity;
import java.time.OffsetDateTime;
import java.util.Map;

/** 把耐久 RAG 索引意图映射为现有 Python Agent 队列协议。 */
final class RagAgentSubmitter implements RagIndexSubmitter {

    private final AgentServiceClient client;

    RagAgentSubmitter(AgentServiceClient client) {
        this.client = java.util.Objects.requireNonNull(client);
    }

    @Override
    public RagDispatchStatus submit(
            String userId,
            String novelId,
            String referenceId,
            String contentHash,
            OffsetDateTime generation) {
        RagJobIdentity identity = RagJobIdentity.create(referenceId, contentHash, generation);
        AgentJobAccepted accepted;
        try {
            accepted = client.submit(new AgentJobRequest(
                    identity.runId(),
                    AgentJobRequest.KindEnum.RAG,
                    novelId,
                    Map.of("referenceId", referenceId, "contentHash", contentHash),
                    30,
                    "1.0",
                    identity.runId(),
                    identity.taskId(),
                    userId));
        } catch (AgentGatewayException exception) {
            throw new RagSubmissionException(exception.code());
        }
        return switch (accepted.getStatus()) {
            case QUEUED -> RagDispatchStatus.QUEUED;
            case RUNNING -> RagDispatchStatus.RUNNING;
            case COMPLETED -> RagDispatchStatus.COMPLETED;
            case FAILED -> RagDispatchStatus.FAILED;
            case CANCELLED -> RagDispatchStatus.CANCELLED;
        };
    }
}
