package cn.inkforge.core.identity.infrastructure;

import cn.inkforge.core.identity.application.PhoneChallengeStore;
import cn.inkforge.core.platform.http.ApiException;
import java.time.Duration;
import java.util.List;
import java.util.Objects;

/** Redis Lua 手机号挑战状态机；手机号只以带密钥摘要进入短期状态。 */
public final class RedisPhoneChallengeStore implements PhoneChallengeStore {

    private static final String CREATE_SCRIPT = """
            local existing = redis.call('GET', KEYS[1])
            if existing then
              return {'EXISTING', existing}
            end
            if redis.call('EXISTS', KEYS[2]) == 1 then
              return {'COLLISION', ''}
            end
            redis.call('SET', KEYS[1], ARGV[1], 'PX', ARGV[4])
            redis.call('HSET', KEYS[2],
              'state', 'CREATING',
              'phoneDigest', ARGV[2],
              'consentVersion', ARGV[3],
              'attempts', '0',
              'requestId', '',
              'leaseUntil', '0',
              'userId', '',
              'newUser', '0')
            redis.call('PEXPIRE', KEYS[2], ARGV[4])
            return {'CREATED', ARGV[1]}
            """;

    private static final String READ_STATE_SCRIPT = """
            local state = redis.call('HGET', KEYS[1], 'state')
            if not state then
              return {'MISSING'}
            end
            return {state}
            """;

    private static final String TRANSITION_SCRIPT = """
            local state = redis.call('HGET', KEYS[1], 'state')
            if not state then
              return {'MISSING'}
            end
            if state == ARGV[2] then
              return {'OK'}
            end
            if state ~= ARGV[1] then
              return {'INVALID'}
            end
            redis.call('HSET', KEYS[1], 'state', ARGV[2])
            return {'OK'}
            """;

    private static final String CLAIM_SCRIPT = """
            local state = redis.call('HGET', KEYS[1], 'state')
            if not state then
              return {'EXPIRED', '', '', '0'}
            end
            if redis.call('HGET', KEYS[1], 'phoneDigest') ~= ARGV[1] then
              return {'PHONE_MISMATCH', '', '', '0'}
            end

            local consent = redis.call('HGET', KEYS[1], 'consentVersion') or ''
            local owner = redis.call('HGET', KEYS[1], 'requestId') or ''
            local user_id = redis.call('HGET', KEYS[1], 'userId') or ''
            local new_user = redis.call('HGET', KEYS[1], 'newUser') or '0'
            if state == 'COMPLETED' then
              if owner == ARGV[2] then
                return {'COMPLETED', consent, user_id, new_user}
              end
              return {'REQUEST_CONFLICT', consent, '', '0'}
            end
            if state == 'VERIFIED' then
              if owner == ARGV[2] then
                return {'VERIFIED', consent, '', '0'}
              end
              return {'REQUEST_CONFLICT', consent, '', '0'}
            end

            local time = redis.call('TIME')
            local now_ms = tonumber(time[1]) * 1000 + math.floor(tonumber(time[2]) / 1000)
            if state == 'PROCESSING' then
              if owner ~= ARGV[2] then
                return {'REQUEST_CONFLICT', consent, '', '0'}
              end
              local lease_until = tonumber(redis.call('HGET', KEYS[1], 'leaseUntil') or '0')
              if lease_until > now_ms then
                return {'IN_PROGRESS', consent, '', '0'}
              end
              redis.call('HSET', KEYS[1], 'leaseUntil', now_ms + tonumber(ARGV[3]))
              return {'CALL_PROVIDER', consent, '', '0'}
            end
            if state ~= 'SENT' then
              return {'EXPIRED', consent, '', '0'}
            end

            local attempts = tonumber(redis.call('HGET', KEYS[1], 'attempts') or '0')
            if attempts >= tonumber(ARGV[4]) then
              return {'ATTEMPTS_EXHAUSTED', consent, '', '0'}
            end
            redis.call('HSET', KEYS[1],
              'state', 'PROCESSING',
              'attempts', attempts + 1,
              'requestId', ARGV[2],
              'leaseUntil', now_ms + tonumber(ARGV[3]))
            return {'CALL_PROVIDER', consent, '', '0'}
            """;

    private static final String MARK_VERIFIED_SCRIPT = """
            local state = redis.call('HGET', KEYS[1], 'state')
            if not state then
              return {'MISSING'}
            end
            local owner = redis.call('HGET', KEYS[1], 'requestId') or ''
            if owner ~= ARGV[1] then
              return {'INVALID'}
            end
            if state == 'VERIFIED' or state == 'COMPLETED' then
              return {'OK'}
            end
            if state ~= 'PROCESSING' then
              return {'INVALID'}
            end
            redis.call('HSET', KEYS[1], 'state', 'VERIFIED', 'leaseUntil', '0')
            return {'OK'}
            """;

