package cn.inkforge.cli.config;

import java.util.Optional;

/** 持久化不含令牌的 CLI profile 配置。 */
public interface ConfigStore {

    Optional<ProfileConfig> get(String profile);

    void save(String profile, ProfileConfig config);

    void delete(String profile);
}
