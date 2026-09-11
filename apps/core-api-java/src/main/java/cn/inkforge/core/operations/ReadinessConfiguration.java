package cn.inkforge.core.operations;

import cn.inkforge.core.agentgateway.AgentServiceReadiness;
import cn.inkforge.core.platform.db.DatabaseReadiness;
import cn.inkforge.core.platform.redis.RedisReadiness;
import java.util.Optional;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** 仅注册已装配的外部依赖探针，允许未配置外部依赖的最小健康上下文正常启动。 */
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
