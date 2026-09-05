package cn.inkforge.core.styles.infrastructure;

import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.styles.application.PortraitRunSubmitter;
import cn.inkforge.core.styles.application.PortraitTaskDispatcher;
import cn.inkforge.core.styles.application.StyleFileStorage;
import cn.inkforge.core.styles.application.StyleRepository;
import cn.inkforge.core.styles.application.StyleService;
import cn.inkforge.core.styles.application.StylePortraitExecutionReadiness;
import cn.inkforge.core.styles.application.StylePortraitRunStarter;
import cn.inkforge.core.workflows.application.DurableWorkflowService;
import cn.inkforge.core.workflows.application.WorkflowStylePortraitCompletion;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import java.time.Clock;
import java.time.Duration;
import java.util.Optional;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import tools.jackson.databind.ObjectMapper;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(name = "DATABASE_URL")
class StyleConfiguration {

    @Bean
    StyleFileStorage styleFileStorage(CoreSettings settings) {
        return new StyleStorage(settings.uploadsRoot());
    }

    @Bean
    JooqStyleRepository styleRepository(
            CoreDatabase database, CuidV1Generator ids, Clock coreClock, CoreSettings settings, ObjectMapper json) {
        return new JooqStyleRepository(database, ids, coreClock, settings.durableAgentExecutionSchemaReady(), json);
    }

    @Bean
    StyleService styleService(
            StyleRepository repository,
            StyleFileStorage storage,
            Optional<PortraitRunSubmitter> submitter,
            StylePortraitRunStarter starter) {
        return new StyleService(repository, storage, submitter.orElse(null), starter);
    }

    @Bean
    StylePortraitRunStarter stylePortraitRunStarter(CoreDatabase database, JooqStyleRepository repository,
            StyleFileStorage storage, ObjectProvider<PortraitRunSubmitter> submitters,
            ObjectProvider<DurableWorkflowService> workflows, ObjectProvider<StylePortraitExecutionReadiness> readiness,
            ExecutionRegistry registry, CoreSettings settings, CuidV1Generator ids, Clock coreClock, ObjectMapper json) {
        return new JooqStylePortraitRunStarter(database, repository, storage, submitters::getIfAvailable,
                workflows::getIfAvailable, () -> {
                    var configured = readiness.getIfAvailable();
                    return configured != null && configured.check();
                }, registry, settings, ids, coreClock, json);
    }

    @Bean
    @ConditionalOnProperty(name = "DURABLE_AGENT_EXECUTION_SCHEMA_READY", havingValue = "true")
    WorkflowStylePortraitCompletion workflowStylePortraitCompletion(CoreDatabase database, Clock coreClock, ObjectMapper json) {
        return new JooqWorkflowStylePortraitCompletion(database, coreClock, json);
    }

    @Bean
    PortraitTaskDispatcher portraitTaskDispatcher(
            StyleRepository repository,
            ObjectProvider<PortraitRunSubmitter> submitters,
            Clock coreClock) {
        // dispatcher 属于 PostgreSQL 耐久恢复能力，不能由 Agent Bean 的扫描先后决定是否存在；实际端口
        // 在每次投递时解析，未配置时只留下稳定可重试失败，StyleService 的公共 503 语义保持不变。
        return new PortraitTaskDispatcher(
                repository,
                new ProviderPortraitRunSubmitter(submitters),
                coreClock,
                20,
                Duration.ofSeconds(5),
                Duration.ofMinutes(10));
    }
}
