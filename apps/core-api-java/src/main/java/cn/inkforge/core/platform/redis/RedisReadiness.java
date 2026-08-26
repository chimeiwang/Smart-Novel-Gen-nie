package cn.inkforge.core.platform.redis;

import java.time.Duration;

/** 使用短超时探测认证、限流和内部请求重放所依赖的 Redis。 */
public final class RedisReadiness {

    private final CoreRedis redis;
    private final Duration timeout;

    public RedisReadiness(CoreRedis redis) {
        this(redis, Duration.ofSeconds(1));
    }

    RedisReadiness(CoreRedis redis, Duration timeout) {
        this.redis = java.util.Objects.requireNonNull(redis);
        this.timeout = java.util.Objects.requireNonNull(timeout);
    }

    public boolean check() {
        try {
            return redis.ping(timeout);
        } catch (RuntimeException exception) {
            return false;
        }
    }
}