    private static final String RELEASE_SCRIPT = """
            local state = redis.call('HGET', KEYS[1], 'state')
            if not state then
              return {'MISSING'}
            end
            local owner = redis.call('HGET', KEYS[1], 'requestId') or ''
            if state ~= 'PROCESSING' or owner ~= ARGV[1] then
              return {'INVALID'}
            end
            local attempts = tonumber(redis.call('HGET', KEYS[1], 'attempts') or '0')
            if ARGV[2] == 'PROVIDER_FAILURE' then
              attempts = math.max(0, attempts - 1)
            end
            redis.call('HSET', KEYS[1],
              'state', 'SENT',
              'attempts', attempts,
              'requestId', '',
              'leaseUntil', '0')
            return {'OK'}
            """;

    private static final String COMPLETE_SCRIPT = """
            local state = redis.call('HGET', KEYS[1], 'state')
            if not state then
              return {'MISSING'}
            end
            local owner = redis.call('HGET', KEYS[1], 'requestId') or ''
            if owner ~= ARGV[1] then
              return {'INVALID'}
            end
            if state == 'COMPLETED' then
              local stored_user = redis.call('HGET', KEYS[1], 'userId') or ''
              local stored_new = redis.call('HGET', KEYS[1], 'newUser') or '0'
              if stored_user == ARGV[2] and stored_new == ARGV[3] then
                return {'OK'}
              end
              return {'INVALID'}
            end
            if state ~= 'VERIFIED' then
              return {'INVALID'}
            end
            redis.call('HSET', KEYS[1],
              'state', 'COMPLETED',
              'userId', ARGV[2],
              'newUser', ARGV[3],
              'leaseUntil', '0')
            return {'OK'}
            """;

    private final RedisStringScript redis;
    private final String keyPrefix;

    public RedisPhoneChallengeStore(RedisStringScript redis, String keyPrefix) {
        this.redis = Objects.requireNonNull(redis);
        if (keyPrefix == null || keyPrefix.isBlank()) {
            throw new IllegalArgumentException("手机号挑战键前缀不能为空");
        }
        this.keyPrefix = keyPrefix;
    }

    @Override
    public Creation create(
            String requestDigest,
            String challengeId,
            String phoneDigest,
            String consentVersion,
            Duration ttl) {
        requireDigest(requestDigest, "请求摘要");
        requireChallengeId(challengeId);
        requireDigest(phoneDigest, "手机号摘要");
        if (consentVersion == null
                || consentVersion.isBlank()
                || consentVersion.length() > 64) {
            throw new IllegalArgumentException("协议版本格式无效");
        }
        long ttlMillis = requireDuration(ttl, "手机号挑战有效期");
        List<String> result = eval(
                CREATE_SCRIPT,
                List.of(requestKey(requestDigest), challengeKey(challengeId)),
                List.of(
                        challengeId,
                        phoneDigest,
                        consentVersion,
                        Long.toString(ttlMillis)));
        requireSize(result, 2);
        return switch (result.getFirst()) {
            case "CREATED" -> new Creation(CreationStatus.CREATED, result.get(1));
            case "EXISTING" -> existingCreation(result.get(1));
            default -> throw unavailable();
        };
    }

    @Override
    public void markSent(String challengeId) {
        transition(challengeId, "CREATING", "SENT");
    }

    @Override
    public void markSendFailed(String challengeId) {
        transition(challengeId, "CREATING", "SEND_FAILED");
    }

    @Override
    public Claim claimVerification(
            String challengeId,
            String phoneDigest,
            String clientRequestId,
            Duration processingLease,
            int maximumAttempts) {
        requireChallengeId(challengeId);
        requireDigest(phoneDigest, "手机号摘要");
        requireRequestId(clientRequestId);
        if (maximumAttempts < 1 || maximumAttempts > 20) {
            throw new IllegalArgumentException("手机号核验尝试上限无效");
        }
        List<String> result = eval(
                CLAIM_SCRIPT,
                List.of(challengeKey(challengeId)),
                List.of(
                        phoneDigest,
                        clientRequestId,
                        Long.toString(requireDuration(processingLease, "手机号核验租约")),
                        Integer.toString(maximumAttempts)));
        requireSize(result, 4);
        ClaimStatus status;
        try {
            status = ClaimStatus.valueOf(result.getFirst());
        } catch (IllegalArgumentException exception) {
            throw unavailable();
        }
        return new Claim(
                status,
                blankToNull(result.get(1)),
                blankToNull(result.get(2)),
                "1".equals(result.get(3)));
    }

