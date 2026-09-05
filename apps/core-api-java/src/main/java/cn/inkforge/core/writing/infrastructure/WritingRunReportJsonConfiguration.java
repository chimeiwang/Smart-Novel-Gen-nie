package cn.inkforge.core.writing.infrastructure;

import cn.inkforge.contracts.api.WritingRunV2Response;
import com.fasterxml.jackson.annotation.JsonInclude;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import tools.jackson.databind.JacksonModule;
import tools.jackson.databind.module.SimpleModule;

/** 审阅报告是新增可选投影；其他 Run 的既有响应不补空报告字段。 */
@Configuration(proxyBeanMethods = false)
class WritingRunReportJsonConfiguration {

    @Bean
    JacksonModule writingRunReportJacksonModule() {
        return new SimpleModule("inkforge-writing-run-report")
                .setMixInAnnotation(WritingRunV2Response.class, ReportMixin.class);
    }

    abstract static class ReportMixin {
        @JsonInclude(JsonInclude.Include.NON_NULL)
        public abstract String getReviewReport();
    }
}
