package cn.inkforge.core.platform.http;

import cn.inkforge.core.platform.config.CoreSettings;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
class InternalHttpConfiguration implements WebMvcConfigurer {

    private final InternalAgentNetworkInterceptor networkInterceptor;
    private final ManagedSseEmitterInterceptor managedSseEmitterInterceptor =
            new ManagedSseEmitterInterceptor();

    InternalHttpConfiguration(CoreSettings settings) {
        this.networkInterceptor = new InternalAgentNetworkInterceptor(settings);
    }

    @Bean
    InternalAgentNetworkInterceptor internalAgentNetworkInterceptor() {
        return networkInterceptor;
    }

    @Bean
    ManagedSseEmitterInterceptor managedSseEmitterInterceptor() {
        return managedSseEmitterInterceptor;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(networkInterceptor)
                .addPathPatterns("/internal/v1/**")
                .order(0);
        registry.addInterceptor(managedSseEmitterInterceptor)
                .addPathPatterns("/api/v1/writing/runs/*/events")
                .order(0);
    }

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        // SseEmitter 承载写作 SSE，StreamingResponseBody 承载完整文件流。Servlet 默认约 30 秒总超时不会因 SSE 心跳
        // 重置，会把合法长任务截断并让 JSON 异常处理器写入已提交的 event-stream；0 表示不设总超时。
        configurer.setDefaultTimeout(0L);
    }
}
