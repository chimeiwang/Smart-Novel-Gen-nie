package cn.inkforge.core.styles.infrastructure;

import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.styles.application.PortraitRunSubmitter;
import cn.inkforge.core.styles.application.PortraitTaskDispatcher;
import cn.inkforge.core.styles.application.StyleFileStorage;
import cn.inkforge.core.styles.application.StyleRepository;
import cn.inkforge.core.styles.application.StyleService;
import java.time.Clock;
import java.time.Duration;
import java.util.Optional;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(name = "DATABASE_URL")
class StyleConfiguration {

    @Bean
    StyleFileStorage styleFileStorage(CoreSettings settings) {
        return new StyleStorage(settings.uploadsRoot());
    }

    @Bean
    StyleRepository styleRepository(
            CoreDatabase database, CuidV1Generator ids, Clock coreClock) {
        return new JooqStyleRepository(database, ids, coreClock);
    }

    @Bean
    StyleService styleService(
            StyleRepository repository,
            StyleFileStorage storage,
            Optional<PortraitRunSubmitter> submitter) {
        return new StyleService(repository, storage, submitter.orElse(null));
    }

    @Bean
    @ConditionalOnBean(PortraitRunSubmitter.class)
    PortraitTaskDispatcher portraitTaskDispatcher(
            StyleRepository repository,
            PortraitRunSubmitter submitter,
            Clock coreClock) {
        return new PortraitTaskDispatcher(
                repository,
                submitter,
                coreClock,
                20,
                Duration.ofSeconds(5),
                Duration.ofMinutes(10));
    }
}
