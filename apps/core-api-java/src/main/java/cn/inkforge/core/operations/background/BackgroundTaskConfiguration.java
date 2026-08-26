package cn.inkforge.core.operations.background;

import cn.inkforge.core.operations.ReadinessRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class BackgroundTaskConfiguration {

    @Bean(destroyMethod = "close")
    BackgroundTaskManager backgroundTaskManager(ReadinessRegistry readiness) {
        return new BackgroundTaskManager(readiness);
    }
}
