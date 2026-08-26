package cn.inkforge.cli.config;

import java.util.Optional;

/** 会话凭据端口；生产实现不得回退到普通文件。 */
public interface CredentialStore {

    Optional<String> get(String profile, String origin);

    void set(String profile, String origin, String token);

    void delete(String profile, String origin);
}
