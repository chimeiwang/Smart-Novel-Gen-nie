package cn.inkforge.cli.transport;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.Map;
import org.junit.jupiter.api.Test;

class CoreOriginTest {

    @Test
    void 只允许回环HTTP或任意HTTPS并规范化origin() {
        assertThat(CoreOrigin.validate("http://localhost:8000/", Map.of()))
                .isEqualTo("http://localhost:8000");
        assertThat(CoreOrigin.validate("http://127.0.0.1", Map.of()))
                .isEqualTo("http://127.0.0.1");
        assertThat(CoreOrigin.validate("http://[::1]:8000", Map.of()))
                .isEqualTo("http://[::1]:8000");
        assertThat(CoreOrigin.validate("https://INKFORGE.CN:443", Map.of()))
                .isEqualTo("https://inkforge.cn:443");

        for (String invalid : new String[] {
            "http://inkforge.cn",
            "ftp://localhost",
            "https://user:pass@inkforge.cn",
            "https://inkforge.cn/api",
            "https://inkforge.cn?q=1",
            " https://inkforge.cn",
            "https://inkforge.cn#fragment"
        }) {
            assertThatThrownBy(() -> CoreOrigin.validate(invalid, Map.of()))
                    .isInstanceOf(IllegalArgumentException.class);
        }
    }

    @Test
    void 受控环境变量只能精确放行一个远程HTTPorigin() {
        Map<String, String> allowed = Map.of(
                "INKFORGE_CLI_ALLOW_INSECURE_HTTP_ORIGIN",
                "http://dev.inkforge.test:8080/");
        assertThat(CoreOrigin.validate("http://dev.inkforge.test:8080", allowed))
                .isEqualTo("http://dev.inkforge.test:8080");
        assertThatThrownBy(() -> CoreOrigin.validate(
                        "http://other.inkforge.test:8080", allowed))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
