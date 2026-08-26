package cn.inkforge.core.outlines.infrastructure;

import cn.inkforge.core.outlines.application.OutlineRepository;
import cn.inkforge.core.outlines.application.OutlineService;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.id.CuidV1Generator;
import java.time.Clock;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(name = "DATABASE_URL")
class OutlineConfiguration {

    @Bean
    OutlineRepository outlineRepository(
            CoreDatabase database, CuidV1Generator ids, Clock coreClock) {
        return new JooqOutlineRepository(database, ids, coreClock);
    }

    @Bean
    OutlineService outlineService(OutlineRepository repository) {
        return new OutlineService(repository);
    }
}
