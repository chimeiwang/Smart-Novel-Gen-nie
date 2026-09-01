package cn.inkforge.core.workflows.infrastructure;

import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.DurableAgentSchemaGate;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.workflows.application.DurableWorkflowService;
import cn.inkforge.core.workflows.application.WorkflowBillingReconciliationRepository;
import cn.inkforge.core.workflows.application.WorkflowBillingReconciliationService;
import cn.inkforge.core.workflows.application.WorkflowCallbackRepository;
import cn.inkforge.core.workflows.application.WorkflowCancellationReconciler;
import cn.inkforge.core.workflows.application.WorkflowDispatchRepository;
import cn.inkforge.core.workflows.application.WorkflowEventObserverTimeouts;
import cn.inkforge.core.workflows.application.WorkflowEventStreamRepository;
import cn.inkforge.core.workflows.application.WorkflowEventStreamService;
import cn.inkforge.core.workflows.application.WorkflowEventTailObserver;
import cn.inkforge.core.workflows.application.WorkflowExecutionCanceller;
import cn.inkforge.core.workflows.application.WorkflowExecutionSubmitter;
import cn.inkforge.core.workflows.application.WorkflowRunCancellationRepository;
import cn.inkforge.core.workflows.application.WorkflowRunCancellationService;
import cn.inkforge.core.workflows.application.WorkflowStartRepository;
import cn.inkforge.core.workflows.application.WorkflowStepDispatcher;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.protocol.WorkflowEventPayloadCodec;
import jakarta.validation.Validator;
import java.time.Clock;
import java.time.Duration;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import tools.jackson.databind.ObjectMapper;

/** 新 V2 Workflow 内核装配；schema 就绪且 route-off 时仍装配读取/收敛能力。 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        name = "DURABLE_AGENT_EXECUTION_SCHEMA_READY",
        havingValue = "true")
class WorkflowConfiguration {

    WorkflowConfiguration(DurableAgentSchemaGate ignored) {}

    @Bean
    WorkflowStartRepository workflowStartRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock coreClock,
            ObjectMapper objectMapper) {
        return new JooqWorkflowStartRepository(database, ids, coreClock, objectMapper);
    }

    @Bean
    WorkflowDispatchRepository workflowDispatchRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock coreClock,
            ObjectMapper objectMapper,
            ExecutionRegistry workflowExecutionRegistry,
            CoreSettings settings) {
        return new JooqWorkflowDispatchRepository(
                database,
                ids,
                coreClock,
                objectMapper,
                workflowExecutionRegistry,
                Duration.ofSeconds(30),
                settings.agentMaxConcurrency());
    }

    @Bean
    WorkflowCallbackRepository workflowCallbackRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock coreClock,
            ObjectMapper objectMapper,
            ExecutionRegistry workflowExecutionRegistry) {
        return new JooqWorkflowCallbackRepository(
                database,
                ids,
                coreClock,
                objectMapper,
                workflowExecutionRegistry,
                Duration.ofSeconds(30));
    }

    @Bean
    WorkflowBillingReconciliationRepository workflowBillingReconciliationRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock coreClock,
            ObjectMapper objectMapper,
            ExecutionRegistry workflowExecutionRegistry) {
        return new JooqWorkflowBillingReconciliationRepository(
                database, ids, coreClock, objectMapper, workflowExecutionRegistry);
    }

    @Bean
    WorkflowBillingReconciliationService workflowBillingReconciliationService(
            WorkflowBillingReconciliationRepository repository) {
        return new WorkflowBillingReconciliationService(repository);
    }

    @Bean
    WorkflowRunCancellationRepository workflowRunCancellationRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock coreClock,
            ObjectMapper objectMapper,
            ExecutionRegistry workflowExecutionRegistry) {
        return new JooqWorkflowRunCancellationRepository(
                database, ids, coreClock, objectMapper, workflowExecutionRegistry);
    }

    @Bean
    WorkflowRunCancellationService workflowRunCancellationService(
            WorkflowRunCancellationRepository repository,
            ObjectProvider<WorkflowExecutionCanceller> cancellers) {
        return new WorkflowRunCancellationService(
                repository, java.util.Optional.ofNullable(cancellers.getIfAvailable()), 20);
    }

    @Bean
    WorkflowCancellationReconciler workflowCancellationReconciler(
            WorkflowRunCancellationService cancellations) {
        return new WorkflowCancellationReconciler(cancellations, Duration.ofSeconds(1));
    }

    @Bean
    WorkflowEventObserverTimeouts workflowEventObserverTimeouts() {
        // 语句、TCP、observer 墙钟和停机只能从这一个配置源派生，禁止 repository 与 observer 各自漂移。
        return WorkflowEventObserverTimeouts.productionDefaults();
    }

    @Bean
    WorkflowEventStreamRepository workflowEventStreamRepository(
            CoreDatabase database,
            ObjectMapper objectMapper,
            Validator validator,
            WorkflowEventObserverTimeouts timeouts) {
        return new JooqWorkflowEventStreamRepository(
                database,
                new WorkflowEventPayloadCodec(objectMapper, validator),
                objectMapper,
                timeouts);
    }

    @Bean
    WorkflowEventTailObserver workflowEventTailObserver(
            WorkflowEventStreamRepository repository,
            WorkflowEventObserverTimeouts timeouts) {
        // 同一进程最多 256 条、每用户最多 8 条连接；每个慢连接只缓存 4 个共享事件批次。
        return new WorkflowEventTailObserver(
                repository,
                Duration.ofSeconds(1),
                100,
                256,
                8,
                4,
                timeouts);
    }

    @Bean
    WorkflowEventStreamService workflowEventStreamService(
            WorkflowEventStreamRepository repository,
            WorkflowEventTailObserver observer,
            ObjectMapper objectMapper) {
        // observer 承担共享 PostgreSQL 兜底；连接只等待有界更新并每 15 秒写无查询心跳。
        return new WorkflowEventStreamService(
                repository, observer, objectMapper, Duration.ofSeconds(15));
    }

    @Bean
    @ConditionalOnBean(WorkflowExecutionSubmitter.class)
    WorkflowStepDispatcher workflowStepDispatcher(
            WorkflowDispatchRepository repository,
            WorkflowExecutionSubmitter submitter,
            CoreSettings settings) {
        return new WorkflowStepDispatcher(
                repository,
                submitter,
                settings.agentMaxConcurrency(),
                Duration.ofSeconds(1));
    }

    @Bean
    DurableWorkflowService durableWorkflowService(WorkflowStartRepository starts) {
        return new DurableWorkflowService(starts);
    }
}
