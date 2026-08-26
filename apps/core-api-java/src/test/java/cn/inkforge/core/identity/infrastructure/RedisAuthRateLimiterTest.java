package cn.inkforge.core.identity.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.identity.application.AuthAction;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.redis.RedisUnavailableException;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;

class RedisAuthRateLimiterTest {

    @Test
    void 限流键不得包含明文用户名且策略与重试秒数必须兼容() {
        AtomicReference<List<String>> keys = new AtomicReference<>();
        AtomicReference<List<String>> arguments = new AtomicReference<>();
        RedisAuthRateLimiter limiter = new RedisAuthRateLimiter(
                (script, capturedKeys, capturedArguments) -> {
                    assertThat(script).contains("PEXPIRE", "source_count");
                    keys.set(capturedKeys);
                    arguments.set(capturedArguments);
                    return List.of(1L, 31_000L, 6L, 6L);
                },
                "测试:认证:");

        assertThatThrownBy(() -> limiter.check(
                        AuthAction.LOGIN, "198.51.100.10", "sensitive_user"))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(429);
                    assertThat(error.code()).isEqualTo("RATE_LIMITED");
                    assertThat(error.headers()).containsEntry("Retry-After", "31");
                });
        assertThat(keys.get()).allSatisfy(key -> assertThat(key).doesNotContain("sensitive_user"));
        assertThat(arguments.get()).containsExactly("20", "60000", "5", "60000");
    }

    @Test
    void 注册使用独立策略且Redis故障必须失败关闭() {
        AtomicReference<List<String>> arguments = new AtomicReference<>();
        RedisAuthRateLimiter limiter = new RedisAuthRateLimiter(
                (script, keys, capturedArguments) -> {
                    arguments.set(capturedArguments);
                    return List.of(0L, 0L, 1L, 1L);
                },
                "测试:认证:");
        limiter.check(AuthAction.REGISTER, "198.51.100.10", "alice");
        assertThat(arguments.get()).containsExactly("3", "3600000", "3", "3600000");

        RedisAuthRateLimiter unavailable = new RedisAuthRateLimiter(
                (script, keys, values) -> {
                    throw new RedisUnavailableException();
                },
                "测试:认证:");
        assertThatThrownBy(() -> unavailable.check(AuthAction.LOGIN, "ip", "alice"))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(503);
                    assertThat(error.code()).isEqualTo("RATE_LIMIT_UNAVAILABLE");
                    assertThat(error.getMessage()).doesNotContain("Redis");
                });
    }
}
