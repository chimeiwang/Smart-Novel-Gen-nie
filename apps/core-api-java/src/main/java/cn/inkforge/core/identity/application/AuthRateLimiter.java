package cn.inkforge.core.identity.application;

public interface AuthRateLimiter {

    void check(AuthAction action, String clientIdentity, String username);
}
