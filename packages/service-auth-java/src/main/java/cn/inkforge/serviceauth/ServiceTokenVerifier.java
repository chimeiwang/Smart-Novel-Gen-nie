package cn.inkforge.serviceauth;

import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.MessageDigest;
import java.security.PublicKey;
import java.security.Signature;
import java.security.spec.X509EncodedKeySpec;
import java.time.Instant;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Base64;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Pattern;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/** 严格验证 Ed25519 JWT、原始 HTTP 绑定、资源身份与重放。 */
public final class ServiceTokenVerifier {

    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();
    private static final Base64.Decoder BASE64_URL = Base64.getUrlDecoder();
    private static final Pattern SHA256 = Pattern.compile("[0-9a-f]{64}");
    private static final Set<String> HEADER_FIELDS = Set.of("alg", "typ", "kid");
    private static final Set<String> CLAIM_FIELDS = Set.of(
            "iss",
            "sub",
            "aud",
            "scope",
            "task_id",
            "run_id",
            "novel_id",
            "jti",
            "iat",
            "exp",
            "body_sha256",
            "query_sha256",
            "idempotency_key",
            "request_timestamp",
            "http_method",
            "http_path");
    private static final Set<ServiceScope> WRITE_SCOPES = EnumSet.of(
            ServiceScope.AGENT_RUN,
            ServiceScope.AGENT_CANCEL,
            ServiceScope.CALLBACK_EVENT,
            ServiceScope.CALLBACK_CHECKPOINT,
            ServiceScope.CALLBACK_COMPLETE,
            ServiceScope.CALLBACK_FAIL,
            ServiceScope.TOOL_WRITE,
            ServiceScope.RAG_INDEX_WRITE,
            ServiceScope.PORTRAIT_WRITE,
            ServiceScope.QUALITY_WRITE,
            ServiceScope.VIDEO_WRITE,
            ServiceScope.VIDEO_RENDER,
            ServiceScope.EXECUTION_SUBMIT,
            ServiceScope.EXECUTION_CANCEL,
            ServiceScope.EXECUTION_PROGRESS,
            ServiceScope.EXECUTION_RESULT,
            ServiceScope.BILLING_USAGE_WRITE,
            ServiceScope.BILLING_RECONCILE);

    private final Map<String, PublicKey> publicKeys;
    private final String expectedIssuer;
    private final String expectedSubject;
    private final String audience;
    private final ReplayStore replayStore;
    private final ReplayPolicy replayPolicy;
    private final int clockSkewSeconds;
    private final Set<ServiceScope> allowedScopes;

    private ServiceTokenVerifier(
            Map<String, PublicKey> publicKeys,
            String expectedIssuer,
            String expectedSubject,
            String audience,
            ReplayStore replayStore,
            ReplayPolicy replayPolicy,
            int clockSkewSeconds,
            List<ServiceScope> allowedScopes) {
        this.publicKeys = Map.copyOf(publicKeys);
        this.expectedIssuer = ServiceAuthCanonical.nonBlank(expectedIssuer, "签发者");
        this.expectedSubject = ServiceAuthCanonical.nonBlank(expectedSubject, "主体");
        this.audience = ServiceAuthCanonical.nonBlank(audience, "受众");
        this.replayStore = replayStore;
        this.replayPolicy = replayPolicy;
        if (clockSkewSeconds < 0 || clockSkewSeconds > 30) {
            throw new IllegalArgumentException("服务令牌时钟偏差必须在 0 到 30 秒之间");
        }
        this.clockSkewSeconds = clockSkewSeconds;
        if (allowedScopes == null || allowedScopes.isEmpty()) {
            throw new IllegalArgumentException("允许的服务权限范围无效");
        }
        this.allowedScopes = Set.copyOf(allowedScopes);
    }

