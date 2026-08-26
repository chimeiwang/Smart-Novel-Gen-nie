package cn.inkforge.cli.config;

import java.util.Optional;

public interface ConfigStore {

    Optional<ProfileConfig> get(String profile);

    void save(String profile, ProfileConfig config);

    void delete(String profile);
}
