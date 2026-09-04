package cn.inkforge.core.workflows.infrastructure;

import cn.inkforge.contracts.api.ProposedCommand;
import com.fasterxml.jackson.annotation.JsonSetter;
import com.fasterxml.jackson.annotation.Nulls;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import tools.jackson.databind.JacksonModule;
import tools.jackson.databind.module.SimpleModule;

/** 仅拒绝意图命令参数的显式 null；缺省值仍由既有共享投影补为空对象。 */
@Configuration(proxyBeanMethods = false)
class WorkflowProposedCommandJsonConfiguration {

    @Bean
    JacksonModule workflowProposedCommandJacksonModule() {
        return new SimpleModule("inkforge-workflow-proposed-command")
                .setMixInAnnotation(ProposedCommand.class, ProposedCommandArgumentsMixin.class);
    }

    abstract static class ProposedCommandArgumentsMixin {
        @JsonSetter(value = "arguments", nulls = Nulls.FAIL)
        public abstract void setArguments(Map<String, Object> arguments);
    }
}