    public static ServiceTokenVerifier fromJwks(
            JsonNode jwks,
            String expectedIssuer,
            String expectedSubject,
            String audience,
            ReplayStore replayStore,
            ReplayPolicy replayPolicy,
            int clockSkewSeconds,
            List<ServiceScope> allowedScopes) {
        if (replayStore == null || replayPolicy == null) {
            throw new IllegalArgumentException("重放保护配置无效");
        }
        return new ServiceTokenVerifier(
                loadJwks(jwks),
                expectedIssuer,
                expectedSubject,
                audience,
                replayStore,
                replayPolicy,
                clockSkewSeconds,
                allowedScopes);
    }

    public static ServiceTokenVerifier fromJwksFile(
            Path path,
            String expectedIssuer,
            String expectedSubject,
            String audience,
            ReplayStore replayStore,
            ReplayPolicy replayPolicy,
            int clockSkewSeconds,
            List<ServiceScope> allowedScopes) {
        return fromJwks(
                ServiceKeyFiles.readJwks(path),
                expectedIssuer,
                expectedSubject,
                audience,
                replayStore,
                replayPolicy,
                clockSkewSeconds,
                allowedScopes);
    }

    public VerifiedServiceRequest verify(ServiceVerificationRequest request) {
        long now = (request.now() == null ? Instant.now() : request.now()).getEpochSecond();
        ServiceJwtClaims claims = authenticate(request.token(), now);
        if (!allowedScopes.containsAll(claims.scope()) || !allowedScopes.contains(request.requiredScope())) {
            throw ServiceAuthException.scope();
        }
        verifyRequestBinding(claims, request, now);
        verifyResource("task_id", claims.taskId(), request.taskId());
        verifyResource("run_id", claims.runId(), request.runId());
        verifyResource("novel_id", claims.novelId(), request.novelId());
        if (!claims.scope().contains(request.requiredScope())) {
            throw ServiceAuthException.scope();
        }
        if (replayPolicy == ReplayPolicy.ALL_SCOPES || WRITE_SCOPES.contains(request.requiredScope())) {
            boolean consumed;
            try {
                consumed = replayStore.consume(claims.jti(), 300);
            } catch (Exception exception) {
                throw ServiceAuthException.replayUnavailable();
            }
            if (!consumed) {
                throw ServiceAuthException.replayed();
            }
        }
        return new VerifiedServiceRequest(claims);
    }

    private ServiceJwtClaims authenticate(String token, long now) {
        try {
            String[] parts = token.split("\\.", -1);
            if (parts.length != 3 || ArraysSupport.hasBlank(parts)) {
                throw ServiceAuthException.authentication("服务身份认证失败");
            }
            JsonNode header = OBJECT_MAPPER.readTree(BASE64_URL.decode(parts[0]));
            if (!header.isObject()
                    || !Set.copyOf(header.propertyNames()).equals(HEADER_FIELDS)
                    || !"EdDSA".equals(header.path("alg").asString())
                    || !"JWT".equals(header.path("typ").asString())) {
                throw ServiceAuthException.authentication("服务令牌头字段无效");
            }
            String kid = header.path("kid").asString(null);
            PublicKey publicKey = publicKeys.get(kid);
            if (publicKey == null) {
                throw ServiceAuthException.authentication("服务令牌 kid 未知");
            }
            Signature signature = Signature.getInstance("Ed25519");
            signature.initVerify(publicKey);
            signature.update((parts[0] + "." + parts[1]).getBytes(StandardCharsets.US_ASCII));
            if (!signature.verify(BASE64_URL.decode(parts[2]))) {
                throw ServiceAuthException.authentication("服务身份认证失败");
            }
            JsonNode payload = OBJECT_MAPPER.readTree(BASE64_URL.decode(parts[1]));
            ServiceJwtClaims claims = parseClaims(payload);
            if (!expectedIssuer.equals(claims.iss())
                    || !expectedSubject.equals(claims.sub())
                    || !audience.equals(claims.aud())) {
                throw ServiceAuthException.authentication("服务身份认证失败");
            }
            if (claims.iat() > now + clockSkewSeconds) {
                throw ServiceAuthException.authentication("服务令牌尚未生效");
            }
            if (claims.exp() < now - clockSkewSeconds) {
                throw ServiceAuthException.authentication("服务令牌已过期");
            }
            return claims;
        } catch (ServiceAuthException exception) {
            throw exception;
        } catch (Exception exception) {
            throw ServiceAuthException.authentication("服务身份认证失败");
        }
    }

