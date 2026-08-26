package cn.inkforge.core.agentgateway;

import cn.inkforge.contracts.agent.SeedanceRenderQueryRequest;
import cn.inkforge.contracts.agent.SeedanceRenderQueryResponse;
import cn.inkforge.contracts.agent.SeedanceRenderSubmitRequest;
import cn.inkforge.contracts.agent.SeedanceRenderSubmitResponse;
import cn.inkforge.core.video.application.VideoRenderGateway;
import cn.inkforge.core.video.application.VideoRenderQueryException;
import cn.inkforge.core.video.application.VideoRenderSubmissionRejectedException;
import cn.inkforge.core.video.application.VideoRenderSubmissionUnknownException;
import java.util.Objects;

/** 把 Agent HTTP 故障翻译成视频应用端口可判定的提交、查询语义。 */
final class VideoRenderAgentGateway implements VideoRenderGateway {

    private final AgentServiceClient client;

    VideoRenderAgentGateway(AgentServiceClient client) {
        this.client = Objects.requireNonNull(client);
    }

    @Override
    public SeedanceRenderSubmitResponse submit(SeedanceRenderSubmitRequest request) {
        try {
            return client.submitSeedanceRender(request);
        } catch (SeedanceSubmissionUnknownException exception) {
            throw new VideoRenderSubmissionUnknownException();
        } catch (SeedanceGatewayRejectedException exception) {
            throw new VideoRenderSubmissionRejectedException(exception.getMessage());
        }
    }

    @Override
    public SeedanceRenderQueryResponse query(SeedanceRenderQueryRequest request) {
        try {
            return client.querySeedanceRender(request);
        } catch (SeedanceGatewayQueryException exception) {
            throw new VideoRenderQueryException();
        }
    }
}
