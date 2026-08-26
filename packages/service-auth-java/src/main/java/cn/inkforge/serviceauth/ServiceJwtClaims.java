package cn.inkforge.serviceauth;

import java.util.List;
import com.fasterxml.jackson.annotation.JsonProperty;

public record ServiceJwtClaims(
        String iss,
        String sub,
        String aud,
        List<ServiceScope> scope,
        @JsonProperty("task_id") String taskId,
        @JsonProperty("run_id") String runId,
        @JsonProperty("novel_id") String novelId,
        String jti,
        long iat,
        long exp,
        @JsonProperty("body_sha256") String bodySha256,
        @JsonProperty("query_sha256") String querySha256,
        @JsonProperty("idempotency_key") String idempotencyKey,
        @JsonProperty("request_timestamp") long requestTimestamp,
        @JsonProperty("http_method") String httpMethod,
        @JsonProperty("http_path") String httpPath) {

    public ServiceJwtClaims {
        scope = List.copyOf(scope);
    }
}
