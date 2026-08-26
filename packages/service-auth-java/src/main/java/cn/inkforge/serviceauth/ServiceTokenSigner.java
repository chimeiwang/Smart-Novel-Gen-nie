package cn.inkforge.serviceauth;

import java.nio.charset.StandardCharsets;
import java.security.PrivateKey;
import java.security.Signature;
import java.nio.file.Path;
import java.time.Instant;
import java.util.Base64;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

/** Ed25519 服务请求签发器。 */
public final class ServiceTokenSigner {

    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();
    private static final Base64.Encoder BASE64_URL = Base64.getUrlEncoder().withoutPadding();

    private final PrivateKey privateKey;
    private final String issuer;
    private final String subject;
    private final String audience;
    private final String kid;
    private final int defaultTtlSeconds;
    private final List<ServiceScope> allowedScopes;

    ServiceTokenSigner(
            PrivateKey privateKey,
            String issuer,
            String subject,
            String audience,
            String kid,
            int defaultTtlSeconds,
            List<ServiceScope> allowedScopes) {
        this.privateKey = privateKey;
        this.issuer = ServiceAuthCanonical.nonBlank(issuer, "签发者");
        this.subject = ServiceAuthCanonical.nonBlank(subject, "主体");
        this.audience = ServiceAuthCanonical.nonBlank(audience, "受众");
        this.kid = ServiceAuthCanonical.nonBlank(kid, "kid");
        this.defaultTtlSeconds = validateTtl(defaultTtlSeconds);
        if (allowedScopes == null || allowedScopes.isEmpty()) {
            throw new IllegalArgumentException("允许的服务权限范围无效");
        }
        this.allowedScopes = List.copyOf(allowedScopes);
    }

    public static ServiceTokenSigner fromPkcs8File(
            Path path,
            String issuer,
            String subject,
            String audience,
            String kid,
            int defaultTtlSeconds,
            List<ServiceScope> allowedScopes) {
        return new ServiceTokenSigner(
                ServiceKeyFiles.readPrivateKey(path),
                issuer,
                subject,
                audience,
                kid,
                defaultTtlSeconds,
                allowedScopes);
    }

    public SignedServiceRequest sign(ServiceRequest request) {
        if (request == null || request.body() == null || request.queryString() == null) {
            throw new IllegalArgumentException("服务请求不能为空");
        }
        List<ServiceScope> scopes = request.scopes();
        if (scopes.isEmpty()
                || new HashSet<>(scopes).size() != scopes.size()
                || !allowedScopes.containsAll(scopes)) {
            throw ServiceAuthException.scope();
        }
        Instant now = request.now() == null ? Instant.now() : request.now();
        long issuedAt = now.getEpochSecond();
        int lifetime = request.ttlSeconds() == 0 ? defaultTtlSeconds : validateTtl(request.ttlSeconds());
        String bodyDigest = ServiceAuthCanonical.sha256(request.body());
        String queryDigest = ServiceAuthCanonical.sha256(request.queryString());
        String method = ServiceAuthCanonical.method(request.httpMethod());
        String path = ServiceAuthCanonical.path(request.httpPath());
        String idempotencyKey = ServiceAuthCanonical.nonBlank(request.idempotencyKey(), "Idempotency-Key");

        ObjectNode header = OBJECT_MAPPER.createObjectNode();
        header.put("alg", "EdDSA");
        header.put("kid", kid);
        header.put("typ", "JWT");

        ObjectNode claims = OBJECT_MAPPER.createObjectNode();
        claims.put("iss", issuer);
        claims.put("sub", subject);
        claims.put("aud", audience);
        ArrayNode scope = claims.putArray("scope");
        scopes.forEach(item -> scope.add(item.value()));
        claims.put("task_id", ServiceAuthCanonical.nonBlank(request.taskId(), "task_id"));
        claims.put("run_id", ServiceAuthCanonical.nonBlank(request.runId(), "run_id"));
        claims.put("novel_id", ServiceAuthCanonical.nonBlank(request.novelId(), "novel_id"));
        claims.put(
                "jti",
                request.jti() == null
                        ? java.util.UUID.randomUUID().toString()
                        : ServiceAuthCanonical.nonBlank(request.jti(), "jti"));
        claims.put("iat", issuedAt);
        claims.put("exp", issuedAt + lifetime);
        claims.put("body_sha256", bodyDigest);
        claims.put("query_sha256", queryDigest);
        claims.put("idempotency_key", idempotencyKey);
        claims.put("request_timestamp", issuedAt);
        claims.put("http_method", method);
        claims.put("http_path", path);

        String encodedHeader = BASE64_URL.encodeToString(OBJECT_MAPPER.writeValueAsBytes(header));
        String encodedClaims = BASE64_URL.encodeToString(OBJECT_MAPPER.writeValueAsBytes(claims));
        String signingInput = encodedHeader + "." + encodedClaims;
        String token = signingInput + "." + BASE64_URL.encodeToString(sign(signingInput));

        Map<String, String> headers = new LinkedHashMap<>();
        headers.put("Authorization", "Bearer " + token);
        headers.put("Idempotency-Key", idempotencyKey);
        headers.put("X-InkForge-Timestamp", Long.toString(issuedAt));
        headers.put("X-InkForge-Body-SHA256", bodyDigest);
        return new SignedServiceRequest(token, headers);
    }

    private byte[] sign(String signingInput) {
        try {
            Signature signature = Signature.getInstance("Ed25519");
            signature.initSign(privateKey);
            signature.update(signingInput.getBytes(StandardCharsets.US_ASCII));
            return signature.sign();
        } catch (Exception exception) {
            throw ServiceAuthException.authentication("服务令牌签发失败");
        }
    }

    private static int validateTtl(int ttlSeconds) {
        if (ttlSeconds < 1 || ttlSeconds > 300) {
            throw new IllegalArgumentException("服务令牌有效期必须在 1 到 300 秒之间");
        }
        return ttlSeconds;
    }
}
