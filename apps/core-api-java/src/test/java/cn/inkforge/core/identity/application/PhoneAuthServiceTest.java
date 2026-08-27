package cn.inkforge.core.identity.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.identity.domain.AuthUser;
import cn.inkforge.core.platform.http.ApiException;
import java.time.Duration;
import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;

class PhoneAuthServiceTest {

    @Test
    void 发码必须先通过同意限流和人机验证且同请求不得重复发短信() {
        Fixture fixture = new Fixture();

        PhoneChallengeReceipt first = fixture.service.createChallenge(
                "13800138000",
                "captcha-proof",
                "2026-08-27",
                true,
                "phone-send-request-0001",
                "198.51.100.10");
        PhoneChallengeReceipt replay = fixture.service.createChallenge(
                "13800138000",
                "captcha-proof",
                "2026-08-27",
                true,
                "phone-send-request-0001",
                "198.51.100.10");

        assertThat(first).isEqualTo(replay);
        assertThat(first.expiresInSeconds()).isEqualTo(300);
        assertThat(first.resendAfterSeconds()).isEqualTo(60);
        assertThat(fixture.sms.sendCalls).isEqualTo(1);
        assertThat(fixture.captchaCalls).isEqualTo(2);
        assertThat(fixture.sourceLimitCalls).isEqualTo(2);
        assertThat(fixture.phoneLimitCalls).isEqualTo(2);
    }

    @Test
    void 新手机号核验后必须自动建号并支持响应丢失后的安全重放() {
        Fixture fixture = new Fixture();
        fixture.repository.newUser = true;
        fixture.service.createChallenge(
                "13800138000",
                "captcha-proof",
                "2026-08-27",
                true,
                "phone-send-request-0001",
                "198.51.100.10");

        PhoneLoginResult first = fixture.service.verifyChallenge(
                fixture.challengeId,
                "13800138000",
                "123456",
                "phone-verify-request-01");
        PhoneLoginResult replay = fixture.service.verifyChallenge(
                fixture.challengeId,
                "13800138000",
                "123456",
                "phone-verify-request-01");

        assertThat(first.newUser()).isTrue();
        assertThat(first.maskedPhone()).isEqualTo("138****8000");
        assertThat(replay).isEqualTo(first);
        assertThat(fixture.sms.verifyCalls).isEqualTo(1);
        assertThat(fixture.repository.loginOrCreateCalls).isEqualTo(1);
    }

    @Test
    void 已有手机号直接登录且错误验证码不会触碰数据库() {
        Fixture fixture = new Fixture();
        fixture.sms.codeValid = false;
        fixture.service.createChallenge(
                "13800138000",
                "captcha-proof",
                "2026-08-27",
                true,
                "phone-send-request-0001",
                "198.51.100.10");

        assertCode(() -> fixture.service.verifyChallenge(
                        fixture.challengeId,
                        "13800138000",
                        "000000",
                        "phone-verify-request-01"),
                "INVALID_SMS_CODE");
        assertThat(fixture.repository.loginOrCreateCalls).isZero();
    }

    @Test
    void 手机号挑战不可换号且不同请求不能重放完成结果() {
        Fixture fixture = new Fixture();
        fixture.service.createChallenge(
                "13800138000",
                "captcha-proof",
                "2026-08-27",
                true,
                "phone-send-request-0001",
                "198.51.100.10");

        assertCode(() -> fixture.service.verifyChallenge(
                        fixture.challengeId,
                        "13900139000",
                        "123456",
                        "phone-verify-request-01"),
                "PHONE_CHALLENGE_MISMATCH");
        assertThat(fixture.sms.verifyCalls).isZero();
    }

    @Test
    void 未同意协议或人机验证失败不得发送短信() {
        Fixture fixture = new Fixture();

        assertCode(() -> fixture.service.createChallenge(
                        "13800138000",
                        "captcha-proof",
                        "2026-08-27",
                        false,
                        "phone-send-request-0001",
                        "ip"),
                "PHONE_CONSENT_REQUIRED");
        fixture.captchaValid = false;
        assertCode(() -> fixture.service.createChallenge(
                        "13800138000",
                        "captcha-proof",
                        "2026-08-27",
                        true,
                        "phone-send-request-0002",
                        "ip"),
                "HUMAN_VERIFICATION_FAILED");
        assertThat(fixture.sms.sendCalls).isZero();
        assertThat(fixture.sourceLimitCalls).isEqualTo(1);
        assertThat(fixture.phoneLimitCalls).isZero();
    }

