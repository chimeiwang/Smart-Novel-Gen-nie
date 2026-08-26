package cn.inkforge.core.billing.infrastructure;

import cn.inkforge.core.billing.application.BillingRepository;
import cn.inkforge.core.billing.application.BillingService;
import cn.inkforge.core.billing.domain.ModelGrantCodec;
import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.serviceauth.Ed25519PrivateKeyLoader;
import java.time.Clock;
import java.util.Optional;
import java.util.UUID;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import tools.jackson.databind.ObjectMapper;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(name = "DATABASE_URL")
class BillingConfiguration {

    @Bean
    BillingRepository billingRepository(
            CoreDatabase database, CuidV1Generator ids, Clock coreClock) {
        return new JooqBillingRepository(database, ids, coreClock);
    }

    @Bean
    @ConditionalOnProperty(name = "CORE_SERVICE_PRIVATE_KEY_PATH")
    ModelGrantCodec modelGrantCodec(CoreSettings settings, ObjectMapper objectMapper) {
        return new ModelGrantCodec(
                Ed25519PrivateKeyLoader.fromPkcs8File(settings.coreServicePrivateKeyPath()),
                null,
                objectMapper);
    }

    @Bean
    BillingService billingService(
            BillingRepository repository,
            Optional<ModelGrantCodec> grantCodec,
            Clock coreClock) {
        return new BillingService(
                repository,
                grantCodec.orElse(null),
                coreClock,
                () -> UUID.randomUUID().toString());
    }
}
