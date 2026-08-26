package cn.inkforge.core.operations;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.function.Supplier;

/** 聚合数据库、Redis、Agent 与后台任务检查；任何异常都收敛为 failed。 */
public final class ReadinessRegistry {

    private final Map<String, Check> checks = new ConcurrentSkipListMap<>();

    public void register(String name, Supplier<Boolean> check) {
        register(name, check, Map::of);
    }

    public void register(
            String name, Supplier<Boolean> check, Supplier<Map<String, String>> errorDetails) {
        if (name == null || name.isBlank() || checks.putIfAbsent(name, new Check(check, errorDetails)) != null) {
            throw new IllegalArgumentException("就绪检查名称无效或重复");
        }
    }

    public Snapshot evaluate() {
        Map<String, String> results = new LinkedHashMap<>();
        Map<String, String> details = new LinkedHashMap<>();
        checks.forEach((name, check) -> {
            boolean ready;
            try {
                ready = Boolean.TRUE.equals(check.probe().get());
            } catch (Exception exception) {
                ready = false;
            }
            results.put(name, ready ? "ok" : "failed");
            if (!ready) {
                try {
                    details.putAll(check.errorDetails().get());
                } catch (Exception exception) {
                    details.put(name, "BACKGROUND_STATUS_UNAVAILABLE");
                }
            }
        });
        return new Snapshot(results.values().stream().allMatch("ok"::equals), results, details);
    }

    public record Snapshot(
            boolean ready, Map<String, String> checks, Map<String, String> backgroundTasks) {

        public Snapshot {
            checks = Map.copyOf(checks);
            backgroundTasks = Map.copyOf(backgroundTasks);
        }
    }

    private record Check(Supplier<Boolean> probe, Supplier<Map<String, String>> errorDetails) {}
}
