package cn.inkforge.core.lore.infrastructure;

import cn.inkforge.core.lore.application.LoreRepository;
import cn.inkforge.core.lore.application.LoreService;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.id.CuidV1Generator;
import java.time.Clock;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(name = "DATABASE_URL")
class LoreConfiguration {

    @Bean
    LoreRepository loreRepository(
            CoreDatabase database, CuidV1Generator ids, Clock coreClock) {
        return new JooqLoreRepository(database, ids, coreClock);
    }

    @Bean
    LoreService loreService(LoreRepository repository) {
        return new LoreService(repository);
    }
}
