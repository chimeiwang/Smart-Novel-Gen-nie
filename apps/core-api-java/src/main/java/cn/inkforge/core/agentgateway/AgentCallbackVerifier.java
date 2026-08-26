package cn.inkforge.core.agentgateway;

import cn.inkforge.serviceauth.ServiceVerificationRequest;
import cn.inkforge.serviceauth.VerifiedServiceRequest;

/** 便于内部控制器与具体 Ed25519 实现解耦的验签端口。 */
@FunctionalInterface
public interface AgentCallbackVerifier {

    VerifiedServiceRequest verify(ServiceVerificationRequest request);
}
