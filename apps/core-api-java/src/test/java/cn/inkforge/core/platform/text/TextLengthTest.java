package cn.inkforge.core.platform.text;

import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;

class TextLengthTest {
    @Test
    void 中文补充平面与精确空白集合保持历史兼容() {
        assertThat(TextLength.count("甲😀𠀀\n \u0085\u00a0\u1680\u2000\u200a\u2028\u2029\u202f\u205f\u3000\ufeff")).isEqualTo(3);
        assertThat(TextLength.count("\u001c\u200b")).isEqualTo(2);
        assertThat(TextLength.count("")).isZero();
    }
}
