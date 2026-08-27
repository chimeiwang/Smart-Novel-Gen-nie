package cn.inkforge.core.identity.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.core.identity.application.PhoneChallengeStore;
import cn.inkforge.core.platform.redis.CoreRedis;
import java.time.Duration;
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
class RedisPhoneChallengeStoreIntegrationTest {

    @Container
    private static final GenericContainer<?> REDIS =
            new GenericContainer<>(DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(6379);

    @Test
    void 挑战必须支持发码幂等核验租约和完成结果重放() {
        try (CoreRedis redis = CoreRedis.connect(redisUrl())) {
            RedisPhoneChallengeStore store = store(redis);
            String requestDigest = "a".repeat(64);
            String phoneDigest = "b".repeat(64);
            String challengeId = "phone-challenge-00000001";

            assertThat(store.create(
                            requestDigest,
                            challengeId,
                            phoneDigest,
                            "2026-08-27",
                            Duration.ofMinutes(5)).status())
                    .isEqualTo(PhoneChallengeStore.CreationStatus.CREATED);
            assertThat(store.create(
                            requestDigest,
                            "phone-challenge-unused-01",
                            phoneDigest,
                            "2026-08-27",
                            Duration.ofMinutes(5)).status())
                    .isEqualTo(PhoneChallengeStore.CreationStatus.IN_PROGRESS);

            store.markSent(challengeId);
            PhoneChallengeStore.Creation replay = store.create(
                    requestDigest,
                    "phone-challenge-unused-02",
                    phoneDigest,
                    "2026-08-27",
                    Duration.ofMinutes(5));
            assertThat(replay.status())
                    .isEqualTo(PhoneChallengeStore.CreationStatus.REPLAY_SENT);
            assertThat(replay.challengeId()).isEqualTo(challengeId);

            assertThat(store.claimVerification(
                                    challengeId,
                                    "c".repeat(64),
                                    "verify-request-0001",
                                    Duration.ofSeconds(30),
                                    5)
                            .status())
                    .isEqualTo(PhoneChallengeStore.ClaimStatus.PHONE_MISMATCH);
            assertThat(store.claimVerification(
                                    challengeId,
                                    phoneDigest,
                                    "verify-request-0001",
                                    Duration.ofSeconds(30),
                                    5)
                            .status())
                    .isEqualTo(PhoneChallengeStore.ClaimStatus.CALL_PROVIDER);
            assertThat(store.claimVerification(
                                    challengeId,
                                    phoneDigest,
                                    "verify-request-0001",
                                    Duration.ofSeconds(30),
                                    5)
                            .status())
                    .isEqualTo(PhoneChallengeStore.ClaimStatus.IN_PROGRESS);
            assertThat(store.claimVerification(
                                    challengeId,
                                    phoneDigest,
                                    "verify-request-0002",
                                    Duration.ofSeconds(30),
                                    5)
                            .status())
                    .isEqualTo(PhoneChallengeStore.ClaimStatus.REQUEST_CONFLICT);

            store.markVerified(challengeId, "verify-request-0001");
            assertThat(store.claimVerification(
                                    challengeId,
                                    phoneDigest,
                                    "verify-request-0001",
                                    Duration.ofSeconds(30),
                                    5)
                            .status())
                    .isEqualTo(PhoneChallengeStore.ClaimStatus.VERIFIED);
            store.complete(challengeId, "verify-request-0001", "user-phone-1", true);
            PhoneChallengeStore.Claim completed = store.claimVerification(
                    challengeId,
                    phoneDigest,
                    "verify-request-0001",
                    Duration.ofSeconds(30),
                    5);
            assertThat(completed.status())
                    .isEqualTo(PhoneChallengeStore.ClaimStatus.COMPLETED);
            assertThat(completed.userId()).isEqualTo("user-phone-1");
            assertThat(completed.newUser()).isTrue();
        }
    }

    @Test
    void 错误验证码计入上限而供应商故障不消耗尝试次数() {
        try (CoreRedis redis = CoreRedis.connect(redisUrl())) {
            RedisPhoneChallengeStore store = store(redis);
            String phoneDigest = "d".repeat(64);
            String challengeId = "phone-challenge-attempts01";
            store.create(
                    "e".repeat(64),
                    challengeId,
                    phoneDigest,
                    "2026-08-27",
                    Duration.ofMinutes(5));
            store.markSent(challengeId);

            assertThat(store.claimVerification(
                                    challengeId,
                                    phoneDigest,
                                    "verify-provider-fail-01",
                                    Duration.ofSeconds(30),
                                    1)
                            .status())
                    .isEqualTo(PhoneChallengeStore.ClaimStatus.CALL_PROVIDER);
            store.releaseProviderFailure(challengeId, "verify-provider-fail-01");
            assertThat(store.claimVerification(
                                    challengeId,
                                    phoneDigest,
                                    "verify-invalid-code-01",
                                    Duration.ofSeconds(30),
                                    1)
                            .status())
                    .isEqualTo(PhoneChallengeStore.ClaimStatus.CALL_PROVIDER);
            store.releaseInvalidCode(challengeId, "verify-invalid-code-01");
            assertThat(store.claimVerification(
                                    challengeId,
                                    phoneDigest,
                                    "verify-invalid-code-02",
                                    Duration.ofSeconds(30),
                                    1)
                            .status())
                    .isEqualTo(PhoneChallengeStore.ClaimStatus.ATTEMPTS_EXHAUSTED);
        }
    }

    @Test
    void 并发核验只有一个请求能取得供应商调用租约() throws Exception {
        try (CoreRedis redis = CoreRedis.connect(redisUrl());
                var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            RedisPhoneChallengeStore store = store(redis);
            String phoneDigest = "f".repeat(64);
            String challengeId = "phone-challenge-concurrent1";
            store.create(
                    "1".repeat(64),
                    challengeId,
                    phoneDigest,
                    "2026-08-27",
                    Duration.ofMinutes(5));
            store.markSent(challengeId);

            List<Callable<PhoneChallengeStore.ClaimStatus>> calls = new ArrayList<>();
            for (int index = 0; index < 8; index++) {
                String requestId = "verify-concurrent-request-" + index;
                calls.add(() -> store.claimVerification(
                                challengeId,
                                phoneDigest,
                                requestId,
                                Duration.ofSeconds(30),
                                5)
                        .status());
            }
            List<PhoneChallengeStore.ClaimStatus> statuses = executor.invokeAll(calls)
                    .stream()
                    .map(future -> {
                        try {
                            return future.get();
                        } catch (Exception exception) {
                            throw new RuntimeException(exception);
                        }
                    })
                    .toList();
            assertThat(statuses)
                    .filteredOn(PhoneChallengeStore.ClaimStatus.CALL_PROVIDER::equals)
                    .hasSize(1);
            assertThat(statuses)
                    .filteredOn(PhoneChallengeStore.ClaimStatus.REQUEST_CONFLICT::equals)
                    .hasSize(7);
        }
    }

    @Test
    void 过期挑战不得继续核验() throws Exception {
        try (CoreRedis redis = CoreRedis.connect(redisUrl())) {
            RedisPhoneChallengeStore store = store(redis);
            String challengeId = "phone-challenge-expiring01";
            store.create(
                    "2".repeat(64),
                    challengeId,
                    "3".repeat(64),
                    "2026-08-27",
                    Duration.ofMillis(50));
            store.markSent(challengeId);
            Thread.sleep(100);

            assertThat(store.claimVerification(
                                    challengeId,
                                    "3".repeat(64),
                                    "verify-expired-request-01",
                                    Duration.ofSeconds(30),
                                    5)
                            .status())
                    .isEqualTo(PhoneChallengeStore.ClaimStatus.EXPIRED);
        }
    }

    private static RedisPhoneChallengeStore store(CoreRedis redis) {
        return new RedisPhoneChallengeStore(
                redis::evalStrings, "phone-test:" + UUID.randomUUID() + ":");
    }

    private static String redisUrl() {
        return "redis://" + REDIS.getHost() + ":" + REDIS.getMappedPort(6379) + "/0";
    }
}
