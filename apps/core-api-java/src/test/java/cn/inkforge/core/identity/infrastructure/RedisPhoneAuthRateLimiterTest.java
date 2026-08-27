package cn.inkforge.core.identity.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.redis.RedisUnavailableException;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class RedisPhoneAuthRateLimiterTest {

    @Test
    void 两阶段六个限流键不得包含来源或手机号且策略参数必须冻结() {
        List<List<String>> capturedKeys = new ArrayList<>();
        List<List<String>> capturedArguments = new ArrayList<>();
        RedisPhoneAuthRateLimiter limiter = new RedisPhoneAuthRateLimiter(
                (script, keys, arguments) -> {
                    assertThat(script).contains("china_day", "day_ttl");
                    capturedKeys.add(keys);
                    capturedArguments.add(arguments);
                    return keys.getFirst().contains("phone:")
                            ? List.of(1L, 61_000L, 2L, 2L, 2L)
                            : List.of(0L, 0L, 1L, 1L, 1L);
                },
                "测试:手机号:",
                value -> {
                    assertThat(value).isEqualTo("source" + '\0' + "198.51.100.10");
                    return "c".repeat(64);
                });

        limiter.checkHumanVerification("198.51.100.10");
        assertThatThrownBy(() -> limiter.checkPhoneSend("a".repeat(64)))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.code()).isEqualTo("PHONE_RATE_LIMITED");
                    assertThat(error.headers()).containsEntry("Retry-After", "61");
                });

        assertThat(capturedKeys).hasSize(2);
        assertThat(capturedKeys.stream().flatMap(List::stream).toList())
                .hasSize(6)
                .allSatisfy(key -> assertThat(key)
                        .doesNotContain("198.51.100.10")
                        .doesNotContain("13800138000"));
        assertThat(capturedArguments)
                .containsExactly(
                        List.of("5", "20", "50", "60000", "3600000"),
                        List.of("1", "5", "10", "60000", "3600000"));
    }

    @Test
    void Redis故障必须失败关闭() {
        RedisPhoneAuthRateLimiter limiter = new RedisPhoneAuthRateLimiter(
                (script, keys, arguments) -> {
                    throw new RedisUnavailableException();
                },
                "测试:手机号:",
                value -> "b".repeat(64));

        assertThatThrownBy(() -> limiter.checkHumanVerification("ip"))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(503);
                    assertThat(error.code()).isEqualTo("PHONE_RATE_LIMIT_UNAVAILABLE");
                    assertThat(error.getMessage()).doesNotContain("Redis");
                });
    }
}
