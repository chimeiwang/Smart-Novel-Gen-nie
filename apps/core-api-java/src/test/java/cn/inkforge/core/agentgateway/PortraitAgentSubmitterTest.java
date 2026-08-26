package cn.inkforge.core.agentgateway;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import cn.inkforge.contracts.agent.AgentJobAccepted;
import cn.inkforge.contracts.agent.AgentJobRequest;
import cn.inkforge.core.styles.domain.PortraitDispatchStatus;
import cn.inkforge.core.styles.domain.PortraitSection;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class PortraitAgentSubmitterTest {

    @Test
    void 必须复用任务身份style资源和优先级20() {
        AgentServiceClient client = mock(AgentServiceClient.class);
        when(client.submit(any())).thenReturn(new AgentJobAccepted(
                "portrait-task-1", "task-1", AgentJobAccepted.StatusEnum.QUEUED, "task-1"));
        PortraitAgentSubmitter submitter = new PortraitAgentSubmitter(client);

        assertThat(submitter.submit(
                        "user-1",
                        "style-1",
                        "task-1",
                        "task-1",
                        PortraitSection.UNIQUE_MARKERS))
                .isEqualTo(PortraitDispatchStatus.QUEUED);

        ArgumentCaptor<AgentJobRequest> request = ArgumentCaptor.forClass(AgentJobRequest.class);
        verify(client).submit(request.capture());
        AgentJobRequest value = request.getValue();
        assertThat(value.getJobId()).isEqualTo("portrait-task-1");
        assertThat(value.getKind()).isEqualTo(AgentJobRequest.KindEnum.PORTRAIT);
        assertThat(value.getNovelId()).isEqualTo("style:style-1");
        assertThat(value.getTaskId()).isEqualTo("task-1");
        assertThat(value.getRunId()).isEqualTo("task-1");
        assertThat(value.getPriority()).isEqualTo(20);
        assertThat(value.getPayload()).containsEntry("styleId", "style-1")
                .containsEntry("section", "uniqueMarkers");
    }
}
