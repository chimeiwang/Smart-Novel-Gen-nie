package cn.inkforge.core.identity.domain;

public interface SessionTokens {

    int SESSION_MAX_AGE_SECONDS = 30 * 24 * 60 * 60;

    String create(String userId);

    String verify(String token);
}
