package cn.inkforge.serviceauth;

import java.time.Duration;

/** 由 Core 的 Spring Data Redis 适配器实现。 */
@FunctionalInterface
public interface RedisSetIfAbsent {
    Boolean setIfAbsent(String key, String value, Duration ttl);
}
