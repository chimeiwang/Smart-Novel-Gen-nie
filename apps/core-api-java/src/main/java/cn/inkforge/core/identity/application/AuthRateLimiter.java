package cn.inkforge.core.identity.application;

/** 按认证动作、客户端身份和用户名共同执行限流。 */
public interface AuthRateLimiter {

    void check(AuthAction action, String clientIdentity, String username);
}
