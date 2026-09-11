package cn.inkforge.core.operations.api;

import cn.inkforge.core.operations.ReadinessRegistry;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/** 保持 Python Core 公共健康接口契约。 */
@RestController
public final class HealthController {

    private final ReadinessRegistry readiness;

    public HealthController(ReadinessRegistry readiness) {
        this.readiness = readiness;
    }

    /** 存活检查只确认 HTTP 服务可以响应；外部依赖的可用性由就绪检查报告。 */
    @GetMapping(value = "/api/v1/health/live", produces = MediaType.APPLICATION_JSON_VALUE)
    public LiveHealthResponse live() {
        return new LiveHealthResponse("ok", "core-api");
    }

    @GetMapping(value = "/api/v1/health/ready", produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<ReadyHealthResponse> ready() {
        ReadinessRegistry.Snapshot snapshot = readiness.evaluate();
        // 沿用公共契约：无后台诊断时省略 backgroundTasks 字段，因此用 null 配合 NON_NULL 序列化。
        ReadyHealthResponse response = new ReadyHealthResponse(
                snapshot.ready() ? "ready" : "not_ready",
                "core-api",
                snapshot.checks(),
                snapshot.backgroundTasks().isEmpty() ? null : snapshot.backgroundTasks());
        return ResponseEntity.status(snapshot.ready() ? 200 : 503).body(response);
    }

    public record LiveHealthResponse(String status, String service) {}

    @com.fasterxml.jackson.annotation.JsonInclude(
            com.fasterxml.jackson.annotation.JsonInclude.Include.NON_NULL)
    public record ReadyHealthResponse(
            String status,
            String service,
            Map<String, String> checks,
            Map<String, String> backgroundTasks) {}
}
