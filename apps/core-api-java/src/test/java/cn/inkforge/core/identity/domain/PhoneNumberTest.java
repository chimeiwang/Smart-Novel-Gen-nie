package cn.inkforge.core.identity.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

class PhoneNumberTest {

    @Test
    void 大陆手机号必须规范化为E164并只展示脱敏值() {
        PhoneNumber phone = PhoneNumber.mainland("13800138000");

        assertThat(phone.national()).isEqualTo("13800138000");
        assertThat(phone.e164()).isEqualTo("+8613800138000");
        assertThat(phone.masked()).isEqualTo("138****8000");
    }

    @Test
    void 拒绝国家码空白和非法号段() {
        assertThatThrownBy(() -> PhoneNumber.mainland("+8613800138000"))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> PhoneNumber.mainland("12800138000"))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> PhoneNumber.mainland(" 13800138000 "))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
