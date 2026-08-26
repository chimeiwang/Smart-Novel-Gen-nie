package cn.inkforge.core.agentgateway;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import cn.inkforge.contracts.agent.AgentJobAccepted;
import cn.inkforge.contracts.agent.AgentJobRequest;
import cn.inkforge.core.quality.domain.QualityDispatchRecord;
import cn.inkforge.core.quality.domain.QualityDispatchStatus;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class QualityAgentSubmitterTest {

    @Test
    void 必须映射稳定job身份并沿用来源任务做计费归属() {
        AgentServiceClient client = mock(AgentServiceClient.class);
        when(client.submit(any())).thenReturn(new AgentJobAccepted(
                "quality-run-1",
                "run-1",
                AgentJobAccepted.StatusEnum.QUEUED,
                "source-task-1"));
        QualityAgentSubmitter submitter = new QualityAgentSubmitter(client);

        QualityDispatchStatus status = submitter.submit(new QualityDispatchRecord(
                "run-1",
                "check-1",
                "user-1",
                "novel-1",
                "chapter-1",
                "source-task-1",
                "检查时间线"));

        ArgumentCaptor<AgentJobRequest> request = ArgumentCaptor.forClass(AgentJobRequest.class);
        verify(client).submit(request.capture());
        assertThat(status).isEqualTo(QualityDispatchStatus.QUEUED);
        assertThat(request.getValue().getJobId()).isEqualTo("quality-run-1");
        assertThat(request.getValue().getRunId()).isEqualTo("run-1");
        assertThat(request.getValue().getTaskId()).isEqualTo("source-task-1");
        assertThat(request.getValue().getKind()).isEqualTo(AgentJobRequest.KindEnum.QUALITY);
        assertThat(request.getValue().getPriority()).isEqualTo(5);
        assertThat(request.getValue().getPayload())
                .containsEntry("checkId", "check-1")
                .containsEntry("chapterId", "chapter-1")
                .containsEntry("sourceTaskId", "source-task-1")
                .containsEntry("message", "检查时间线");
    }
}
