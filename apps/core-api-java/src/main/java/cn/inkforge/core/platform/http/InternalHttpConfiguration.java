package cn.inkforge.core.platform.http;

import cn.inkforge.core.platform.config.CoreSettings;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
class InternalHttpConfiguration implements WebMvcConfigurer {

    private final InternalAgentNetworkInterceptor networkInterceptor;

    InternalHttpConfiguration(CoreSettings settings) {
        this.networkInterceptor = new InternalAgentNetworkInterceptor(settings);
    }

    @Bean
    InternalAgentNetworkInterceptor internalAgentNetworkInterceptor() {
        return networkInterceptor;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(networkInterceptor)
                .addPathPatterns("/internal/v1/**")
                .order(0);
    }
}
