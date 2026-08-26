package cn.inkforge.core.identity.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.identity.domain.InvalidSessionTokenException;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class Hs256SessionTokensTest {

    private static final String KEY = "测试专用会话密钥-长度足够";
    private static final Instant NOW = Instant.ofEpochSecond(1_700_000_000L);

    @Test
    void 新令牌必须只包含HS256主体签发和三十天过期声明() {
        Hs256SessionTokens tokens = tokens();

        String token = tokens.create("user-1");
        String[] parts = token.split("\\.");
        String header = decode(parts[0]);
        String payload = decode(parts[1]);

        assertThat(header).contains("\"alg\":\"HS256\"", "\"typ\":\"JWT\"");
        assertThat(payload).contains(
                "\"sub\":\"user-1\"",
                "\"iat\":1700000000",
                "\"exp\":1702592000");
        assertThat(payload).doesNotContain("iss", "aud", "jti");
        assertThat(tokens.verify(token)).isEqualTo("user-1");
    }

    @Test
    void 必须接受历史NodeJose令牌并拒绝篡改过期与非字符串主体() {
        Hs256SessionTokens legacy = new Hs256SessionTokens(
                KEY, Clock.fixed(Instant.ofEpochSecond(1_800_000_000L), ZoneOffset.UTC));
        String fixture = "eyJhbGciOiJIUzI1NiJ9."
                + "eyJzdWIiOiJsZWdhY3ktdXNlciIsImlhdCI6MTcwMDAwMDAwMCwiZXhwIjo0MTAyNDQ0ODAwfQ."
                + "g4qCrC8KNtFeH0fwQQEvn2TFb-V1mXpEPwePYy5NRUg";

        assertThat(legacy.verify(fixture)).isEqualTo("legacy-user");
        assertThatThrownBy(() -> legacy.verify(fixture.substring(0, fixture.length() - 1) + "A"))
                .isInstanceOf(InvalidSessionTokenException.class);

        String expired = tokens().create("user-1");
        Hs256SessionTokens future = new Hs256SessionTokens(
                KEY, Clock.fixed(NOW.plusSeconds(Hs256SessionTokens.SESSION_MAX_AGE_SECONDS + 1L), ZoneOffset.UTC));
        assertThatThrownBy(() -> future.verify(expired))
                .isInstanceOf(InvalidSessionTokenException.class);
    }

    private Hs256SessionTokens tokens() {
        return new Hs256SessionTokens(KEY, Clock.fixed(NOW, ZoneOffset.UTC));
    }

    private String decode(String value) {
        return new String(
                java.util.Base64.getUrlDecoder().decode(value),
                java.nio.charset.StandardCharsets.UTF_8);
    }
}
