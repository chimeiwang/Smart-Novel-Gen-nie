package cn.inkforge.core.platform.db;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.core.db.generated.Public;
import org.jooq.Table;
import org.junit.jupiter.api.Test;

class GeneratedSchemaTest {

    @Test
    void jooq代码必须覆盖冻结开发库的全部业务表() {
        assertThat(Public.PUBLIC.getTables())
                .hasSize(85)
                .extracting(Table::getName)
                .contains("User", "Novel", "Chapter", "WritingTask", "VideoEpisodeExport");
    }
}
