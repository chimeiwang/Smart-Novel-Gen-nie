package cn.inkforge.core.video.application;

import cn.inkforge.contracts.agent.SeedanceRenderQueryRequest;
import cn.inkforge.contracts.agent.SeedanceRenderQueryResponse;
import cn.inkforge.contracts.agent.SeedanceRenderSubmitRequest;
import cn.inkforge.contracts.agent.SeedanceRenderSubmitResponse;

/** 逐镜渲染对 Agent Service 的窄接口，便于隔离协议和故障语义。 */
public interface VideoRenderGateway {

    SeedanceRenderSubmitResponse submit(SeedanceRenderSubmitRequest request);

    SeedanceRenderQueryResponse query(SeedanceRenderQueryRequest request);
}
