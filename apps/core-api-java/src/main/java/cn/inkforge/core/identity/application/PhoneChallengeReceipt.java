package cn.inkforge.core.identity.application;

/** 发码成功或安全幂等重放时返回的公开挑战元数据。 */
public record PhoneChallengeReceipt(
        String challengeId, int expiresInSeconds, int resendAfterSeconds) {}
