package cn.inkforge.serviceauth;

import java.time.Instant;
import java.util.List;

public record ServiceRequest(
        byte[] body,
        String httpMethod,
        String httpPath,
        byte[] queryString,
        String idempotencyKey,
        List<ServiceScope> scopes,
        String taskId,
        String runId,
        String novelId,
        Instant now,
        int ttlSeconds,
        String jti) {

    public ServiceRequest {
        body = body.clone();
        queryString = queryString.clone();
        scopes = List.copyOf(scopes);
        if (novelId == null && !ServiceScope.allowsNullNovelId(scopes)) {
            throw new IllegalArgumentException("只有纯 execution scope 服务请求允许 novelId 为 null");
        }
        if (novelId != null) {
            novelId = ServiceAuthCanonical.nonBlank(novelId, "novelId");
        }
    }
}
