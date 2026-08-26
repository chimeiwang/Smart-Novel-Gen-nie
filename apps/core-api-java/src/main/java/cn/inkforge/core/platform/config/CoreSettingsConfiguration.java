package cn.inkforge.core.platform.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
class CoreSettingsConfiguration {

    @Bean
    CoreSettings coreSettings(Environment environment) {
        return CoreSettings.fromLookup(environment::getProperty);
    }
}
