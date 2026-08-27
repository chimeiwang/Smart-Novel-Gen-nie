package cn.inkforge.core.identity.application;

import cn.inkforge.core.identity.domain.AuthUser;
import cn.inkforge.core.identity.domain.PhoneNumber;
import cn.inkforge.core.platform.http.ApiException;
import java.time.Duration;
import java.util.Objects;
import java.util.function.Supplier;

/** 统一手机号登录：已存在则登录，不存在则事务内自动建号。 */
public final class PhoneAuthService {

    public static final int CHALLENGE_TTL_SECONDS = 300;
    public static final int RESEND_AFTER_SECONDS = 60;
    private static final int MAXIMUM_ATTEMPTS = 5;
    private static final Duration PROCESSING_LEASE = Duration.ofSeconds(30);

    private final PhoneCaptchaVerifier captcha;
    private final PhoneSmsProvider sms;
    private final PhoneAuthRateLimiter rateLimiter;
    private final PhoneIdentityDigester digester;
    private final PhoneChallengeStore challenges;
    private final PhoneAuthRepository accounts;
    private final Supplier<String> challengeIds;
    private final String consentVersion;

    public PhoneAuthService(
            PhoneCaptchaVerifier captcha,
            PhoneSmsProvider sms,
            PhoneAuthRateLimiter rateLimiter,
            PhoneIdentityDigester digester,
            PhoneChallengeStore challenges,
            PhoneAuthRepository accounts,
            Supplier<String> challengeIds,
            String consentVersion) {
        this.captcha = Objects.requireNonNull(captcha);
        this.sms = Objects.requireNonNull(sms);
        this.rateLimiter = Objects.requireNonNull(rateLimiter);
        this.digester = Objects.requireNonNull(digester);
        this.challenges = Objects.requireNonNull(challenges);
        this.accounts = Objects.requireNonNull(accounts);
        this.challengeIds = Objects.requireNonNull(challengeIds);
        this.consentVersion = requireNonBlank(consentVersion, "协议版本不能为空");
    }

    public PhoneChallengeReceipt createChallenge(
            String phone,
            String captchaVerifyParam,
            String acceptedConsentVersion,
            boolean acceptedTerms,
            String clientRequestId,
            String clientIdentity) {
        PhoneNumber normalized = PhoneNumber.mainland(phone);
        if (!acceptedTerms || !consentVersion.equals(acceptedConsentVersion)) {
            throw new ApiException(400, "PHONE_CONSENT_REQUIRED", "请先同意用户协议和隐私政策");
        }
        requireRequestId(clientRequestId);
        String phoneDigest = digester.digest(normalized.e164());
        rateLimiter.checkHumanVerification(clientIdentity);
        if (!verifyCaptcha(captchaVerifyParam)) {
            throw new ApiException(403, "HUMAN_VERIFICATION_FAILED", "请重新完成人机验证");
        }
        rateLimiter.checkPhoneSend(phoneDigest);

        String requestDigest = digester.digest(
                clientIdentity + "\0" + normalized.e164() + "\0" + clientRequestId);
        String proposedChallengeId = requireNonBlank(challengeIds.get(), "挑战标识不能为空");
        PhoneChallengeStore.Creation creation = challenges.create(
                requestDigest,
                proposedChallengeId,
                phoneDigest,
                consentVersion,
                Duration.ofSeconds(CHALLENGE_TTL_SECONDS));
        return switch (creation.status()) {
            case REPLAY_SENT -> receipt(creation.challengeId());
            case IN_PROGRESS -> throw new ApiException(
                    409, "PHONE_CHALLENGE_IN_PROGRESS", "验证码正在发送，请稍后重试");
            case DELIVERY_UNKNOWN -> throw providerUnavailable();
            case CREATED -> send(normalized, creation.challengeId());
        };
    }

