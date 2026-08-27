package cn.inkforge.core.identity.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.redis.CoreRedis;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
class RedisPhoneAuthRateLimiterIntegrationTest {

    @Container
    private static final GenericContainer<?> REDIS =
            new GenericContainer<>(DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(6379);

    @Test
    void 同一手机号一分钟只能发送一次() {
        try (CoreRedis redis = CoreRedis.connect(redisUrl())) {
            RedisPhoneAuthRateLimiter limiter = new RedisPhoneAuthRateLimiter(
                    redis::evalIntegers,
                    "phone-rate:" + UUID.randomUUID() + ":",
                    source -> "f".repeat(64));
            assertThat(result(limiter, "198.51.100.10", "a".repeat(64))).isEqualTo("ok");
            assertThat(result(limiter, "198.51.100.11", "a".repeat(64)))
                    .isEqualTo("PHONE_RATE_LIMITED");
        }
    }

    @Test
    void 同一来源不能通过轮换手机号绕过分钟限制() {
        try (CoreRedis redis = CoreRedis.connect(redisUrl())) {
            RedisPhoneAuthRateLimiter limiter = new RedisPhoneAuthRateLimiter(
                    redis::evalIntegers,
                    "phone-rate:" + UUID.randomUUID() + ":",
                    source -> "e".repeat(64));
            List<String> results = new ArrayList<>();
            for (int index = 0; index < 6; index++) {
                results.add(result(
                        limiter,
                        "198.51.100.12",
                        Integer.toHexString(index).repeat(64).substring(0, 64)));
            }
            assertThat(results).containsExactly(
                    "ok", "ok", "ok", "ok", "ok", "PHONE_RATE_LIMITED");
        }
    }

    private static String result(
            RedisPhoneAuthRateLimiter limiter, String source, String phoneDigest) {
        try {
            limiter.checkHumanVerification(source);
            limiter.checkPhoneSend(phoneDigest);
            return "ok";
        } catch (ApiException exception) {
            return exception.code();
        }
    }

    private static String redisUrl() {
        return "redis://" + REDIS.getHost() + ":" + REDIS.getMappedPort(6379) + "/0";
    }
}
