package cn.inkforge.core.identity.domain;

/** 认证领域唯一可向上层暴露的用户快照；密码哈希不会进入公共 DTO。 */
public record AuthUser(
        String id, String username, String passwordHash, long creditBalanceMicros) {}