    @Override
    public void markVerified(String challengeId, String clientRequestId) {
        requireRequestId(clientRequestId);
        expectOk(eval(
                MARK_VERIFIED_SCRIPT,
                List.of(challengeKey(requireChallengeId(challengeId))),
                List.of(clientRequestId)));
    }

    @Override
    public void releaseInvalidCode(String challengeId, String clientRequestId) {
        release(challengeId, clientRequestId, "INVALID_CODE");
    }

    @Override
    public void releaseProviderFailure(String challengeId, String clientRequestId) {
        release(challengeId, clientRequestId, "PROVIDER_FAILURE");
    }

    @Override
    public void complete(
            String challengeId,
            String clientRequestId,
            String userId,
            boolean newUser) {
        requireRequestId(clientRequestId);
        if (userId == null || userId.isBlank() || userId.length() > 128) {
            throw new IllegalArgumentException("用户标识格式无效");
        }
        expectOk(eval(
                COMPLETE_SCRIPT,
                List.of(challengeKey(requireChallengeId(challengeId))),
                List.of(clientRequestId, userId, newUser ? "1" : "0")));
    }

    private Creation existingCreation(String challengeId) {
        requireChallengeId(challengeId);
        List<String> state = eval(
                READ_STATE_SCRIPT, List.of(challengeKey(challengeId)), List.of());
        requireSize(state, 1);
        return switch (state.getFirst()) {
            case "CREATING" -> new Creation(CreationStatus.IN_PROGRESS, challengeId);
            case "SEND_FAILED", "MISSING" ->
                    new Creation(CreationStatus.DELIVERY_UNKNOWN, challengeId);
            case "SENT", "PROCESSING", "VERIFIED", "COMPLETED" ->
                    new Creation(CreationStatus.REPLAY_SENT, challengeId);
            default -> throw unavailable();
        };
    }

    private void transition(String challengeId, String from, String to) {
        expectOk(eval(
                TRANSITION_SCRIPT,
                List.of(challengeKey(requireChallengeId(challengeId))),
                List.of(from, to)));
    }

    private void release(String challengeId, String clientRequestId, String reason) {
        requireRequestId(clientRequestId);
        expectOk(eval(
                RELEASE_SCRIPT,
                List.of(challengeKey(requireChallengeId(challengeId))),
                List.of(clientRequestId, reason)));
    }

    private List<String> eval(
            String script, List<String> keys, List<String> arguments) {
        try {
            return redis.eval(script, keys, arguments);
        } catch (ApiException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw unavailable();
        }
    }

    private static void expectOk(List<String> result) {
        requireSize(result, 1);
        if (!"OK".equals(result.getFirst())) {
            throw unavailable();
        }
    }

    private static void requireSize(List<String> values, int expected) {
        if (values == null || values.size() != expected) {
            throw unavailable();
        }
    }

    private String challengeKey(String challengeId) {
        return keyPrefix + "challenge:" + challengeId;
    }

    private String requestKey(String requestDigest) {
        return keyPrefix + "request:" + requestDigest;
    }

    private static String requireChallengeId(String value) {
        if (value == null || !value.matches("^[A-Za-z0-9_-]{16,128}$")) {
            throw new IllegalArgumentException("手机号挑战标识格式无效");
        }
        return value;
    }

    private static void requireDigest(String value, String label) {
        if (value == null || !value.matches("^[0-9a-f]{64}$")) {
            throw new IllegalArgumentException(label + "格式无效");
        }
    }

    private static void requireRequestId(String value) {
        if (value == null || value.length() < 16 || value.length() > 128) {
            throw new IllegalArgumentException("clientRequestId 格式无效");
        }
    }

    private static long requireDuration(Duration value, String label) {
        if (value == null || value.isZero() || value.isNegative()) {
            throw new IllegalArgumentException(label + "必须大于零");
        }
        try {
            long milliseconds = value.toMillis();
            if (milliseconds < 1) {
                throw new IllegalArgumentException(label + "必须至少为 1 毫秒");
            }
            return milliseconds;
        } catch (ArithmeticException exception) {
            throw new IllegalArgumentException(label + "无效");
        }
    }

    private static String blankToNull(String value) {
        return value == null || value.isBlank() ? null : value;
    }

    private static ApiException unavailable() {
        return new ApiException(503, "PHONE_AUTH_UNAVAILABLE", "手机号认证暂时不可用");
    }
}
