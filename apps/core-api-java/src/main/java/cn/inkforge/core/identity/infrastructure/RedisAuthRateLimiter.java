package cn.inkforge.core.identity.infrastructure;

import cn.inkforge.core.identity.application.AuthAction;
import cn.inkforge.core.identity.application.AuthRateLimiter;
import cn.inkforge.core.platform.http.ApiException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;

/** 两级 Redis Lua 认证限流：先限制来源总量，再限制来源与账号组合。 */
public final class RedisAuthRateLimiter implements AuthRateLimiter {

    private static final String SCRIPT = """
            local source_count = redis.call('INCR', KEYS[1])
            if source_count == 1 then
              redis.call('PEXPIRE', KEYS[1], ARGV[2])
            end
            local source_ttl = redis.call('PTTL', KEYS[1])
            if source_count > tonumber(ARGV[1]) then
              return {1, source_ttl, source_count, -1}
            end
            local account_count = redis.call('INCR', KEYS[2])
            if account_count == 1 then
              redis.call('PEXPIRE', KEYS[2], ARGV[4])
            end
            local account_ttl = redis.call('PTTL', KEYS[2])
            local blocked = 0
            local retry_ms = 0
            if account_count > tonumber(ARGV[3]) then
              blocked = 1
              retry_ms = math.max(retry_ms, account_ttl)
            end
            return {blocked, retry_ms, source_count, account_count}
            """;
    private static final Policy LOGIN = new Policy(20, 60_000, 5, 60_000);
    private static final Policy REGISTER = new Policy(3, 3_600_000, 3, 3_600_000);

    private final RedisIntegerScript redis;
    private final String keyPrefix;

    public RedisAuthRateLimiter(RedisIntegerScript redis, String keyPrefix) {
        this.redis = java.util.Objects.requireNonNull(redis);
        if (keyPrefix == null || keyPrefix.isBlank()) {
            throw new IllegalArgumentException("认证限流键前缀不能为空");
        }
        this.keyPrefix = keyPrefix;
    }

    @Override
    public void check(AuthAction action, String clientIdentity, String username) {
        Policy policy = action == AuthAction.LOGIN ? LOGIN : REGISTER;
        String sourceDigest = sha256(clientIdentity);
        String accountDigest = sha256(clientIdentity + "\0" + username);
        List<Long> result;
        try {
            result = redis.eval(
                    SCRIPT,
                    List.of(
                            keyPrefix + action.key() + ":source:" + sourceDigest,
                            keyPrefix + action.key() + ":account:" + accountDigest),
                    List.of(
                            Integer.toString(policy.sourceLimit()),
                            Integer.toString(policy.sourceWindowMillis()),
                            Integer.toString(policy.accountLimit()),
                            Integer.toString(policy.accountWindowMillis())));
            if (result.size() != 4) {
                throw new IllegalStateException("Redis 限流结果无效");
            }
        } catch (RuntimeException exception) {
            throw new ApiException(503, "RATE_LIMIT_UNAVAILABLE", "认证服务暂时不可用");
        }
        if (result.getFirst() != 0) {
            long retryAfter = Math.max(1, Math.ceilDiv(Math.max(result.get(1), 0), 1_000));
            throw new ApiException(
                    429,
                    "RATE_LIMITED",
                    "请求过于频繁，请稍后重试",
                    null,
                    Map.of("Retry-After", Long.toString(retryAfter)));
        }
    }

    private static String sha256(String value) {
        try {
            return HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256")
                            .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception exception) {
            throw new IllegalStateException("JVM 不支持 SHA-256", exception);
        }
    }

    private record Policy(
            int sourceLimit,
            int sourceWindowMillis,
            int accountLimit,
            int accountWindowMillis) {}
}
