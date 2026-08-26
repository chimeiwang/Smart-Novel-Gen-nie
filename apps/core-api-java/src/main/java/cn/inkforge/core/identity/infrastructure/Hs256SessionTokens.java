package cn.inkforge.core.identity.infrastructure;

import cn.inkforge.core.identity.domain.InvalidSessionTokenException;
import cn.inkforge.core.identity.domain.SessionTokens;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Clock;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

/** 无额外 JWT 依赖的严格 HS256 实现，可读取历史 Node jose/Python PyJWT Cookie。 */
public final class Hs256SessionTokens implements SessionTokens {

    public static final int SESSION_MAX_AGE_SECONDS = SessionTokens.SESSION_MAX_AGE_SECONDS;
    private static final int MAX_TOKEN_LENGTH = 16 * 1024;
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final Base64.Encoder ENCODER = Base64.getUrlEncoder().withoutPadding();
    private static final Base64.Decoder DECODER = Base64.getUrlDecoder();

    private final byte[] secret;
    private final Clock clock;

    public Hs256SessionTokens(String secret, Clock clock) {
        if (secret == null || secret.isBlank()) {
            throw new IllegalArgumentException("会话签名密钥不能为空");
        }
        this.secret = secret.getBytes(StandardCharsets.UTF_8);
        this.clock = java.util.Objects.requireNonNull(clock);
    }

    @Override
    public String create(String userId) {
        if (userId == null || userId.isBlank()) {
            throw new IllegalArgumentException("会话用户标识不能为空");
        }
        long issuedAt = clock.instant().getEpochSecond();
        ObjectNode header = JSON.createObjectNode();
        header.put("alg", "HS256");
        header.put("typ", "JWT");
        ObjectNode payload = JSON.createObjectNode();
        payload.put("sub", userId);
        payload.put("iat", issuedAt);
        payload.put("exp", issuedAt + SESSION_MAX_AGE_SECONDS);
        String signingInput = encode(JSON.writeValueAsBytes(header))
                + "."
                + encode(JSON.writeValueAsBytes(payload));
        return signingInput + "." + encode(hmac(signingInput));
    }

    @Override
    public String verify(String token) {
        try {
            if (token == null || token.isBlank() || token.length() > MAX_TOKEN_LENGTH) {
                throw new InvalidSessionTokenException();
            }
            String[] parts = token.split("\\.", -1);
            if (parts.length != 3 || parts[0].isBlank() || parts[1].isBlank() || parts[2].isBlank()) {
                throw new InvalidSessionTokenException();
            }
            byte[] suppliedSignature = DECODER.decode(parts[2]);
            byte[] expectedSignature = hmac(parts[0] + "." + parts[1]);
            if (!MessageDigest.isEqual(suppliedSignature, expectedSignature)) {
                throw new InvalidSessionTokenException();
            }
            JsonNode header = JSON.readTree(DECODER.decode(parts[0]));
            if (!header.isObject()
                    || !"HS256".equals(header.path("alg").asString())
                    || header.has("typ") && !"JWT".equals(header.path("typ").asString())) {
                throw new InvalidSessionTokenException();
            }
            JsonNode payload = JSON.readTree(DECODER.decode(parts[1]));
            JsonNode subject = payload.get("sub");
            JsonNode issuedAt = payload.get("iat");
            JsonNode expiresAt = payload.get("exp");
            if (!payload.isObject()
                    || subject == null
                    || !subject.isString()
                    || subject.asString().isEmpty()
                    || !integral(issuedAt)
                    || !integral(expiresAt)) {
                throw new InvalidSessionTokenException();
            }
            long now = clock.instant().getEpochSecond();
            if (issuedAt.longValue() > now || expiresAt.longValue() <= now) {
                throw new InvalidSessionTokenException();
            }
            return subject.asString();
        } catch (InvalidSessionTokenException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw new InvalidSessionTokenException();
        }
    }

    private byte[] hmac(String value) {
        try {
            Mac hmac = Mac.getInstance("HmacSHA256");
            hmac.init(new SecretKeySpec(secret, "HmacSHA256"));
            return hmac.doFinal(value.getBytes(StandardCharsets.US_ASCII));
        } catch (Exception exception) {
            throw new IllegalStateException("JVM 不支持 HmacSHA256", exception);
        }
    }

    private static boolean integral(JsonNode value) {
        return value != null && value.isIntegralNumber() && value.canConvertToLong();
    }

    private static String encode(byte[] value) {
        return ENCODER.encodeToString(value);
    }
}
