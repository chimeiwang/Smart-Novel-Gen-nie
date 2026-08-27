package cn.inkforge.core.identity.application;

/** 发短信前的两阶段本地限流：先保护人机验签，再限制已通过验签的手机号。 */
public interface PhoneAuthRateLimiter {

    void checkHumanVerification(String clientIdentity);

    void checkPhoneSend(String phoneDigest);
}
