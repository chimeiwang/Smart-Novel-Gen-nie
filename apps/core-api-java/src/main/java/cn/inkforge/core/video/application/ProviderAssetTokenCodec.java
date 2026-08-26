package cn.inkforge.core.video.application;

import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import java.nio.charset.StandardCharsets;
import java.security.InvalidKeyException;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Pattern;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/** 与 Python Core 完全同构的 HMAC-SHA256 供应商素材短时令牌。 */
public final class ProviderAssetTokenCodec {

    private static final Base64.Encoder ENCODER = Base64.getUrlEncoder().withoutPadding();
    private static final Base64.Decoder DECODER = Base64.getUrlDecoder();
    private static final Pattern SHA256 = Pattern.compile("[0-9a-f]{64}");
    private static final Set<String> PAYLOAD_FIELDS = Set.of("assetId", "sha256", "exp");

    private final byte[] secret;
    private final Duration lifetime;
    private final Clock clock;
    private final ObjectMapper json;

    public ProviderAssetTokenCodec(
            String secret, Duration lifetime, Clock clock, ObjectMapper json) {
        if (secret == null
                || secret.getBytes(StandardCharsets.UTF_8).length < 32
                || lifetime == null
                || lifetime.isZero()
                || lifetime.isNegative()) {
            throw new IllegalArgumentException("供应商素材令牌配置无效");
        }
        this.secret = secret.getBytes(StandardCharsets.UTF_8).clone();
        this.lifetime = lifetime;
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
    }

    public String encode(String assetId, String sha256) {
        Objects.requireNonNull(assetId);
        Objects.requireNonNull(sha256);
        byte[] payload = CommandIdempotency.canonicalJsonBytes(
                Map.of(
                        "assetId", assetId,
                        "sha256", sha256,
                        "exp", clock.instant().plus(lifetime).getEpochSecond()),
                json);
        String encoded = ENCODER.encodeToString(payload);
        return encoded + "." + ENCODER.encodeToString(sign(encoded));
    }

    public ProviderAssetGrant decode(String token) {
        try {
            String[] parts = token == null ? new String[0] : token.split("\\.", -1);
            if (parts.length != 2 || parts[0].isEmpty() || parts[1].isEmpty()) {
                throw new IllegalArgumentException();
            }
            byte[] actualSignature = DECODER.decode(parts[1]);
            if (!MessageDigest.isEqual(actualSignature, sign(parts[0]))) {
                throw new IllegalArgumentException();
            }
            JsonNode payload = json.readTree(DECODER.decode(parts[0]));
            if (!payload.isObject()
                    || payload.size() != PAYLOAD_FIELDS.size()
                    || !payload.propertyNames().stream()
                            .collect(java.util.stream.Collectors.toSet())
                            .equals(PAYLOAD_FIELDS)) {
                throw new IllegalArgumentException();
            }
            String assetId = text(payload, "assetId");
            String sha256 = text(payload, "sha256");
            if (!SHA256.matcher(sha256).matches()) throw new IllegalArgumentException();
            JsonNode expiryValue = payload.get("exp");
            if (expiryValue == null || !expiryValue.isIntegralNumber()) {
                throw new IllegalArgumentException();
            }
            Instant expiresAt = Instant.ofEpochSecond(expiryValue.asLong());
            if (!expiresAt.isAfter(clock.instant())) {
                throw new ApiException(
                        404,
                        "VIDEO_PROVIDER_ASSET_TOKEN_EXPIRED",
                        "供应商素材地址已过期");
            }
            return new ProviderAssetGrant(assetId, sha256, expiresAt);
        } catch (ApiException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw new ApiException(
                    404,
                    "VIDEO_PROVIDER_ASSET_TOKEN_INVALID",
                    "供应商素材地址无效或已过期");
        }
    }

    private byte[] sign(String encodedPayload) {
        try {
            Mac hmac = Mac.getInstance("HmacSHA256");
            hmac.init(new SecretKeySpec(secret, "HmacSHA256"));
            return hmac.doFinal(encodedPayload.getBytes(StandardCharsets.US_ASCII));
        } catch (NoSuchAlgorithmException | InvalidKeyException exception) {
            throw new IllegalStateException("JVM 不支持 HMAC-SHA256", exception);
        }
    }

    private static String text(JsonNode node, String name) {
        JsonNode value = node.get(name);
        if (value == null || !value.isString() || value.asString().isEmpty()) {
            throw new IllegalArgumentException();
        }
        return value.asString();
    }
}
