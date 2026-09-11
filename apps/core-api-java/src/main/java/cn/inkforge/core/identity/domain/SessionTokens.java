package cn.inkforge.core.identity.domain;

/** 创建并验证浏览器会话令牌，返回值只携带用户身份。 */
public interface SessionTokens {

    int SESSION_MAX_AGE_SECONDS = 30 * 24 * 60 * 60;

    String create(String userId);

    String verify(String token);
}
