package cn.inkforge.core.identity.application;

/** 手机短信验证码供应商端口；验证码正文永不返回 Core。 */
public interface PhoneSmsProvider {

    void sendVerificationCode(String nationalPhone, String challengeId);

    boolean verifyCode(String nationalPhone, String challengeId, String code);
}
