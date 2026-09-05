package cn.inkforge.core.writing.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.contracts.api.WritingRunV2Response;
import cn.inkforge.core.CoreApplication;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import tools.jackson.databind.ObjectMapper;

@SpringBootTest(classes = CoreApplication.class, properties = {"DATABASE_URL=false", "REDIS_URL=false"})
class WritingRunReportJsonConfigurationTest {

    @Autowired private ObjectMapper json;

    @Test
    void 实际应用Mapper仅在报告存在时输出全文并保持原可空字段() {
        WritingRunV2Response run = new WritingRunV2Response();
        var absent = json.valueToTree(run);
        assertThat(absent.has("reviewReport")).isFalse();
        assertThat(absent.has("operation")).isTrue();
        assertThat(absent.has("artifact")).isTrue();
        String report = "  审阅全文😀\r\n".repeat(10_000) + "尾部🚀";
        run.setReviewReport(report);
        assertThat(json.valueToTree(run).path("reviewReport").asText()).isEqualTo(report);
    }
}
