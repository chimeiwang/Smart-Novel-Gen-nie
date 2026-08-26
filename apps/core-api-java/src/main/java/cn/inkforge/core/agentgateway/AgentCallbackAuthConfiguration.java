package cn.inkforge.core.agentgateway;

import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.serviceauth.ReplayPolicy;
import cn.inkforge.serviceauth.ReplayStore;
import cn.inkforge.serviceauth.ServiceScope;
import cn.inkforge.serviceauth.ServiceTokenVerifier;
import java.util.List;
import java.util.Optional;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class AgentCallbackAuthConfiguration {

    @Bean
    @ConditionalOnProperty(name = {"AGENT_SERVICE_PUBLIC_KEY_PATH", "REDIS_URL"})
    AgentCallbackVerifier agentCallbackVerifier(CoreSettings settings, ReplayStore replayStore) {
        ServiceTokenVerifier verifier = ServiceTokenVerifier.fromJwksFile(
                settings.agentServicePublicKeyPath(),
                "agent-service",
                "agent-service",
                "core-api",
                replayStore,
                ReplayPolicy.ALL_SCOPES,
                10,
                List.of(
                        ServiceScope.CALLBACK_EVENT,
                        ServiceScope.CALLBACK_CHECKPOINT,
                        ServiceScope.CALLBACK_COMPLETE,
                        ServiceScope.CALLBACK_FAIL,
                        ServiceScope.TOOL_READ,
                        ServiceScope.TOOL_WRITE,
                        ServiceScope.RAG_INDEX_WRITE,
                        ServiceScope.PORTRAIT_WRITE,
                        ServiceScope.QUALITY_WRITE,
                        ServiceScope.VIDEO_WRITE,
                        ServiceScope.BILLING_AUTHORIZE,
                        ServiceScope.BILLING_USAGE_WRITE));
        return verifier::verify;
    }

    @Bean
    AgentCallbackAuthenticator agentCallbackAuthenticator(
            Optional<AgentCallbackVerifier> verifier) {
        return new AgentCallbackAuthenticator(verifier);
    }
}
