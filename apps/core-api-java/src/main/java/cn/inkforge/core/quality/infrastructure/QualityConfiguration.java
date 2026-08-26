package cn.inkforge.core.quality.infrastructure;

import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.quality.application.QualityRepository;
import cn.inkforge.core.quality.application.QualityRunDispatcher;
import cn.inkforge.core.quality.application.QualityRunSubmitter;
import cn.inkforge.core.quality.application.QualityService;
import java.time.Clock;
import java.time.Duration;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import tools.jackson.databind.ObjectMapper;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(name = "DATABASE_URL")
class QualityConfiguration {

    @Bean
    QualityRepository qualityRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock coreClock,
            ObjectMapper objectMapper) {
        return new JooqQualityRepository(database, ids, coreClock, objectMapper);
    }

    @Bean
    QualityRunDispatcher qualityRunDispatcher(
            QualityRepository repository,
            ObjectProvider<QualityRunSubmitter> submitters) {
        QualityRunSubmitter submitter = submitters.getIfAvailable();
        if (submitter == null) return null;
        return new QualityRunDispatcher(
                repository, submitter, 20, Duration.ofSeconds(5));
    }

    @Bean
    QualityService qualityService(
            QualityRepository repository,
            ObjectProvider<QualityRunDispatcher> dispatchers) {
        return new QualityService(repository, dispatchers.getIfAvailable());
    }
}
