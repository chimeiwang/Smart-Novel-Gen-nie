package cn.inkforge.core.agentgateway;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import cn.inkforge.contracts.agent.SeedanceRenderQueryRequest;
import cn.inkforge.contracts.agent.SeedanceRenderQueryResponse;
import cn.inkforge.contracts.agent.SeedanceRenderSubmitRequest;
import cn.inkforge.contracts.agent.SeedanceRenderSubmitResponse;
import cn.inkforge.core.video.application.VideoRenderQueryException;
import cn.inkforge.core.video.application.VideoRenderSubmissionRejectedException;
import cn.inkforge.core.video.application.VideoRenderSubmissionUnknownException;
import org.junit.jupiter.api.Test;

class VideoRenderAgentGatewayTest {

    @Test
    void 必须透传成功响应并把Agent故障翻译为视频应用语义() {
        AgentServiceClient client = mock(AgentServiceClient.class);
        VideoRenderAgentGateway gateway = new VideoRenderAgentGateway(client);
        SeedanceRenderSubmitRequest submitRequest = mock(SeedanceRenderSubmitRequest.class);
        SeedanceRenderSubmitResponse submitResponse =
                new SeedanceRenderSubmitResponse("provider-1", "task-1");
        SeedanceRenderQueryRequest queryRequest =
                new SeedanceRenderQueryRequest("novel-1", 1, "provider-1", "task-1");
        SeedanceRenderQueryResponse queryResponse = new SeedanceRenderQueryResponse(
                "provider-1",
                SeedanceRenderQueryResponse.StatusEnum.RUNNING,
                "task-1");

        when(client.submitSeedanceRender(submitRequest)).thenReturn(submitResponse);
        when(client.querySeedanceRender(queryRequest)).thenReturn(queryResponse);
        assertThat(gateway.submit(submitRequest)).isSameAs(submitResponse);
        assertThat(gateway.query(queryRequest)).isSameAs(queryResponse);

        doThrow(new SeedanceSubmissionUnknownException())
                .when(client)
                .submitSeedanceRender(submitRequest);
        assertThatThrownBy(() -> gateway.submit(submitRequest))
                .isInstanceOf(VideoRenderSubmissionUnknownException.class);

        doThrow(new SeedanceGatewayRejectedException(422, "参考图不符合供应商要求"))
                .when(client)
                .submitSeedanceRender(submitRequest);
        assertThatThrownBy(() -> gateway.submit(submitRequest))
                .isInstanceOfSatisfying(
                        VideoRenderSubmissionRejectedException.class,
                        error -> assertThat(error.getMessage())
                                .isEqualTo("参考图不符合供应商要求"));

        doThrow(new SeedanceGatewayQueryException())
                .when(client)
                .querySeedanceRender(queryRequest);
        assertThatThrownBy(() -> gateway.query(queryRequest))
                .isInstanceOf(VideoRenderQueryException.class);
    }
}
