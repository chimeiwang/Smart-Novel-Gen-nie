package cn.inkforge.serviceauth;

import java.time.Instant;

public record ServiceVerificationRequest(
        String token,
        byte[] body,
        String httpMethod,
        String httpPath,
        byte[] queryString,
        String idempotencyKey,
        String requestTimestamp,
        String bodySha256,
        ServiceScope requiredScope,
        String taskId,
        String runId,
        String novelId,
        Instant now) {

    public ServiceVerificationRequest {
        body = body.clone();
        queryString = queryString.clone();
    }
}
