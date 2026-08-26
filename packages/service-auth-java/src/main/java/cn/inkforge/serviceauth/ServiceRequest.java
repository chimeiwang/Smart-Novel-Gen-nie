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
    }
}
