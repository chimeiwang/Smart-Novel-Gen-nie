package cn.inkforge.core.identity.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

class HmacSha256PhoneIdentityDigesterTest {

    @Test
    void 摘要必须稳定且不能退化为无密钥哈希或泄露密钥() {
        HmacSha256PhoneIdentityDigester first = new HmacSha256PhoneIdentityDigester(
                "test-phone-auth-hmac-secret-0000000000000001");
        HmacSha256PhoneIdentityDigester second = new HmacSha256PhoneIdentityDigester(
                "test-phone-auth-hmac-secret-0000000000000002");

        String digest = first.digest("+8613800138000");
        assertThat(digest).matches("^[0-9a-f]{64}$");
        assertThat(first.digest("+8613800138000")).isEqualTo(digest);
        assertThat(second.digest("+8613800138000")).isNotEqualTo(digest);
        assertThat(first.toString()).doesNotContain("test-phone-auth");
    }

    @Test
    void 密钥长度不足必须拒绝启动() {
        assertThatThrownBy(() -> new HmacSha256PhoneIdentityDigester("too-short"))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
