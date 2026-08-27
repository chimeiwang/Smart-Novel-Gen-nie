package cn.inkforge.core.identity.application;

import cn.inkforge.core.identity.domain.AuthUser;

public interface PhoneAuthRepository {

    PhoneAccountResult loginOrCreate(
            String phoneE164, String consentVersion, String verificationReference);

    AuthUser findById(String userId);
}
