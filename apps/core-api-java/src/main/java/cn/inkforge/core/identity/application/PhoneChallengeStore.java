package cn.inkforge.core.identity.application;

import java.time.Duration;

/** Redis 挑战状态机端口；所有状态转换都必须由实现方原子完成。 */
public interface PhoneChallengeStore {

    Creation create(
            String requestDigest,
            String challengeId,
            String phoneDigest,
            String consentVersion,
            Duration ttl);

    void markSent(String challengeId);

    void markSendFailed(String challengeId);

    Claim claimVerification(
            String challengeId,
            String phoneDigest,
            String clientRequestId,
            Duration processingLease,
            int maximumAttempts);

    void markVerified(String challengeId, String clientRequestId);

    void releaseInvalidCode(String challengeId, String clientRequestId);

    void releaseProviderFailure(String challengeId, String clientRequestId);

    void complete(
            String challengeId,
            String clientRequestId,
            String userId,
            boolean newUser);

    enum CreationStatus {
        CREATED,
        REPLAY_SENT,
        IN_PROGRESS,
        DELIVERY_UNKNOWN
    }

    record Creation(CreationStatus status, String challengeId) {}

    enum ClaimStatus {
        CALL_PROVIDER,
        VERIFIED,
        COMPLETED,
        IN_PROGRESS,
        EXPIRED,
        PHONE_MISMATCH,
        REQUEST_CONFLICT,
        ATTEMPTS_EXHAUSTED
    }

    record Claim(
            ClaimStatus status,
            String consentVersion,
            String userId,
            boolean newUser) {}
}
