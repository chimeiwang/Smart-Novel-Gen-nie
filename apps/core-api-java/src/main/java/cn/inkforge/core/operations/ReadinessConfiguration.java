package cn.inkforge.core.operations;

import cn.inkforge.core.agentgateway.AgentServiceReadiness;
import cn.inkforge.core.platform.db.DatabaseReadiness;
import cn.inkforge.core.platform.redis.RedisReadiness;
import java.util.Optional;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class ReadinessConfiguration {

    @Bean
    ReadinessRegistry readinessRegistry(
            Optional<DatabaseReadiness> database,
            Optional<RedisReadiness> redis,
            Optional<AgentServiceReadiness> agent) {
        ReadinessRegistry registry = new ReadinessRegistry();
        database.ifPresent(readiness -> {
            registry.register("database", readiness::checkConnection);
            registry.register("database_schema", readiness::checkSchema);
        });
        redis.ifPresent(readiness -> registry.register("redis", readiness::check));
        agent.ifPresent(readiness -> registry.register("agent", readiness::check));
        return registry;
    }
}
