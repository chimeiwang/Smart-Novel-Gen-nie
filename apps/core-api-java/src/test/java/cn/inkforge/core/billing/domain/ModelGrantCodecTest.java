package cn.inkforge.core.billing.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.InputStream;
import java.security.KeyFactory;
import java.security.KeyPairGenerator;
import java.security.spec.EdECPrivateKeySpec;
import java.security.spec.NamedParameterSpec;
import java.time.Instant;
import java.util.HexFormat;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

class ModelGrantCodecTest {

    private static final Instant NOW = Instant.parse("2026-08-25T06:00:00Z");

    @Test
    void grant必须严格绑定完整模型调用身份并兼容三段EdDSAJWT() throws Exception {
        var keyPair = KeyPairGenerator.getInstance("Ed25519").generateKeyPair();
        ModelGrantCodec codec = new ModelGrantCodec(
                keyPair.getPrivate(), keyPair.getPublic(), new ObjectMapper());
        ModelGrantClaims claims = claims(NOW.getEpochSecond(), NOW.plusSeconds(1_200).getEpochSecond());

        String token = codec.issue(claims);
        ModelGrantClaims verified = codec.verify(token, NOW);

        assertThat(token.split("\\.")).hasSize(3);
        assertThat(verified).isEqualTo(claims);
        assertThat(token).doesNotContain("grant-secret", "password");
    }

    @Test
    void grant拒绝篡改超期未来签发和超长生命周期() throws Exception {
        var keyPair = KeyPairGenerator.getInstance("Ed25519").generateKeyPair();
        ModelGrantCodec codec = new ModelGrantCodec(
                keyPair.getPrivate(), keyPair.getPublic(), new ObjectMapper());
        String token = codec.issue(claims(
                NOW.getEpochSecond(), NOW.plusSeconds(1_200).getEpochSecond()));
        String[] parts = token.split("\\.");
        byte[] signature = java.util.Base64.getUrlDecoder().decode(parts[2]);
        signature[0] ^= 1;
        String tampered = parts[0] + "." + parts[1] + "."
                + java.util.Base64.getUrlEncoder().withoutPadding().encodeToString(signature);

        assertThatThrownBy(() -> codec.verify(tampered, NOW))
                .isInstanceOf(ModelGrantException.class);
        assertThatThrownBy(() -> codec.verify(token, NOW.plusSeconds(1_231)))
                .isInstanceOf(ModelGrantException.class);
        assertThatThrownBy(() -> codec.verify(token, NOW.minusSeconds(31)))
                .isInstanceOf(ModelGrantException.class);
        assertThatThrownBy(() -> claims(
                        NOW.getEpochSecond(), NOW.plusSeconds(1_201).getEpochSecond()))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void Java与Python模型grant必须共享逐字段和签名兼容向量() throws Exception {
        JsonNode fixture;
        try (InputStream input = getClass().getResourceAsStream(
                "/model-grant-fixtures/golden-grant.json")) {
            if (input == null) throw new IllegalStateException("缺少模型授权测试向量");
            fixture = new ObjectMapper().readTree(input);
        }
        var privateKey = KeyFactory.getInstance("Ed25519").generatePrivate(
                new EdECPrivateKeySpec(
                        NamedParameterSpec.ED25519,
                        HexFormat.of().parseHex(
                                fixture.path("testOnlyPrivateKeySeedHex").asString())));
        ModelGrantCodec codec = new ModelGrantCodec(privateKey, null, new ObjectMapper());
        JsonNode claims = fixture.path("claims");
        ModelGrantClaims expected = new ModelGrantClaims(
                claims.path("requestId").asString(),
                claims.path("taskId").asString(),
                claims.path("runId").asString(),
                claims.path("novelId").asString(),
                claims.path("userId").asString(),
                claims.path("provider").asString(),
                claims.path("model").asString(),
                claims.path("agentId").asString(),
                claims.path("maxOutputTokens").asInt(),
                claims.path("billable").asBoolean(),
                claims.path("iat").asLong(),
                claims.path("exp").asLong());

        assertThat(codec.verify(
                        fixture.path("pythonToken").asString(),
                        Instant.ofEpochSecond(1_800_000_000L)))
                .isEqualTo(expected);
        assertThat(codec.issue(expected)).isEqualTo(fixture.path("javaToken").asString());
    }

    private static ModelGrantClaims claims(long issuedAt, long expiresAt) {
        return new ModelGrantClaims(
                "request-1",
                "task-1",
                "run-1",
                "novel-1",
                "user-1",
                "openai_compatible",
                "deepseek-v4-flash",
                "写作",
                4_096,
                true,
                issuedAt,
                expiresAt);
    }
}
