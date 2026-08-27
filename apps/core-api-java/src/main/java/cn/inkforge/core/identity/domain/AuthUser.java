package cn.inkforge.core.identity.domain;

/** 认证领域唯一可向上层暴露的用户快照；密码哈希不会进入公共 DTO。 */
public record AuthUser(
        String id,
        String username,
        String passwordHash,
        long creditBalanceMicros,
        String maskedPhone) {

    public AuthUser(
            String id, String username, String passwordHash, long creditBalanceMicros) {
        this(id, username, passwordHash, creditBalanceMicros, null);
    }

    public AuthUser {
        if (maskedPhone != null
                && !maskedPhone.matches("^1[3-9][0-9]\\*{4}[0-9]{4}$")) {
            throw new IllegalArgumentException("脱敏手机号格式无效");
        }
    }
}
