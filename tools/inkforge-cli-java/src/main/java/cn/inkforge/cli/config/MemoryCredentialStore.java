package cn.inkforge.cli.config;

import cn.inkforge.cli.transport.CoreOrigin;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

/** 仅供测试和嵌入式调用，不作为生产降级后端。 */
public final class MemoryCredentialStore implements CredentialStore {

    private final Map<Key, String> values = new HashMap<>();

    @Override
    public Optional<String> get(String profile, String origin) {
        return Optional.ofNullable(values.get(new Key(profile, CoreOrigin.validate(origin))));
    }

    @Override
    public void set(String profile, String origin, String token) {
        values.put(new Key(profile, CoreOrigin.validate(origin)), token);
    }

    @Override
    public void delete(String profile, String origin) {
        values.remove(new Key(profile, CoreOrigin.validate(origin)));
    }

    private record Key(String profile, String origin) {}
}
