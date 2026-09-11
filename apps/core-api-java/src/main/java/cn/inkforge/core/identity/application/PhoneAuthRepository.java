package cn.inkforge.core.identity.application;

import cn.inkforge.core.identity.domain.AuthUser;

/** 在验证码成功后原子登录既有手机号身份或创建新用户。 */
public interface PhoneAuthRepository {

    PhoneAccountResult loginOrCreate(
            String phoneE164, String consentVersion, String verificationReference);

    AuthUser findById(String userId);
}
