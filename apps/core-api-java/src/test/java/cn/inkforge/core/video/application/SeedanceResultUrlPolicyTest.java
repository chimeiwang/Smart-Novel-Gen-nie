package cn.inkforge.core.video.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import org.junit.jupiter.api.Test;

class SeedanceResultUrlPolicyTest {

    @Test
    void 只接受后缀下的HTTPS子域名() {
        assertThat(SeedanceResultUrlPolicy.requireAllowed(
                                "https://media.example.volces.com/result.mp4?token=x",
                                List.of(".volces.com"))
                        .toString())
                .isEqualTo("https://media.example.volces.com/result.mp4?token=x");

        assertCode("https://volces.com/result.mp4", "SEEDANCE_RESULT_HOST_FORBIDDEN");
        assertCode("https://evilvolces.com/result.mp4", "SEEDANCE_RESULT_HOST_FORBIDDEN");
    }

    @Test
    void 拒绝明文凭据与IP地址() {
        assertCode("http://media.example.volces.com/result.mp4", "SEEDANCE_RESULT_URL_INVALID");
        assertCode(
                "https://user:secret@media.example.volces.com/result.mp4",
                "SEEDANCE_RESULT_URL_INVALID");
        assertThatThrownBy(() -> SeedanceResultUrlPolicy.requireAllowed(
                        "https://127.0.0.1/result.mp4", List.of(".0.0.1")))
                .isInstanceOfSatisfying(IllegalArgumentException.class, exception ->
                        assertThat(exception.getMessage())
                                .isEqualTo("SEEDANCE_RESULT_URL_IP_FORBIDDEN"));
    }

    private static void assertCode(String url, String code) {
        assertThatThrownBy(() ->
                        SeedanceResultUrlPolicy.requireAllowed(url, List.of(".volces.com")))
                .isInstanceOfSatisfying(IllegalArgumentException.class, exception ->
                        assertThat(exception.getMessage()).isEqualTo(code));
    }
}
