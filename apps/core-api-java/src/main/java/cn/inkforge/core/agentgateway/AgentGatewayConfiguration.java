package cn.inkforge.core.agentgateway;

import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.quality.application.QualityRunSubmitter;
import cn.inkforge.core.video.application.VideoAdaptationTaskSubmitter;
import cn.inkforge.core.video.application.VideoRenderGateway;
import cn.inkforge.core.writing.application.WritingCommandSubmitter;
import cn.inkforge.serviceauth.ServiceScope;
import cn.inkforge.serviceauth.ServiceTokenSigner;
import java.net.http.HttpClient;
import java.time.Duration;
import java.util.List;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import tools.jackson.databind.ObjectMapper;

@Configuration(proxyBeanMethods = false)
class AgentGatewayConfiguration {

    @Bean
    @ConditionalOnProperty(name = "AGENT_SERVICE_URL")
    HttpClient agentHttpClient() {
        // Python Agent 的 Uvicorn 只接受此内网明文链路上的 HTTP/1.1。JDK 默认优先 h2c；带正文的
        // POST 会先发送 Upgrade 并被 Uvicorn 以 400 拒绝，而 GET readiness 仍可能回退成功，形成假健康。
        return HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(2))
                .build();
    }

    @Bean
    @ConditionalOnProperty(name = "AGENT_SERVICE_URL")
    AgentServiceReadiness agentServiceReadiness(
            HttpClient agentHttpClient, CoreSettings settings, ObjectMapper objectMapper) {
        return new AgentServiceReadiness(
                agentHttpClient,
                settings.agentServiceUrl(),
                objectMapper,
                Duration.ofSeconds(1));
    }

    @Bean
    @ConditionalOnProperty(name = {"AGENT_SERVICE_URL", "CORE_SERVICE_PRIVATE_KEY_PATH"})
    ServiceTokenSigner coreToAgentSigner(CoreSettings settings) {
        return ServiceTokenSigner.fromPkcs8File(
                settings.coreServicePrivateKeyPath(),
                "core-api",
                "core-api",
                "agent-service",
                settings.coreServiceKeyId(),
                120,
                List.of(
                        ServiceScope.AGENT_RUN,
                        ServiceScope.AGENT_CANCEL,
                        ServiceScope.AGENT_DEBUG_READ,
                        ServiceScope.VIDEO_RENDER));
    }

    @Bean
    @ConditionalOnProperty(name = {"AGENT_SERVICE_URL", "CORE_SERVICE_PRIVATE_KEY_PATH"})
    AgentServiceClient agentServiceClient(
            HttpClient agentHttpClient,
            CoreSettings settings,
            ServiceTokenSigner coreToAgentSigner,
            ObjectMapper objectMapper) {
        return new AgentServiceClient(
                agentHttpClient,
                settings.agentServiceUrl(),
                coreToAgentSigner,
                objectMapper,
                Duration.ofSeconds(10));
    }

    @Bean
    @ConditionalOnBean(AgentServiceClient.class)
    @ConditionalOnProperty(name = "RAG_INDEX_ENABLED", havingValue = "true")
    RagAgentSubmitter ragAgentSubmitter(AgentServiceClient agentServiceClient) {
        return new RagAgentSubmitter(agentServiceClient);
    }

    @Bean
    @ConditionalOnBean(AgentServiceClient.class)
    PortraitAgentSubmitter portraitAgentSubmitter(AgentServiceClient agentServiceClient) {
        return new PortraitAgentSubmitter(agentServiceClient);
    }

    @Bean
    @ConditionalOnBean(AgentServiceClient.class)
    QualityRunSubmitter qualityRunSubmitter(AgentServiceClient agentServiceClient) {
        return new QualityAgentSubmitter(agentServiceClient);
    }

    @Bean
    @ConditionalOnBean(AgentServiceClient.class)
    WritingCommandSubmitter writingCommandSubmitter(
            AgentServiceClient agentServiceClient) {
        return new WritingCommandAgentSubmitter(agentServiceClient);
    }

    @Bean
    @ConditionalOnBean(AgentServiceClient.class)
    VideoAdaptationTaskSubmitter videoAdaptationTaskSubmitter(
            AgentServiceClient agentServiceClient) {
        return new VideoAdaptationAgentSubmitter(agentServiceClient);
    }

    @Bean
    @ConditionalOnBean(AgentServiceClient.class)
    @ConditionalOnProperty(name = "SEEDANCE_ENABLED", havingValue = "true")
    VideoRenderGateway videoRenderGateway(AgentServiceClient agentServiceClient) {
        return new VideoRenderAgentGateway(agentServiceClient);
    }
}
