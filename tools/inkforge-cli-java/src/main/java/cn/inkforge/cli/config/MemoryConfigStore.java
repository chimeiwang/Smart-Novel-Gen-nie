package cn.inkforge.cli.config;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;

/** 仅供测试和嵌入式调用，不作为生产降级后端。 */
public final class MemoryConfigStore implements ConfigStore {

    private final Map<String, ProfileConfig> values = new LinkedHashMap<>();

    @Override
    public Optional<ProfileConfig> get(String profile) {
        return Optional.ofNullable(values.get(profile));
    }

    @Override
    public void save(String profile, ProfileConfig config) {
        values.put(profile, config);
    }

    @Override
    public void delete(String profile) {
        values.remove(profile);
    }
}
