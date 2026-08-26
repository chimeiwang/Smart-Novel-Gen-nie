package cn.inkforge.core.identity.application;

public record RateLimitAttempt(
        AuthAction action, String clientIdentity, String username) {}
