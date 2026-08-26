package cn.inkforge.core.identity.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.platform.http.ApiException;
import org.junit.jupiter.api.Test;

class BCryptPasswordCodecTest {

    private final BCryptPasswordCodec codec = new BCryptPasswordCodec();

    @Test
    void 必须生成成本12并接受NodeBcryptjs固定哈希() {
        String hash = codec.hash("123456");

        assertThat(hash).startsWith("$2b$12$");
        assertThat(codec.matches("123456", hash)).isTrue();
        assertThat(codec.matches(
                        "a".repeat(72) + "后缀",
                        "$2b$12$abcdefghijklmnopqrstuu54EclbqC8XduEGLYgonKPRJ3bZnTXsi"))
                .isTrue();
    }

    @Test
    void 必须按UTF8前72字节保持bcryptjs历史兼容() {
        String first = "a".repeat(72) + "第一个后缀";
        String compatible = "a".repeat(72) + "另一个后缀";
        String hash = codec.hash(first);

        assertThat(codec.matches(first, hash)).isTrue();
        assertThat(codec.matches(compatible, hash)).isTrue();
    }

    @Test
    void 注册拒绝非法Unicode而登录统一按不匹配处理() {
        String unpairedSurrogate = "\ud800";

        assertThatThrownBy(() -> codec.hash(unpairedSurrogate))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(400);
                    assertThat(error.code()).isEqualTo("INVALID_PASSWORD_ENCODING");
                });
        assertThat(codec.matches(unpairedSurrogate, codec.hash("123456"))).isFalse();
        assertThat(codec.matches("123456", "不是有效哈希")).isFalse();
    }
}
