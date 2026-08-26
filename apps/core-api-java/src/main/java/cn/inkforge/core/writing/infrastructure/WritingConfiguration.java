package cn.inkforge.core.writing.infrastructure;

import cn.inkforge.core.novels.application.NovelRepository;
import cn.inkforge.core.outlines.application.OutlineRepository;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.idempotency.CommandIdempotencyStore;
import cn.inkforge.core.platform.redis.CoreRedis;
import cn.inkforge.core.references.application.ReferenceRepository;
import cn.inkforge.core.reviews.application.ReviewRepository;
import cn.inkforge.core.writing.application.WritingCallbackRepository;
import cn.inkforge.core.writing.application.WritingCallbackService;
import cn.inkforge.core.writing.application.WritingCommandDispatchRepository;
import cn.inkforge.core.writing.application.WritingCommandRepository;
import cn.inkforge.core.writing.application.WritingCommandSubmitter;
import cn.inkforge.core.writing.application.WritingContextProvider;
import cn.inkforge.core.writing.application.WritingContextRepository;
import cn.inkforge.core.writing.application.WritingContextService;
import cn.inkforge.core.writing.application.WritingEventStore;
import cn.inkforge.core.writing.application.WritingEventStreamService;
import cn.inkforge.core.writing.application.WritingForeshadowingReader;
import cn.inkforge.core.writing.application.WritingOutboxPublisher;
import cn.inkforge.core.writing.application.WritingOutboxReadiness;
import cn.inkforge.core.writing.application.WritingOutboxRepository;
import cn.inkforge.core.writing.application.WritingReadToolArguments;
import cn.inkforge.core.writing.application.WritingReadToolService;
import cn.inkforge.core.writing.application.WritingReconciliationRepository;
import cn.inkforge.core.writing.application.WritingReviewArtifactReader;
import cn.inkforge.core.writing.application.WritingRunCommandDispatcher;
import cn.inkforge.core.writing.application.WritingRunQueryRepository;
import cn.inkforge.core.writing.application.WritingRunReconciler;
import cn.inkforge.core.writing.application.WritingRunService;
import cn.inkforge.core.writing.application.WritingRunStartRequestParser;
import cn.inkforge.core.writing.application.WritingSemanticReferenceReader;
import cn.inkforge.core.writing.application.WritingSessionRepository;
import cn.inkforge.core.writing.application.WritingSessionService;
import cn.inkforge.core.writing.application.WritingToolGateway;
import cn.inkforge.core.writing.application.WritingWorkspaceReader;
import cn.inkforge.core.writing.domain.WritingRunCursor;
import cn.inkforge.core.writing.domain.WritingRunOutcomeProjector;
import cn.inkforge.core.writing.domain.WritingRunStatusProjector;
import jakarta.validation.Validator;
import java.time.Clock;
import java.time.Duration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import tools.jackson.databind.ObjectMapper;

