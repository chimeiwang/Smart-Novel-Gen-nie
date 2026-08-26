package cn.inkforge.core.platform.id;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.HashSet;
import org.junit.jupiter.api.Test;

class CuidV1GeneratorTest {

    @Test
    void 必须保持PrismaCuidV1布局长度字符集和进程内唯一性() {
        CuidV1Generator generator = new CuidV1Generator(
                Clock.fixed(Instant.ofEpochMilli(1_780_000_000_000L), ZoneOffset.UTC));
        HashSet<String> values = new HashSet<>();

        for (int index = 0; index < 10_000; index++) {
            String value = generator.next();
            assertThat(value).matches("^c[a-z0-9]{24}$");
            values.add(value);
        }
        assertThat(values).hasSize(10_000);
    }
}
