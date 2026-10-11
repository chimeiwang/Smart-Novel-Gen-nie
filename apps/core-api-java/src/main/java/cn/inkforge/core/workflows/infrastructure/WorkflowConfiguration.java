package cn.inkforge.core.workflows.infrastructure;

import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.DurableAgentSchemaGate;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.workflows.application.WorkflowBillingReconciliationRepository;
import cn.inkforge.core.workflows.application.WorkflowBillingReconciliationService;
import cn.inkforge.core.workflows.application.WorkflowEventObserverTimeouts;
import cn.inkforge.core.workflows.application.WorkflowEventStreamRepository;
import cn.inkforge.core.workflows.application.WorkflowEventStreamService;
import cn.inkforge.core.workflows.application.WorkflowEventTailObserver;
import cn.inkforge.core.workflows.application.WorkflowExecutionContextReader;
import cn.inkforge.core.workflows.protocol.WorkflowEventPayloadCodec;
import jakarta.validation.Validator;
import java.time.Clock;
import java.time.Duration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.autoconfigure.condition.ConditionalOnExpression;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import tools.jackson.databind.ObjectMapper;

/** 历史执行仅装配来源读取、事件查询和账务对账，不启动或派发模型任务。 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnExpression("${HISTORICAL_WORKFLOW_SCHEMA_READY:${DURABLE_AGENT_EXECUTION_SCHEMA_READY:false}}")
class WorkflowConfiguration {

    WorkflowConfiguration(DurableAgentSchemaGate ignored) {}

    @Bean
    WorkflowExecutionContextReader workflowExecutionContextReader(ObjectMapper objectMapper) {
        return new JooqWorkflowExecutionContextReader(objectMapper);
    }

    @Bean
    WorkflowBillingReconciliationRepository workflowBillingReconciliationRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock coreClock,
            ObjectMapper objectMapper) {
        return new JooqWorkflowBillingReconciliationRepository(
                database, ids, coreClock, objectMapper);
    }

    @Bean
    WorkflowBillingReconciliationService workflowBillingReconciliationService(
            WorkflowBillingReconciliationRepository repository) {
        return new WorkflowBillingReconciliationService(repository);
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
            WorkflowEventObserverTimeouts timeouts,
            WorkflowExecutionContextReader contexts) {
        return new JooqWorkflowEventStreamRepository(
                database,
                new WorkflowEventPayloadCodec(objectMapper, validator),
                objectMapper,
                timeouts,
                contexts);
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

}
