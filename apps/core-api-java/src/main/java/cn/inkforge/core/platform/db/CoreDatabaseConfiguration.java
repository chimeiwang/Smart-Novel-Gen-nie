package cn.inkforge.core.platform.db;

import cn.inkforge.core.platform.config.CoreSettings;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class CoreDatabaseConfiguration {

    @Bean(destroyMethod = "close")
    @ConditionalOnProperty(name = "DATABASE_URL")
    CoreDatabase coreDatabase(CoreSettings settings) {
        return CoreDatabase.connect(PostgresConnectionSettings.parse(settings.databaseUrl().reveal()));
    }

    @Bean
    @ConditionalOnProperty(name = "DATABASE_URL")
    DatabaseReadiness databaseReadiness(CoreDatabase database, CoreSettings settings) {
        SchemaProfile profile = SchemaProfile.forCapabilities(
                settings.videoPreviewEnabled(),
                settings.phoneAuthEnabled() && settings.phoneAuthSendEnabled());
        return new DatabaseReadiness(database, profile);
    }
}
