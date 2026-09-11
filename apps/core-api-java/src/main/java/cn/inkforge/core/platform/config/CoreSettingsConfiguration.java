package cn.inkforge.core.platform.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

/** 将 Spring 环境统一映射为经过校验的 Core 运行配置。 */
@Configuration(proxyBeanMethods = false)
class CoreSettingsConfiguration {

    @Bean
    CoreSettings coreSettings(Environment environment) {
        return CoreSettings.fromLookup(environment::getProperty);
    }
}