    private static ServiceJwtClaims parseClaims(JsonNode payload) {
        if (!payload.isObject() || !Set.copyOf(payload.propertyNames()).equals(CLAIM_FIELDS)) {
            throw ServiceAuthException.authentication("服务令牌声明字段无效");
        }
        List<ServiceScope> scopes = new ArrayList<>();
        JsonNode scopeNode = payload.path("scope");
        if (!scopeNode.isArray() || scopeNode.isEmpty()) {
            throw ServiceAuthException.authentication("服务令牌声明字段无效");
        }
        for (JsonNode value : scopeNode) {
            if (!value.isString()) {
                throw ServiceAuthException.authentication("服务令牌声明字段无效");
            }
            scopes.add(ServiceScope.fromValue(value.asString()));
        }
        if (new HashSet<>(scopes).size() != scopes.size()) {
            throw ServiceAuthException.authentication("服务令牌权限范围不能重复");
        }
        long issuedAt = strictLong(payload, "iat");
        long expiresAt = strictLong(payload, "exp");
        long requestTimestamp = strictLong(payload, "request_timestamp");
        if (expiresAt <= issuedAt || expiresAt - issuedAt > 300 || requestTimestamp != issuedAt) {
            throw ServiceAuthException.authentication("服务令牌有效期无效");
        }
        String bodyDigest = strictText(payload, "body_sha256");
        String queryDigest = strictText(payload, "query_sha256");
        if (!SHA256.matcher(bodyDigest).matches() || !SHA256.matcher(queryDigest).matches()) {
            throw ServiceAuthException.authentication("服务令牌摘要无效");
        }
        String method = strictText(payload, "http_method");
        String path = strictText(payload, "http_path");
        if (!method.equals(ServiceAuthCanonical.method(method))
                || !path.equals(ServiceAuthCanonical.path(path))) {
            throw ServiceAuthException.authentication("服务令牌请求绑定无效");
        }
        return new ServiceJwtClaims(
                strictText(payload, "iss"),
                strictText(payload, "sub"),
                strictText(payload, "aud"),
                scopes,
                strictText(payload, "task_id"),
                strictText(payload, "run_id"),
                nullableStrictText(payload, "novel_id"),
                strictText(payload, "jti"),
                issuedAt,
                expiresAt,
                bodyDigest,
                queryDigest,
                strictText(payload, "idempotency_key"),
                requestTimestamp,
                method,
                path);
    }

    private void verifyRequestBinding(ServiceJwtClaims claims, ServiceVerificationRequest request, long now) {
        long timestamp;
        try {
            timestamp = Long.parseLong(request.requestTimestamp());
            if (!Long.toString(timestamp).equals(request.requestTimestamp())
                    || !SHA256.matcher(request.bodySha256()).matches()) {
                throw new IllegalArgumentException();
            }
        } catch (Exception exception) {
            throw ServiceAuthException.binding("服务请求绑定头格式无效");
        }
        if (Math.abs(now - timestamp) > clockSkewSeconds) {
            throw ServiceAuthException.binding("服务请求时间超出允许偏差");
        }
        String bodyDigest = ServiceAuthCanonical.sha256(request.body());
        String queryDigest = ServiceAuthCanonical.sha256(request.queryString());
        if (!ServiceAuthCanonical.digestEquals(request.bodySha256(), bodyDigest)
                || !ServiceAuthCanonical.digestEquals(claims.bodySha256(), bodyDigest)) {
            throw ServiceAuthException.binding("服务请求体摘要不匹配");
        }
        if (!ServiceAuthCanonical.digestEquals(claims.querySha256(), queryDigest)) {
            throw ServiceAuthException.binding("服务请求查询字符串摘要不匹配");
        }
        String method;
        String path;
        try {
            method = ServiceAuthCanonical.method(request.httpMethod());
            path = ServiceAuthCanonical.path(request.httpPath());
        } catch (IllegalArgumentException exception) {
            throw ServiceAuthException.binding("服务请求绑定头格式无效");
        }
        if (claims.requestTimestamp() != timestamp) {
            throw ServiceAuthException.binding("服务请求请求时间不匹配");
        }
        if (!claims.idempotencyKey().equals(request.idempotencyKey())) {
            throw ServiceAuthException.binding("服务请求幂等键不匹配");
        }
        if (!claims.httpMethod().equals(method)) {
            throw ServiceAuthException.binding("服务请求HTTP 方法不匹配");
        }
        if (!claims.httpPath().equals(path)) {
            throw ServiceAuthException.binding("服务请求HTTP 路径不匹配");
        }
    }

