package cn.inkforge.core.identity.application;

import cn.inkforge.core.identity.domain.AuthUser;

/** 手机号登录统一结果；新建和已有账号只以 newUser 区分。 */
public record PhoneLoginResult(AuthUser user, String maskedPhone, boolean newUser) {}
