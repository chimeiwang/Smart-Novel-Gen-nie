package cn.inkforge.core.identity.application;

import cn.inkforge.core.identity.domain.AuthUser;

/** 手机号查询或事务内自动建号的权威数据库结果。 */
public record PhoneAccountResult(AuthUser user, boolean newUser) {}
