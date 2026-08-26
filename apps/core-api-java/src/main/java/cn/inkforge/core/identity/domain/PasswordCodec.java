package cn.inkforge.core.identity.domain;

public interface PasswordCodec {

    String hash(String password);

    boolean matches(String password, String passwordHash);
}
