package cn.inkforge.core.shortmedium.infrastructure;

import cn.inkforge.contracts.api.DocumentType;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.shortmedium.application.ShortMediumVersionRepository;
import cn.inkforge.core.shortmedium.application.ShortMediumVersionService;
import java.time.Clock;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import tools.jackson.databind.ObjectMapper;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(name = "DATABASE_URL")
class ShortMediumConfiguration {

    @Bean
    ShortMediumVersionRepository shortMediumVersionRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock coreClock,
            ObjectMapper objectMapper) {
        return new JooqShortMediumVersionRepository(
                database, ids, coreClock, objectMapper);
    }

    @Bean
    ShortMediumVersionService shortMediumVersionService(
            ShortMediumVersionRepository repository) {
        return new ShortMediumVersionService(repository);
    }

    @Bean
    Converter<String, DocumentType> shortMediumDocumentTypeConverter() {
        return DocumentType::fromValue;
    }
}
