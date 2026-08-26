package cn.inkforge.core.chapters.domain;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.stream.Stream;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class TextLengthTest {

    @ParameterizedTest
    @MethodSource("样例")
    void 必须与Web和Python共享Unicode计数规则(String value, int expected) {
        assertThat(TextLength.count(value)).isEqualTo(expected);
    }

    private static Stream<Arguments> 样例() {
        return Stream.of(
                Arguments.of("甲 乙\n丙", 3),
                Arguments.of("\u3000甲\t乙", 2),
                Arguments.of("甲\u00a0乙", 2),
                Arguments.of("甲\ufeff乙", 2),
                Arguments.of("\u0085甲", 1),
                Arguments.of("😀", 1));
    }
}
