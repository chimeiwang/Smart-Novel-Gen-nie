package cn.inkforge.core.platform.config;

import cn.inkforge.core.platform.id.CuidV1Generator;
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** 所有领域共享的时钟与标识生成器，不能归属于任一业务模块。 */
@Configuration(proxyBeanMethods = false)
class PlatformRuntimeConfiguration {

    @Bean
    Clock coreClock() {
        return Clock.systemUTC();
    }

    @Bean
    CuidV1Generator cuidV1Generator(Clock coreClock) {
        return new CuidV1Generator(coreClock);
    }
}
