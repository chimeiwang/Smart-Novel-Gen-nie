package cn.inkforge.core.quality.infrastructure;

import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.quality.application.QualityRepository;
import cn.inkforge.core.quality.application.QualityRunDispatcher;
import cn.inkforge.core.quality.application.QualityRunSubmitter;
import cn.inkforge.core.quality.application.QualityService;
import cn.inkforge.core.quality.application.QualityRunStarter;
import cn.inkforge.core.quality.application.QualityExecutionReadiness;
import cn.inkforge.core.workflows.application.DurableWorkflowService;
import cn.inkforge.core.workflows.application.WorkflowQualityCompletion;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import java.time.Clock;
import java.time.Duration;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import tools.jackson.databind.ObjectMapper;

/** 装配质量检查的持久化、V1 投递和 V2 耐久完成链路。 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(name = "DATABASE_URL")
class QualityConfiguration {

    @Bean
    JooqQualityRepository qualityRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock coreClock,
            ObjectMapper objectMapper,
            CoreSettings settings) {
        return new JooqQualityRepository(database, ids, coreClock, objectMapper,
                settings.durableAgentExecutionSchemaReady());
    }

    @Bean
    QualityRunDispatcher qualityRunDispatcher(
            QualityRepository repository,
            ObjectProvider<QualityRunSubmitter> submitters) {
        // 未配置 Agent 时不创建后台投递器，质量查询仍可使用数据库中的既有结果。
        QualityRunSubmitter submitter = submitters.getIfAvailable();
        if (submitter == null) return null;
        return new QualityRunDispatcher(
                repository, submitter, 20, Duration.ofSeconds(5));
    }

    @Bean
    QualityService qualityService(
            QualityRepository repository,
            ObjectProvider<QualityRunDispatcher> dispatchers,
            QualityRunStarter starter) {
        return new QualityService(repository, dispatchers.getIfAvailable(), starter);
    }

    @Bean
    QualityRunStarter qualityRunStarter(CoreDatabase database, JooqQualityRepository repository,
            ObjectProvider<QualityRunDispatcher> dispatchers,
            ObjectProvider<DurableWorkflowService> workflows,
            ObjectProvider<QualityExecutionReadiness> readiness,
            ExecutionRegistry registry, CoreSettings settings, Clock coreClock, ObjectMapper objectMapper) {
        return new JooqQualityRunStarter(database, repository, dispatchers::getIfAvailable,
                workflows::getIfAvailable, () -> {
                    var configured = readiness.getIfAvailable();
                    return configured != null && configured.check();
                }, registry, settings, coreClock, objectMapper);
    }

    @Bean
    @ConditionalOnProperty(name = "DURABLE_AGENT_EXECUTION_SCHEMA_READY", havingValue = "true")
    WorkflowQualityCompletion workflowQualityCompletion(CoreDatabase database, Clock coreClock,
            ObjectMapper objectMapper) {
        return new JooqWorkflowQualityCompletion(database, coreClock, objectMapper);
    }
}