    private static void assertCode(Runnable action, String code) {
        assertThatThrownBy(action::run)
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo(code));
    }

    private static final class Fixture {
        private final String challengeId = "challenge-000000001";
        private final MemoryStore store = new MemoryStore();
        private final FakeSms sms = new FakeSms();
        private final FakeRepository repository = new FakeRepository();
        private boolean captchaValid = true;
        private int captchaCalls;
        private int sourceLimitCalls;
        private int phoneLimitCalls;
        private final PhoneAuthService service = new PhoneAuthService(
                proof -> {
                    captchaCalls++;
                    return captchaValid && "captcha-proof".equals(proof);
                },
                sms,
                new PhoneAuthRateLimiter() {
                    @Override
                    public void checkHumanVerification(String clientIdentity) {
                        sourceLimitCalls++;
                    }

                    @Override
                    public void checkPhoneSend(String phoneDigest) {
                        phoneLimitCalls++;
                    }
                },
                value -> "digest:" + value,
                store,
                repository,
                () -> challengeId,
                "2026-08-27");
    }

    private static final class FakeSms implements PhoneSmsProvider {
        private int sendCalls;
        private int verifyCalls;
        private boolean codeValid = true;

        @Override
        public void sendVerificationCode(String nationalPhone, String challengeId) {
            assertThat(nationalPhone).isEqualTo("13800138000");
            assertThat(challengeId).startsWith("challenge-");
            sendCalls++;
        }

        @Override
        public boolean verifyCode(String nationalPhone, String challengeId, String code) {
            verifyCalls++;
            return codeValid;
        }
    }

    private static final class FakeRepository implements PhoneAuthRepository {
        private final AuthUser user = new AuthUser(
                "user-phone-1", "mobile_internal", "hidden-hash", 1_000_000_000L);
        private int loginOrCreateCalls;
        private boolean newUser;

        @Override
        public PhoneAccountResult loginOrCreate(
                String phoneE164, String consentVersion, String verificationReference) {
            loginOrCreateCalls++;
            assertThat(phoneE164).isEqualTo("+8613800138000");
            assertThat(consentVersion).isEqualTo("2026-08-27");
            assertThat(verificationReference).startsWith("challenge-");
            return new PhoneAccountResult(user, newUser);
        }

        @Override
        public AuthUser findById(String userId) {
            return user.id().equals(userId) ? user : null;
        }
    }

    private static final class MemoryStore implements PhoneChallengeStore {
        private final Map<String, Entry> byChallenge = new HashMap<>();
        private final Map<String, String> byRequest = new HashMap<>();

        @Override
        public Creation create(
                String requestDigest,
                String challengeId,
                String phoneDigest,
                String consentVersion,
                Duration ttl) {
            String existingId = byRequest.get(requestDigest);
            if (existingId != null) {
                Entry existing = byChallenge.get(existingId);
                return new Creation(
                        existing.failed ? CreationStatus.DELIVERY_UNKNOWN
                                : existing.sent ? CreationStatus.REPLAY_SENT
                                : CreationStatus.IN_PROGRESS,
                        existingId);
            }
            byRequest.put(requestDigest, challengeId);
            byChallenge.put(challengeId, new Entry(phoneDigest, consentVersion));
            return new Creation(CreationStatus.CREATED, challengeId);
        }

        @Override
        public void markSent(String challengeId) {
            byChallenge.get(challengeId).sent = true;
        }

        @Override
        public void markSendFailed(String challengeId) {
            byChallenge.get(challengeId).failed = true;
        }

        @Override
        public Claim claimVerification(
                String challengeId,
                String phoneDigest,
                String clientRequestId,
                Duration processingLease,
                int maximumAttempts) {
            Entry entry = byChallenge.get(challengeId);
            if (entry == null) return claim(ClaimStatus.EXPIRED, null);
            if (!entry.phoneDigest.equals(phoneDigest)) {
                return claim(ClaimStatus.PHONE_MISMATCH, entry);
            }
            if (entry.completed) {
                return entry.requestId.equals(clientRequestId)
                        ? claim(ClaimStatus.COMPLETED, entry)
                        : claim(ClaimStatus.REQUEST_CONFLICT, entry);
            }
            if (entry.verified) {
                return entry.requestId.equals(clientRequestId)
                        ? claim(ClaimStatus.VERIFIED, entry)
                        : claim(ClaimStatus.REQUEST_CONFLICT, entry);
            }
            if (entry.attempts >= maximumAttempts) {
                return claim(ClaimStatus.ATTEMPTS_EXHAUSTED, entry);
            }
            entry.attempts++;
            entry.requestId = clientRequestId;
            return claim(ClaimStatus.CALL_PROVIDER, entry);
        }

        @Override
        public void markVerified(String challengeId, String clientRequestId) {
            Entry entry = byChallenge.get(challengeId);
            assertThat(entry.requestId).isEqualTo(clientRequestId);
            entry.verified = true;
        }

        @Override
        public void releaseInvalidCode(String challengeId, String clientRequestId) {
            byChallenge.get(challengeId).requestId = null;
        }

        @Override
        public void releaseProviderFailure(String challengeId, String clientRequestId) {
            byChallenge.get(challengeId).requestId = null;
        }

        @Override
        public void complete(
                String challengeId,
                String clientRequestId,
                String userId,
                boolean newUser) {
            Entry entry = byChallenge.get(challengeId);
            entry.completed = true;
            entry.userId = userId;
            entry.newUser = newUser;
        }

        private Claim claim(ClaimStatus status, Entry entry) {
            return new Claim(
                    status,
                    entry == null ? null : entry.consentVersion,
                    entry == null ? null : entry.userId,
                    entry != null && entry.newUser);
        }

        private static final class Entry {
            private final String phoneDigest;
            private final String consentVersion;
            private boolean sent;
            private boolean failed;
            private boolean verified;
            private boolean completed;
            private int attempts;
            private String requestId;
            private String userId;
            private boolean newUser;

            private Entry(String phoneDigest, String consentVersion) {
                this.phoneDigest = phoneDigest;
                this.consentVersion = consentVersion;
            }
        }
    }
}
