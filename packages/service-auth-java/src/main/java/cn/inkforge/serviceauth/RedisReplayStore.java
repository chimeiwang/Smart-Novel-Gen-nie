package cn.inkforge.serviceauth;

import java.time.Duration;

/** 使用 Redis SET NX EX 原子消费 jti。 */
public final class RedisReplayStore implements ReplayStore {

    private final RedisSetIfAbsent redis;
    private final String keyPrefix;

    public RedisReplayStore(RedisSetIfAbsent redis, String keyPrefix) {
        this.redis = java.util.Objects.requireNonNull(redis);
        this.keyPrefix = ServiceAuthCanonical.nonBlank(keyPrefix, "重放键前缀");
    }

    @Override
    public boolean consume(String jti, int ttlSeconds) {
        return Boolean.TRUE.equals(
                redis.setIfAbsent(keyPrefix + jti, "1", Duration.ofSeconds(ttlSeconds)));
    }
}
