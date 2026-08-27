package cn.inkforge.core.identity.infrastructure;

import cn.inkforge.core.identity.application.PhoneAuthRateLimiter;
import cn.inkforge.core.identity.application.PhoneIdentityDigester;
import cn.inkforge.core.platform.http.ApiException;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/** 手机发码两阶段六桶限流；来源与手机号摘要分别执行分钟、小时及中国时区自然日限制。 */
public final class RedisPhoneAuthRateLimiter implements PhoneAuthRateLimiter {

    private static final String SCRIPT = """
            local function increment(key, window_ms)
              local count = redis.call('INCR', key)
              if count == 1 then
                redis.call('PEXPIRE', key, window_ms)
              end
              return count, redis.call('PTTL', key)
            end

            local now_seconds = tonumber(redis.call('TIME')[1])
            local china_day = math.floor((now_seconds + 28800) / 86400)
            local next_midnight = (china_day + 1) * 86400 - 28800
            local day_ttl_ms = math.max(1000, (next_midnight - now_seconds) * 1000)

            local minute, minute_ttl = increment(KEYS[1], ARGV[4])
            local hour, hour_ttl = increment(KEYS[2], ARGV[5])
            local day, day_ttl = increment(KEYS[3], day_ttl_ms)

            local blocked = 0
            local retry_ms = 0
            local function evaluate(count, limit, ttl)
              if count > tonumber(limit) then
                blocked = 1
                retry_ms = math.max(retry_ms, ttl)
              end
            end
            evaluate(minute, ARGV[1], minute_ttl)
            evaluate(hour, ARGV[2], hour_ttl)
            evaluate(day, ARGV[3], day_ttl)
            return {blocked, retry_ms, minute, hour, day}
            """;

    private static final int SOURCE_MINUTE_LIMIT = 5;
    private static final int SOURCE_HOUR_LIMIT = 20;
    private static final int SOURCE_DAY_LIMIT = 50;
    private static final int PHONE_MINUTE_LIMIT = 1;
    private static final int PHONE_HOUR_LIMIT = 5;
    private static final int PHONE_DAY_LIMIT = 10;

    private final RedisIntegerScript redis;
    private final String keyPrefix;
    private final PhoneIdentityDigester digester;

    public RedisPhoneAuthRateLimiter(
            RedisIntegerScript redis,
            String keyPrefix,
            PhoneIdentityDigester digester) {
        this.redis = Objects.requireNonNull(redis);
        if (keyPrefix == null
                || keyPrefix.isBlank()
                || keyPrefix.length() > 256
                || keyPrefix.indexOf('\0') >= 0) {
            throw new IllegalArgumentException("手机号认证限流键前缀格式无效");
        }
        this.keyPrefix = keyPrefix;
        this.digester = Objects.requireNonNull(digester);
    }

    @Override
    public void checkHumanVerification(String clientIdentity) {
        if (clientIdentity == null
                || clientIdentity.isBlank()
                || clientIdentity.length() > 512
                || clientIdentity.indexOf('\0') >= 0) {
            throw new IllegalArgumentException("客户端来源格式无效");
        }
        checkBuckets(
                "source",
                digester.digest("source\0" + clientIdentity),
                SOURCE_MINUTE_LIMIT,
                SOURCE_HOUR_LIMIT,
                SOURCE_DAY_LIMIT);
    }

    @Override
    public void checkPhoneSend(String phoneDigest) {
        if (phoneDigest == null || !phoneDigest.matches("^[0-9a-f]{64}$")) {
            throw new IllegalArgumentException("手机号摘要格式无效");
        }
        checkBuckets(
                "phone",
                phoneDigest,
                PHONE_MINUTE_LIMIT,
                PHONE_HOUR_LIMIT,
                PHONE_DAY_LIMIT);
    }

    private void checkBuckets(
            String dimension,
            String digest,
            int minuteLimit,
            int hourLimit,
            int dayLimit) {
        List<Long> result;
        try {
            result = redis.eval(
                    SCRIPT,
                    List.of(
                            keyPrefix + dimension + ":minute:" + digest,
                            keyPrefix + dimension + ":hour:" + digest,
                            keyPrefix + dimension + ":day:" + digest),
                    List.of(
                            Integer.toString(minuteLimit),
                            Integer.toString(hourLimit),
                            Integer.toString(dayLimit),
                            "60000",
                            "3600000"));
            if (result == null || result.size() != 5) {
                throw new IllegalStateException("Redis 手机号限流结果无效");
            }
        } catch (RuntimeException exception) {
            throw new ApiException(503, "PHONE_RATE_LIMIT_UNAVAILABLE", "手机号认证暂时不可用");
        }
        if (result.getFirst() != 0) {
            long retryAfter = Math.max(
                    1, Math.ceilDiv(Math.max(result.get(1), 0L), 1_000L));
            throw new ApiException(
                    429,
                    "PHONE_RATE_LIMITED",
                    "验证码请求过于频繁，请稍后重试",
                    null,
                    Map.of("Retry-After", Long.toString(retryAfter)));
        }
    }
}
