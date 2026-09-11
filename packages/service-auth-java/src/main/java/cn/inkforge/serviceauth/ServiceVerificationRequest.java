package cn.inkforge.serviceauth;

import java.time.Instant;

/** 验证服务令牌时使用的实际 HTTP 请求、绑定头和预期资源身份。 */
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
