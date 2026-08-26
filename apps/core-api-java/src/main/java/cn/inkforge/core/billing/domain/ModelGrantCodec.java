package cn.inkforge.core.billing.domain;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.time.Instant;
import java.util.Base64;
import java.util.Set;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

/** 严格 Ed25519 模型授权 JWT；不与浏览器会话或服务请求令牌混用。 */
public final class ModelGrantCodec {

    private static final Base64.Encoder ENCODER = Base64.getUrlEncoder().withoutPadding();
    private static final Base64.Decoder DECODER = Base64.getUrlDecoder();
    private static final Set<String> CLAIM_NAMES = Set.of(
            "requestId",
            "taskId",
            "runId",
            "novelId",
            "userId",
            "provider",
            "model",
            "agentId",
            "maxOutputTokens",
            "billable",
            "iat",
            "exp",
            "iss",
            "aud");

    private final PrivateKey privateKey;
    private final PublicKey publicKey;
    private final ObjectMapper json;

    public ModelGrantCodec(
            PrivateKey privateKey, PublicKey publicKey, ObjectMapper json) {
        this.privateKey = java.util.Objects.requireNonNull(privateKey);
        this.publicKey = publicKey;
        this.json = java.util.Objects.requireNonNull(json);
    }

    public String issue(ModelGrantClaims claims) {
        ObjectNode header = json.createObjectNode();
        header.put("alg", "EdDSA");
        header.put("typ", "JWT");
        ObjectNode payload = json.createObjectNode();
        payload.put("requestId", claims.requestId());
        payload.put("taskId", claims.taskId());
        payload.put("runId", claims.runId());
        payload.put("novelId", claims.novelId());
        payload.put("userId", claims.userId());
        payload.put("provider", claims.provider());
        payload.put("model", claims.model());
        payload.put("agentId", claims.agentId());
        payload.put("maxOutputTokens", claims.maxOutputTokens());
        payload.put("billable", claims.billable());
        payload.put("iat", claims.issuedAt());
        payload.put("exp", claims.expiresAt());
        payload.put("iss", "core-api");
        payload.put("aud", "agent-service");
        String signingInput = encode(json.writeValueAsBytes(header))
                + "."
                + encode(json.writeValueAsBytes(payload));
        return signingInput + "." + encode(sign(signingInput));
    }

    public ModelGrantClaims verify(String token, Instant now) {
        try {
            String[] parts = token.split("\\.", -1);
            if (parts.length != 3
                    || parts[0].isEmpty()
                    || parts[1].isEmpty()
                    || parts[2].isEmpty()) {
                throw new IllegalArgumentException();
            }
            JsonNode header = json.readTree(DECODER.decode(parts[0]));
            if (!header.isObject()
                    || header.size() != 2
                    || !"EdDSA".equals(text(header, "alg"))
                    || !"JWT".equals(text(header, "typ"))) {
                throw new IllegalArgumentException();
            }
            String signingInput = parts[0] + "." + parts[1];
            byte[] signature = DECODER.decode(parts[2]);
            if (!validSignature(signingInput, signature)) {
                throw new IllegalArgumentException();
            }
            JsonNode payload = json.readTree(DECODER.decode(parts[1]));
            if (!payload.isObject()
                    || payload.size() != CLAIM_NAMES.size()
                    || !payload.propertyNames().stream().collect(java.util.stream.Collectors.toSet())
                            .equals(CLAIM_NAMES)
                    || !"core-api".equals(text(payload, "iss"))
                    || !"agent-service".equals(text(payload, "aud"))) {
                throw new IllegalArgumentException();
            }
            ModelGrantClaims claims = new ModelGrantClaims(
                    text(payload, "requestId"),
                    text(payload, "taskId"),
                    text(payload, "runId"),
                    text(payload, "novelId"),
                    text(payload, "userId"),
                    text(payload, "provider"),
                    text(payload, "model"),
                    text(payload, "agentId"),
                    integer(payload, "maxOutputTokens"),
                    bool(payload, "billable"),
                    number(payload, "iat"),
                    number(payload, "exp"));
            long current = now.getEpochSecond();
            if (claims.issuedAt() > current + 30 || claims.expiresAt() < current - 30) {
                throw new IllegalArgumentException();
            }
            return claims;
        } catch (ModelGrantException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw new ModelGrantException();
        }
    }

    private boolean validSignature(String signingInput, byte[] expected) {
        try {
            if (publicKey == null) {
                return MessageDigest.isEqual(sign(signingInput), expected);
            }
            Signature verifier = Signature.getInstance("Ed25519");
            verifier.initVerify(publicKey);
            verifier.update(signingInput.getBytes(StandardCharsets.US_ASCII));
            return verifier.verify(expected);
        } catch (Exception exception) {
            throw new ModelGrantException();
        }
    }

    private byte[] sign(String signingInput) {
        try {
            Signature signer = Signature.getInstance("Ed25519");
            signer.initSign(privateKey);
            signer.update(signingInput.getBytes(StandardCharsets.US_ASCII));
            return signer.sign();
        } catch (Exception exception) {
            throw new ModelGrantException();
        }
    }

    private static String text(JsonNode node, String name) {
        JsonNode value = node.get(name);
        if (value == null || !value.isString() || value.asString().isEmpty()) {
            throw new IllegalArgumentException();
        }
        return value.asString();
    }

    private static long number(JsonNode node, String name) {
        JsonNode value = node.get(name);
        if (value == null || !value.isIntegralNumber()) {
            throw new IllegalArgumentException();
        }
        return value.asLong();
    }

    private static int integer(JsonNode node, String name) {
        long value = number(node, name);
        if (value < Integer.MIN_VALUE || value > Integer.MAX_VALUE) {
            throw new IllegalArgumentException();
        }
        return (int) value;
    }

    private static boolean bool(JsonNode node, String name) {
        JsonNode value = node.get(name);
        if (value == null || !value.isBoolean()) {
            throw new IllegalArgumentException();
        }
        return value.asBoolean();
    }

    private static String encode(byte[] value) {
        return ENCODER.encodeToString(value);
    }
}
