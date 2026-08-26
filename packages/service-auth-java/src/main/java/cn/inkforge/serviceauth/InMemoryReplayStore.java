package cn.inkforge.serviceauth;

import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

/** 只用于单进程测试；生产必须注入 Redis 原子实现。 */
public final class InMemoryReplayStore implements ReplayStore {

    private final Set<String> values = ConcurrentHashMap.newKeySet();

    @Override
    public boolean consume(String jti, int ttlSeconds) {
        return values.add(jti);
    }

    public List<String> consumed() {
        return values.stream().sorted().toList();
    }
}