/**
 * 写作运行的装配根。
 *
 * <p>数据库存在时始终装配耐久命令、查询和对账；只有显式配置 Redis 才装配事件、回调、Outbox 发布和 SSE。
 * Agent submitter 通过 {@link ObjectProvider} 在调用时解析，避免同一配置类中条件 Bean 的解析顺序让最小健康
 * 上下文启动失败。
 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(name = "DATABASE_URL")
class WritingConfiguration {

    @Bean
    WritingSessionRepository writingSessionRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock coreClock,
            ObjectMapper objectMapper) {
        return new JooqWritingSessionRepository(database, ids, coreClock, objectMapper);
    }

    @Bean
    WritingSessionService writingSessionService(WritingSessionRepository repository) {
        return new WritingSessionService(repository);
    }

    @Bean
    WritingRunStartRequestParser writingRunStartRequestParser(
            ObjectMapper objectMapper, Validator validator) {
        return new WritingRunStartRequestParser(objectMapper, validator);
    }

    @Bean
    WritingRunStatusProjector writingRunStatusProjector(
            ObjectMapper objectMapper, Clock coreClock) {
        return new WritingRunStatusProjector(
                objectMapper, new WritingRunOutcomeProjector(), coreClock);
    }

    @Bean
    WritingRunQueryRepository writingRunQueryRepository(
            CoreDatabase database,
            WritingRunStatusProjector projector,
            ObjectMapper objectMapper) {
        return new JooqWritingRunQueryRepository(
                database, projector, new WritingRunCursor(objectMapper));
    }

    @Bean
    WritingCommandRepository writingCommandRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock coreClock,
            ObjectMapper objectMapper) {
        return new JooqWritingCommandRepository(
                database,
                ids,
                coreClock,
                objectMapper,
                new CommandIdempotencyStore(objectMapper));
    }

    @Bean
    WritingCommandDispatchRepository writingCommandDispatchRepository(
            CoreDatabase database, Clock coreClock, ObjectMapper objectMapper) {
        return new JooqWritingCommandDispatchRepository(
                database, coreClock, objectMapper);
    }

    @Bean
    WritingRunCommandDispatcher writingRunCommandDispatcher(
            WritingCommandDispatchRepository repository,
            ObjectProvider<WritingCommandSubmitter> submitters,
            Clock coreClock) {
        // 每轮最多领取 20 条；2 秒轮询用于低延迟，10 分钟 submitted 租约允许进程重启后安全补投。
        return new WritingRunCommandDispatcher(
                repository,
                new ProviderWritingCommandSubmitter(submitters),
                coreClock,
                20,
                Duration.ofSeconds(2),
                Duration.ofMinutes(10));
    }

    @Bean
    WritingReconciliationRepository writingReconciliationRepository(
            CoreDatabase database, Clock coreClock, ObjectMapper objectMapper) {
        return new JooqWritingReconciliationRepository(database, coreClock, objectMapper);
    }

    @Bean
    WritingRunReconciler writingRunReconciler(
            WritingReconciliationRepository repository,
            WritingRunCommandDispatcher dispatcher) {
        // 对账只补齐 20 条持久缺口，30 秒节奏避免在 Redis 故障时形成数据库热循环。
        return new WritingRunReconciler(
                repository, dispatcher, 20, Duration.ofSeconds(30));
    }

    @Bean
    WritingCallbackRepository writingCallbackRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock coreClock,
            ObjectMapper objectMapper) {
        return new JooqWritingCallbackRepository(
                database, ids, coreClock, objectMapper);
    }

    @Bean
    WritingOutboxRepository writingOutboxRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock coreClock,
            ObjectMapper objectMapper) {
        return new JooqWritingOutboxRepository(
                database, ids, coreClock, objectMapper);
    }

    @Bean
    @ConditionalOnProperty(name = "REDIS_URL")
    WritingEventStore writingEventStore(
            CoreRedis redis, Clock coreClock, ObjectMapper objectMapper) {
        return new RedisWritingEventStore(redis, coreClock, objectMapper);
    }

    @Bean
    @ConditionalOnProperty(name = "REDIS_URL")
    WritingCallbackService writingCallbackService(
            WritingCallbackRepository repository,
            WritingEventStore eventStore,
            ObjectMapper objectMapper) {
        return new WritingCallbackService(repository, eventStore, objectMapper);
    }

    @Bean
    @ConditionalOnProperty(name = "REDIS_URL")
    WritingOutboxPublisher writingOutboxPublisher(
            WritingOutboxRepository repository,
            WritingEventStore eventStore,
            Clock coreClock) {
        // 20 条批量、30 秒租约、1 秒基础退避；发布一小时仍未成功由 readiness 明确报警。
        return new WritingOutboxPublisher(
                repository,
                eventStore,
                coreClock,
                20,
                30,
                Duration.ofSeconds(1),
                Duration.ofHours(1));
    }

    @Bean
    WritingOutboxReadiness writingOutboxReadiness(
            WritingOutboxRepository repository, Clock coreClock) {
        return new WritingOutboxReadiness(
                repository, coreClock, Duration.ofMinutes(5));
    }

    @Bean
    WritingRunService writingRunService(
            WritingRunStartRequestParser parser,
            WritingCommandRepository commands,
            WritingRunQueryRepository queries,
            WritingRunCommandDispatcher dispatcher) {
        return new WritingRunService(parser, commands, queries, dispatcher);
    }

    @Bean
    @ConditionalOnProperty(name = "REDIS_URL")
    WritingEventStreamService writingEventStreamService(
            WritingRunQueryRepository queries,
            WritingEventStore eventStore,
            WritingOutboxRepository outbox,
            ObjectMapper objectMapper) {
        // 1 秒用于断流后权威 outcome 对账，15 秒心跳用于穿过代理空闲超时；都不代表任务完成。
        return new WritingEventStreamService(
                queries,
                eventStore,
                outbox,
                objectMapper,
                Duration.ofSeconds(1),
                Duration.ofSeconds(15));
    }

    @Bean
    WritingContextRepository writingContextRepository(
            CoreDatabase database, ObjectMapper objectMapper) {
        return new JooqWritingContextRepository(database, objectMapper);
    }

    @Bean
    WritingWorkspaceReader writingWorkspaceReader(
            NovelRepository novels, ObjectMapper objectMapper) {
        return new RepositoryWritingWorkspaceReader(novels, objectMapper);
    }

    @Bean
    WritingContextProvider writingContextProvider(
            WritingContextRepository planning, WritingWorkspaceReader workspace) {
        return new WritingContextService(planning, workspace);
    }

    @Bean
    WritingForeshadowingReader writingForeshadowingReader(
            OutlineRepository outlines, ObjectMapper objectMapper) {
        return new RepositoryWritingForeshadowingReader(outlines, objectMapper);
    }

    @Bean
    WritingReviewArtifactReader writingReviewArtifactReader(
            ReviewRepository reviews, ObjectMapper objectMapper) {
        return new RepositoryWritingReviewArtifactReader(reviews, objectMapper);
    }

    @Bean
    WritingSemanticReferenceReader writingSemanticReferenceReader(
            ReferenceRepository references) {
        return new RepositoryWritingSemanticReferenceReader(references);
    }

    @Bean
    WritingReadToolService writingReadToolService(
            WritingContextProvider context,
            WritingForeshadowingReader foreshadowings,
            WritingReviewArtifactReader reviews,
            WritingSemanticReferenceReader references,
            ObjectMapper objectMapper) {
        return new WritingReadToolService(
                context, foreshadowings, reviews, references, objectMapper);
    }

    @Bean
    WritingToolGateway writingToolGateway(
            WritingContextRepository authorizer,
            WritingContextProvider context,
            WritingReadToolService readTools) {
        // 注册表是 Agent 可调用能力的唯一入口；每次执行仍由 authorizer 复核 task/user/novel 绑定。
        WritingToolGateway gateway = new WritingToolGateway(authorizer);
        gateway.register(
                "get_writing_context",
                WritingReadToolArguments.ALL_AGENT_IDS,
                true,
                request -> context.build(request.userId(), request.taskId()));
        WritingReadToolArguments.register(gateway, readTools);
        return gateway;
    }
}
