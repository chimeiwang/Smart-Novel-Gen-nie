package cn.inkforge.core.platform.redis;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.serviceauth.RedisReplayStore;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
class CoreRedisIntegrationTest {

    @Container
    private static final GenericContainer<?> REDIS =
            new GenericContainer<>(DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(6379);

    @Test
    void 就绪探测与重放消费必须使用真实Redis原子语义() throws Exception {
        try (CoreRedis redis = CoreRedis.connect(redisUrl())) {
            RedisReadiness readiness = new RedisReadiness(redis);
            RedisReplayStore replay = new RedisReplayStore(redis::setIfAbsent, "java-test:replay:");

            assertThat(readiness.check()).isTrue();
            assertThat(replay.consume("同一-jti", 1)).isTrue();
            assertThat(replay.consume("同一-jti", 1)).isFalse();

            Thread.sleep(1_050);
            assertThat(replay.consume("同一-jti", 1)).isTrue();
        }
    }

    @Test
    void Redis不可用必须失败关闭且不能泄露连接密码() {
        String secret = "redis-secret-that-must-not-leak";
        try (CoreRedis redis = CoreRedis.connect("redis://:" + secret + "@127.0.0.1:1/0")) {
            RedisReadiness readiness = new RedisReadiness(redis, Duration.ofMillis(100));
            RedisReplayStore replay = new RedisReplayStore(redis::setIfAbsent, "java-test:replay:");

            assertThat(readiness.check()).isFalse();
            assertThatThrownBy(() -> replay.consume("未知-jti", 30))
                    .isInstanceOf(RedisUnavailableException.class)
                    .hasMessage("Redis 暂时不可用")
                    .hasMessageNotContaining(secret);
            assertThat(redis.toString()).doesNotContain(secret);
        }
    }

    @Test
    void 非Redis协议和非法数据库编号必须在启动时拒绝() {
        assertThatThrownBy(() -> CoreRedis.connect("http://127.0.0.1:6379/0"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("Redis URL");
        assertThatThrownBy(() -> CoreRedis.connect("redis://127.0.0.1:6379/not-a-db"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("Redis URL");
    }

    private static String redisUrl() {
        return "redis://" + REDIS.getHost() + ":" + REDIS.getMappedPort(6379) + "/0";
    }
}
