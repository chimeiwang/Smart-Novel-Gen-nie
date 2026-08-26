package cn.inkforge.core.identity.infrastructure;

import cn.inkforge.core.identity.application.AuthRateLimiter;
import cn.inkforge.core.identity.application.AuthRepository;
import cn.inkforge.core.identity.application.AuthService;
import cn.inkforge.core.identity.domain.PasswordCodec;
import cn.inkforge.core.identity.domain.SessionTokens;
import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.redis.CoreRedis;
import java.time.Clock;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class IdentityConfiguration {

    @Bean
    PasswordCodec passwordCodec() {
        return new BCryptPasswordCodec();
    }

    @Bean
    @ConditionalOnProperty(name = "DATABASE_URL")
    AuthRepository authRepository(
            CoreDatabase database, CuidV1Generator ids, Clock coreClock) {
        return new JooqAuthRepository(database, ids, coreClock);
    }

    @Bean
    @ConditionalOnProperty(name = "REDIS_URL")
    AuthRateLimiter authRateLimiter(CoreRedis redis) {
        return new RedisAuthRateLimiter(redis::evalIntegers, "auth:limit:");
    }

    @Bean
    @ConditionalOnProperty(name = "JWT_SECRET")
    SessionTokens sessionTokens(CoreSettings settings, Clock coreClock) {
        return new Hs256SessionTokens(settings.jwtSecret().reveal(), coreClock);
    }

    @Bean
    @ConditionalOnProperty(name = {"DATABASE_URL", "REDIS_URL", "JWT_SECRET"})
    AuthService authService(
            AuthRepository repository,
            AuthRateLimiter rateLimiter,
            PasswordCodec passwordCodec,
            SessionTokens sessionTokens,
            CoreSettings settings) {
        return new AuthService(
                repository,
                rateLimiter,
                passwordCodec,
                sessionTokens,
                settings.sessionCookieSecure());
    }
}
