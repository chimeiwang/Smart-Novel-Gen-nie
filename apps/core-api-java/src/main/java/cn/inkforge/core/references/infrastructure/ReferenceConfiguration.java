package cn.inkforge.core.references.infrastructure;

import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.references.application.RagIndexSubmitter;
import cn.inkforge.core.references.application.RagIndexDispatcher;
import cn.inkforge.core.references.application.ReferenceService;
import cn.inkforge.core.references.application.RagIndexRunStarter;
import cn.inkforge.core.workflows.application.DurableWorkflowService;
import cn.inkforge.core.workflows.application.WorkflowRagIndexCompletion;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import java.time.Clock;
import java.time.Duration;
import java.util.Optional;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import tools.jackson.databind.ObjectMapper;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(name = "DATABASE_URL")
class ReferenceConfiguration {

    @Bean
    JooqReferenceRepository referenceRepository(CoreDatabase database, CuidV1Generator ids, Clock coreClock,
            CoreSettings settings, ObjectMapper json, ObjectProvider<RagIndexRunStarter> starters) {
        return new JooqReferenceRepository(database, ids, coreClock, settings.durableAgentExecutionSchemaReady(), json, starters::getIfAvailable);
    }

    @Bean
    RagIndexRunStarter ragIndexRunStarter(ObjectProvider<DurableWorkflowService> workflows, ExecutionRegistry registry, CoreSettings settings) {
        return new JooqRagIndexRunStarter(workflows::getIfAvailable, registry, settings);
    }

    @Bean
    @ConditionalOnProperty(name = "DURABLE_AGENT_EXECUTION_SCHEMA_READY", havingValue = "true")
    WorkflowRagIndexCompletion workflowRagIndexCompletion(CoreDatabase database, CuidV1Generator ids, Clock coreClock, ObjectMapper json) {
        return new JooqWorkflowRagIndexCompletion(database, ids, coreClock, json);
    }

    @Bean
    ReferenceService referenceService(
            JooqReferenceRepository repository, Optional<RagIndexSubmitter> submitter) {
        // 在 Bean 实例装配时包装原端口，不依赖跨 Configuration 的条件扫描先后。
        return new ReferenceService(repository, submitter
                .map(legacy -> (RagIndexSubmitter) new RagIndexSubmissionRouter(repository, () -> legacy)).orElse(null));
    }

    @Bean
    @ConditionalOnBean(RagIndexSubmitter.class)
    RagIndexDispatcher ragIndexDispatcher(
            JooqReferenceRepository repository, RagIndexSubmitter submitter) {
        return new RagIndexDispatcher(repository, new RagIndexSubmissionRouter(repository, () -> submitter), 20, Duration.ofSeconds(5));
    }

}
