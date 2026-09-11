package cn.inkforge.core.identity.application;

/** 一次认证限流检查所绑定的完整维度。 */
public record RateLimitAttempt(
        AuthAction action, String clientIdentity, String username) {}
