package cn.inkforge.core.operations.background;

import cn.inkforge.core.operations.ReadinessRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** 创建受统一生命周期和 readiness 监督的后台任务管理器。 */
@Configuration(proxyBeanMethods = false)
class BackgroundTaskConfiguration {

    @Bean(destroyMethod = "close")
    BackgroundTaskManager backgroundTaskManager(ReadinessRegistry readiness) {
        return new BackgroundTaskManager(readiness);
    }
}