    private static void verifyResource(String field, String claim, String requested) {
        if (!Objects.equals(claim, requested)) {
            throw ServiceAuthException.resource(field);
        }
    }

    private static Map<String, PublicKey> loadJwks(JsonNode jwks) {
        try {
            if (!jwks.isObject()
                    || !Set.copyOf(jwks.propertyNames()).equals(Set.of("keys"))
                    || !jwks.path("keys").isArray()
                    || jwks.path("keys").size() < 1
                    || jwks.path("keys").size() > 2) {
                throw new IllegalArgumentException();
            }
            Map<String, PublicKey> result = new HashMap<>();
            Set<String> fields = Set.of("kty", "crv", "x", "kid", "use", "alg");
            for (JsonNode key : jwks.path("keys")) {
                if (!key.isObject()
                        || !Set.copyOf(key.propertyNames()).equals(fields)
                        || !"OKP".equals(key.path("kty").asString())
                        || !"Ed25519".equals(key.path("crv").asString())
                        || !"sig".equals(key.path("use").asString())
                        || !"EdDSA".equals(key.path("alg").asString())) {
                    throw new IllegalArgumentException();
                }
                String kid = strictText(key, "kid");
                byte[] raw = BASE64_URL.decode(strictText(key, "x"));
                if (raw.length != 32 || result.putIfAbsent(kid, ed25519PublicKey(raw)) != null) {
                    throw new IllegalArgumentException();
                }
            }
            return result;
        } catch (Exception exception) {
            throw ServiceAuthException.authentication("无法加载本地 Ed25519 JWKS");
        }
    }

    private static PublicKey ed25519PublicKey(byte[] raw) throws Exception {
        byte[] prefix = java.util.HexFormat.of().parseHex("302a300506032b6570032100");
        ByteArrayOutputStream encoded = new ByteArrayOutputStream(prefix.length + raw.length);
        encoded.write(prefix);
        encoded.write(raw);
        return KeyFactory.getInstance("Ed25519")
                .generatePublic(new X509EncodedKeySpec(encoded.toByteArray()));
    }

    private static String strictText(JsonNode node, String field) {
        JsonNode value = node.get(field);
        if (value == null || !value.isString() || value.asString().isBlank() || value.asString().length() > 256) {
            throw new IllegalArgumentException("服务令牌文本字段无效");
        }
        return value.asString();
    }

    private static String nullableStrictText(JsonNode node, String field) {
        JsonNode value = node.get(field);
        return value != null && value.isNull() ? null : strictText(node, field);
    }

    private static long strictLong(JsonNode node, String field) {
        JsonNode value = node.get(field);
        if (value == null || !value.isIntegralNumber() || !value.canConvertToLong()) {
            throw new IllegalArgumentException("服务令牌时间字段无效");
        }
        return value.longValue();
    }

    private static final class ArraysSupport {

        private ArraysSupport() {}

        private static boolean hasBlank(String[] values) {
            for (String value : values) {
                if (value.isBlank()) {
                    return true;
                }
            }
            return false;
        }
    }
}
