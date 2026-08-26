package cn.inkforge.core.video.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.platform.http.ApiException;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class ProviderAssetTokenCodecTest {

    private static final String SECRET = "0123456789abcdef0123456789abcdef";
    private static final String SHA256 = "a".repeat(64);
    private static final Instant NOW = Instant.parse("2026-08-25T05:20:00Z");
    private static final String PYTHON_TOKEN =
            "eyJhc3NldElkIjoiYXNzZXRfMDEiLCJleHAiOjE3ODc2MzU4MDAsInNoYTI1NiI6ImFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWEifQ.y4lYm5vDNFIQ2QAix151qZ5n8b0vrMJ0QCvgDEL1RpM";

    @Test
    void 与Python令牌完全兼容并验签() {
        ProviderAssetTokenCodec codec = codec(NOW);

        assertThat(codec.encode("asset_01", SHA256)).isEqualTo(PYTHON_TOKEN);
        ProviderAssetGrant grant = codec.decode(PYTHON_TOKEN);
        assertThat(grant.assetId()).isEqualTo("asset_01");
        assertThat(grant.sha256()).isEqualTo(SHA256);
        assertThat(grant.expiresAt()).isEqualTo(Instant.ofEpochSecond(1_787_635_800));
    }

    @Test
    void 篡改和过期令牌都只暴露404() {
        assertCode(
                () -> codec(NOW).decode(PYTHON_TOKEN.substring(0, PYTHON_TOKEN.length() - 1) + "x"),
                "VIDEO_PROVIDER_ASSET_TOKEN_INVALID");
        assertCode(
                () -> codec(Instant.ofEpochSecond(1_787_635_800)).decode(PYTHON_TOKEN),
                "VIDEO_PROVIDER_ASSET_TOKEN_EXPIRED");
    }

    private static ProviderAssetTokenCodec codec(Instant now) {
        return new ProviderAssetTokenCodec(
                SECRET,
                Duration.ofMinutes(10),
                Clock.fixed(now, ZoneOffset.UTC),
                new ObjectMapper());
    }

    private static void assertCode(Runnable action, String code) {
        assertThatThrownBy(action::run)
                .isInstanceOfSatisfying(ApiException.class, exception -> {
                    assertThat(exception.statusCode()).isEqualTo(404);
                    assertThat(exception.code()).isEqualTo(code);
                });
    }
}
