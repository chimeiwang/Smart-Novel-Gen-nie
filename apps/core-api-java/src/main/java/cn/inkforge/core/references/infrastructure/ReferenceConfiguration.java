package cn.inkforge.core.references.infrastructure;

import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.references.application.RagIndexSubmitter;
import cn.inkforge.core.references.application.RagIndexDispatcher;
import cn.inkforge.core.references.application.ReferenceRepository;
import cn.inkforge.core.references.application.ReferenceService;
import java.time.Clock;
import java.time.Duration;
import java.util.Optional;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(name = "DATABASE_URL")
class ReferenceConfiguration {

    @Bean
    ReferenceRepository referenceRepository(
            CoreDatabase database, CuidV1Generator ids, Clock coreClock) {
        return new JooqReferenceRepository(database, ids, coreClock);
    }

    @Bean
    ReferenceService referenceService(
            ReferenceRepository repository, Optional<RagIndexSubmitter> submitter) {
        return new ReferenceService(repository, submitter.orElse(null));
    }

    @Bean
    @ConditionalOnBean(RagIndexSubmitter.class)
    RagIndexDispatcher ragIndexDispatcher(
            ReferenceRepository repository, RagIndexSubmitter submitter) {
        return new RagIndexDispatcher(repository, submitter, 20, Duration.ofSeconds(5));
    }

}
