package cn.inkforge.core.identity.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.core.identity.application.AuthAction;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.redis.CoreRedis;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.Executors;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
class RedisAuthRateLimiterIntegrationTest {

    @Container
    private static final GenericContainer<?> REDIS =
            new GenericContainer<>(DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(6379);

    @Test
    void 登录账号桶在并发下只能放行五次() throws Exception {
        try (CoreRedis redis = CoreRedis.connect(redisUrl());
                var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            RedisAuthRateLimiter limiter = new RedisAuthRateLimiter(
                    redis::evalIntegers, "java-auth:" + UUID.randomUUID() + ":");
            List<Callable<String>> attempts = new ArrayList<>();
            for (int index = 0; index < 6; index++) {
                attempts.add(() -> result(limiter, AuthAction.LOGIN, "198.51.100.10", "alice"));
            }

            List<String> results = executor.invokeAll(attempts).stream()
                    .map(future -> {
                        try {
                            return future.get();
                        } catch (Exception exception) {
                            throw new RuntimeException(exception);
                        }
                    })
                    .toList();
            assertThat(results).filteredOn("ok"::equals).hasSize(5);
            assertThat(results).filteredOn("RATE_LIMITED"::equals).hasSize(1);
        }
    }

    @Test
    void 注册来源桶不能通过轮换用户名绕过() {
        try (CoreRedis redis = CoreRedis.connect(redisUrl())) {
            RedisAuthRateLimiter limiter = new RedisAuthRateLimiter(
                    redis::evalIntegers, "java-auth:" + UUID.randomUUID() + ":");
            List<String> results = new ArrayList<>();
            for (int index = 0; index < 4; index++) {
                results.add(result(
                        limiter, AuthAction.REGISTER, "198.51.100.10", "user-" + index));
            }
            assertThat(results).containsExactly("ok", "ok", "ok", "RATE_LIMITED");
        }
    }

    private String result(
            RedisAuthRateLimiter limiter,
            AuthAction action,
            String identity,
            String username) {
        try {
            limiter.check(action, identity, username);
            return "ok";
        } catch (ApiException exception) {
            return exception.code();
        }
    }

    private static String redisUrl() {
        return "redis://" + REDIS.getHost() + ":" + REDIS.getMappedPort(6379) + "/0";
    }
}
