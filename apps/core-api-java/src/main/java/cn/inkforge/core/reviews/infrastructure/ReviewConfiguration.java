package cn.inkforge.core.reviews.infrastructure;

import cn.inkforge.core.lore.application.LoreRepository;
import cn.inkforge.core.outlines.application.OutlineRepository;
import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.references.application.ReferenceRepository;
import cn.inkforge.core.reviews.application.AgentUpdatesExecutor;
import cn.inkforge.core.reviews.application.AgentUpdatesMaterializer;
import cn.inkforge.core.reviews.application.AgentUpdatesEvidenceReader;
import cn.inkforge.core.workflows.application.WorkflowStructuredCandidatePreparation;
import cn.inkforge.core.reviews.application.ChapterPlanEvidenceReader;
import cn.inkforge.core.reviews.application.ChapterWritingEvidenceReader;
import cn.inkforge.core.reviews.application.FormalArtifactWriter;
import cn.inkforge.core.reviews.application.ReviewRepository;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.application.WorkflowExecutionContextReader;
import java.time.Clock;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import tools.jackson.databind.ObjectMapper;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(name = "DATABASE_URL")
class ReviewConfiguration {

    @Bean
    AgentUpdatesEvidenceReader agentUpdatesEvidenceReader(ObjectMapper json) {
        return new JooqAgentUpdatesEvidenceReader(json);
    }

    @Bean
    WorkflowStructuredCandidatePreparation structuredCandidatePreparation(ObjectMapper json) {
        return (tx, user, novel, run, bundle, artifact, revision, output) -> AgentUpdatesMaterializer.materialize(
                user, novel, artifact, revision, output, DurableAgentUpdatesReviewEvidence.readSources(tx, json, run, bundle, novel));
    }

    @Bean
    ChapterPlanEvidenceReader chapterPlanEvidenceReader(ObjectMapper objectMapper) {
        return new JooqChapterPlanEvidenceReader(objectMapper);
    }

    @Bean
    ChapterWritingEvidenceReader chapterWritingEvidenceReader(
            ObjectMapper objectMapper, ChapterPlanEvidenceReader chapterPlanningSources) {
        return new JooqChapterWritingEvidenceReader(objectMapper, chapterPlanningSources);
    }

    @Bean
    AgentUpdatesExecutor agentUpdatesExecutor(
            LoreRepository lore,
            OutlineRepository outlines,
            ReferenceRepository references,
            CuidV1Generator ids,
            CoreSettings settings) {
        return new AgentUpdatesExecutor(
                lore, outlines, references, ids, settings.ragIndexEnabled());
    }

    @Bean
    FormalArtifactWriter formalArtifactWriter(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock coreClock,
            ObjectMapper objectMapper,
            AgentUpdatesExecutor updates) {
        return new JooqFormalArtifactWriter(
                database, ids, coreClock, objectMapper, updates);
    }

    @Bean
    ReviewRepository reviewRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock coreClock,
            ObjectMapper objectMapper,
            FormalArtifactWriter formalWriter,
            ObjectProvider<ExecutionRegistry> workflowExecutionRegistries,
            ObjectProvider<WorkflowExecutionContextReader> workflowExecutionContexts,
            CoreSettings settings) {
        ExecutionRegistry workflowExecutionRegistry =
                settings.durableAgentExecutionSchemaReady()
                        ? workflowExecutionRegistries.getIfAvailable()
                        : null;
        if (settings.durableAgentExecutionSchemaReady()
                && workflowExecutionRegistry == null) {
            throw new IllegalStateException("耐久 Agent 数据库结构已就绪但执行 Registry 未装配");
        }
        WorkflowExecutionContextReader executionContexts = settings.durableAgentExecutionSchemaReady()
                ? workflowExecutionContexts.getIfAvailable() : null;
        if (settings.durableAgentExecutionSchemaReady() && executionContexts == null) {
            throw new IllegalStateException("耐久 Agent 数据库结构已就绪但执行上下文 Reader 未装配");
        }
        return new JooqReviewRepository(
                database,
                ids,
                coreClock,
                objectMapper,
                formalWriter,
                workflowExecutionRegistry,
                settings.durableAgentExecutionSchemaReady(), executionContexts);
    }
}
