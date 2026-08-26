package cn.inkforge.core.platform.redis;

import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.serviceauth.RedisReplayStore;
import cn.inkforge.serviceauth.ReplayStore;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class CoreRedisConfiguration {

    @Bean(destroyMethod = "close")
    @ConditionalOnProperty(name = "REDIS_URL")
    CoreRedis coreRedis(CoreSettings settings) {
        return CoreRedis.connect(settings.redisUrl().reveal());
    }

    @Bean
    @ConditionalOnProperty(name = "REDIS_URL")
    RedisReadiness redisReadiness(CoreRedis redis) {
        return new RedisReadiness(redis);
    }

    @Bean
    @ConditionalOnProperty(name = "REDIS_URL")
    ReplayStore serviceReplayStore(CoreRedis redis) {
        return new RedisReplayStore(redis::setIfAbsent, "service-auth:replay:");
    }
}
