package cn.inkforge.core.platform.http;

import org.openapitools.jackson.nullable.JsonNullableJackson3Module;
import org.springframework.boot.jackson.autoconfigure.JsonMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import tools.jackson.databind.JacksonModule;
import tools.jackson.databind.cfg.ConstructorDetector;

/** 让 Jackson 3 保留 JSON 字段“缺失”与“显式 null”的差异。 */
@Configuration(proxyBeanMethods = false)
class JsonNullableConfiguration {

    @Bean
    JacksonModule jsonNullableJackson3Module() {
        return new JsonNullableJackson3Module();
    }

    @Bean
    JsonMapperBuilderCustomizer generatedDtoConstructorSelection() {
        return builder -> builder.constructorDetector(
                ConstructorDetector.DEFAULT.withAllowImplicitWithDefaultConstructor(false));
    }
}
