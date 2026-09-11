package cn.inkforge.serviceauth;

import java.time.Instant;
import java.util.List;

/** 签发服务令牌所需的原始 HTTP 请求事实和资源身份。 */
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
        // 复制可变输入，确保签名期间请求事实不会被调用方改写。
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
