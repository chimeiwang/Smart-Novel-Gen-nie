package cn.inkforge.core.agentgateway;

import cn.inkforge.contracts.agent.AgentJobAccepted;
import cn.inkforge.contracts.agent.AgentJobRequest;
import cn.inkforge.core.quality.application.QualityRunSubmitter;
import cn.inkforge.core.quality.application.QualitySubmissionException;
import cn.inkforge.core.quality.domain.QualityDispatchRecord;
import cn.inkforge.core.quality.domain.QualityDispatchStatus;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

/** 把耐久质量 WorkflowRun 映射为现有 Python Agent 队列协议。 */
final class QualityAgentSubmitter implements QualityRunSubmitter {

    private final AgentServiceClient client;

    QualityAgentSubmitter(AgentServiceClient client) {
        this.client = Objects.requireNonNull(client);
    }

    @Override
    public QualityDispatchStatus submit(QualityDispatchRecord record) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("checkId", record.checkId());
        payload.put("chapterId", record.chapterId());
        payload.put("sourceTaskId", record.sourceTaskId());
        payload.put("message", record.message());
        String billingTaskId = record.sourceTaskId() == null
                ? record.runId()
                : record.sourceTaskId();
        AgentJobAccepted accepted;
        try {
            accepted = client.submit(new AgentJobRequest(
                    "quality-" + record.runId(),
                    AgentJobRequest.KindEnum.QUALITY,
                    record.novelId(),
                    payload,
                    5,
                    "1.0",
                    record.runId(),
                    billingTaskId,
                    record.userId()));
        } catch (AgentGatewayException exception) {
            throw new QualitySubmissionException(exception.code());
        }
        return switch (accepted.getStatus()) {
            case QUEUED -> QualityDispatchStatus.QUEUED;
            case RUNNING -> QualityDispatchStatus.RUNNING;
            case COMPLETED -> QualityDispatchStatus.COMPLETED;
            case FAILED -> QualityDispatchStatus.FAILED;
            case CANCELLED -> QualityDispatchStatus.CANCELLED;
        };
    }
}