    public PhoneLoginResult verifyChallenge(
            String challengeId,
            String phone,
            String code,
            String clientRequestId) {
        String normalizedChallengeId = requireNonBlank(challengeId, "挑战标识不能为空");
        PhoneNumber normalized = PhoneNumber.mainland(phone);
        requireRequestId(clientRequestId);
        if (code == null || !code.matches("^[0-9]{6}$")) {
            throw new ApiException(400, "INVALID_SMS_CODE", "短信验证码错误或已失效");
        }
        PhoneChallengeStore.Claim claim = challenges.claimVerification(
                normalizedChallengeId,
                digester.digest(normalized.e164()),
                clientRequestId,
                PROCESSING_LEASE,
                MAXIMUM_ATTEMPTS);
        return switch (claim.status()) {
            case COMPLETED -> replayCompleted(claim, normalized);
            case VERIFIED -> finishLogin(
                    normalizedChallengeId,
                    clientRequestId,
                    normalized,
                    claim.consentVersion());
            case CALL_PROVIDER -> verifyWithProvider(
                    normalizedChallengeId,
                    clientRequestId,
                    normalized,
                    code,
                    claim.consentVersion());
            case IN_PROGRESS -> throw new ApiException(
                    409, "PHONE_VERIFICATION_IN_PROGRESS", "验证码正在核验，请稍后重试");
            case EXPIRED -> throw new ApiException(
                    410, "PHONE_CHALLENGE_EXPIRED", "验证码已失效，请重新获取");
            case PHONE_MISMATCH -> throw new ApiException(
                    400, "PHONE_CHALLENGE_MISMATCH", "手机号与验证码请求不匹配");
            case REQUEST_CONFLICT -> throw new ApiException(
                    409, "PHONE_CHALLENGE_ALREADY_USED", "该验证码请求已被使用");
            case ATTEMPTS_EXHAUSTED -> throw new ApiException(
                    429, "PHONE_VERIFY_ATTEMPTS_EXHAUSTED", "验证码尝试次数过多，请重新获取");
        };
    }

    private PhoneChallengeReceipt send(PhoneNumber phone, String challengeId) {
        try {
            sms.sendVerificationCode(phone.national(), challengeId);
            challenges.markSent(challengeId);
            return receipt(challengeId);
        } catch (PhoneProviderUnavailableException exception) {
            challenges.markSendFailed(challengeId);
            throw providerUnavailable();
        }
    }

    private PhoneLoginResult verifyWithProvider(
            String challengeId,
            String clientRequestId,
            PhoneNumber phone,
            String code,
            String acceptedConsentVersion) {
        final boolean valid;
        try {
            valid = sms.verifyCode(phone.national(), challengeId, code);
        } catch (PhoneProviderUnavailableException exception) {
            challenges.releaseProviderFailure(challengeId, clientRequestId);
            throw providerUnavailable();
        }
        if (!valid) {
            challenges.releaseInvalidCode(challengeId, clientRequestId);
            throw new ApiException(401, "INVALID_SMS_CODE", "短信验证码错误或已失效");
        }
        challenges.markVerified(challengeId, clientRequestId);
        return finishLogin(challengeId, clientRequestId, phone, acceptedConsentVersion);
    }

    private PhoneLoginResult finishLogin(
            String challengeId,
            String clientRequestId,
            PhoneNumber phone,
            String acceptedConsentVersion) {
        PhoneAccountResult account = accounts.loginOrCreate(
                phone.e164(), acceptedConsentVersion, challengeId);
        challenges.complete(
                challengeId, clientRequestId, account.user().id(), account.newUser());
        return new PhoneLoginResult(account.user(), phone.masked(), account.newUser());
    }

    private PhoneLoginResult replayCompleted(
            PhoneChallengeStore.Claim claim, PhoneNumber phone) {
        AuthUser user = accounts.findById(claim.userId());
        if (user == null) {
            throw new ApiException(503, "PHONE_AUTH_STATE_INCONSISTENT", "手机号认证暂时不可用");
        }
        return new PhoneLoginResult(user, phone.masked(), claim.newUser());
    }

    private boolean verifyCaptcha(String value) {
        try {
            return captcha.verify(requireNonBlank(value, "人机验证参数不能为空"));
        } catch (PhoneProviderUnavailableException exception) {
            throw providerUnavailable();
        }
    }

    private static PhoneChallengeReceipt receipt(String challengeId) {
        return new PhoneChallengeReceipt(
                challengeId, CHALLENGE_TTL_SECONDS, RESEND_AFTER_SECONDS);
    }

    private static ApiException providerUnavailable() {
        return new ApiException(503, "PHONE_PROVIDER_UNAVAILABLE", "手机号认证暂时不可用");
    }

    private static void requireRequestId(String value) {
        String normalized = requireNonBlank(value, "clientRequestId 不能为空");
        if (normalized.length() < 16 || normalized.length() > 128) {
            throw new IllegalArgumentException("clientRequestId 长度无效");
        }
    }

    private static String requireNonBlank(String value, String message) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(message);
        }
        return value;
    }
}
