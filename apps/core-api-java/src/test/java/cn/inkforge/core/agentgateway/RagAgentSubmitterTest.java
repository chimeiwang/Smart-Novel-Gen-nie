package cn.inkforge.core.agentgateway;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import cn.inkforge.contracts.agent.AgentJobAccepted;
import cn.inkforge.contracts.agent.AgentJobRequest;
import cn.inkforge.core.references.domain.RagDispatchStatus;
import java.time.OffsetDateTime;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class RagAgentSubmitterTest {

    @Test
    void 必须使用稳定任务身份优先级30和最小无损载荷() {
        AgentServiceClient client = mock(AgentServiceClient.class);
        when(client.submit(any())).thenReturn(new AgentJobAccepted(
                "rag-ef0f36cc14504d4129c6ec8b8ab21a87",
                "rag-ef0f36cc14504d4129c6ec8b8ab21a87",
                AgentJobAccepted.StatusEnum.QUEUED,
                "rag-783ee574c0a9e060970bfc964fa7d223"));
        RagAgentSubmitter submitter = new RagAgentSubmitter(client);

        RagDispatchStatus status = submitter.submit(
                "user-1",
                "novel-1",
                "reference-1",
                "a".repeat(64),
                OffsetDateTime.parse("2026-08-25T04:00:00.123Z"));

        assertThat(status).isEqualTo(RagDispatchStatus.QUEUED);
        ArgumentCaptor<AgentJobRequest> request = ArgumentCaptor.forClass(AgentJobRequest.class);
        verify(client).submit(request.capture());
        AgentJobRequest value = request.getValue();
        assertThat(value.getKind()).isEqualTo(AgentJobRequest.KindEnum.RAG);
        assertThat(value.getJobId()).isEqualTo("rag-ef0f36cc14504d4129c6ec8b8ab21a87");
        assertThat(value.getRunId()).isEqualTo(value.getJobId());
        assertThat(value.getTaskId()).isEqualTo("rag-783ee574c0a9e060970bfc964fa7d223");
        assertThat(value.getNovelId()).isEqualTo("novel-1");
        assertThat(value.getUserId()).isEqualTo("user-1");
        assertThat(value.getPriority()).isEqualTo(30);
        assertThat(value.getProtocolVersion()).isEqualTo("1.0");
        assertThat(value.getPayload()).containsExactlyInAnyOrderEntriesOf(java.util.Map.of(
                "referenceId", "reference-1", "contentHash", "a".repeat(64)));
    }
}
