package cn.inkforge.core.identity.domain;

/** 隔离密码哈希算法及其验证实现。 */
public interface PasswordCodec {

    String hash(String password);

    boolean matches(String password, String passwordHash);
}
