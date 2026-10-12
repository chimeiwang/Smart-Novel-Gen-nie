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
import cn.inkforge.core.workflows.application.WorkflowEvidenceItemPlan;
import cn.inkforge.contracts.api.EvidenceExpansionRequest;
import cn.inkforge.core.reviews.application.ChapterPlanEvidenceReader;
import cn.inkforge.core.reviews.application.ChapterWritingEvidenceReader;
import cn.inkforge.core.reviews.application.FormalArtifactWriter;
import cn.inkforge.core.reviews.application.ReviewRepository;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.application.WorkflowExecutionContextReader;
import java.time.Clock;
import java.util.List;
import java.util.Map;
import org.jooq.DSLContext;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import tools.jackson.databind.ObjectMapper;

/** 装配草案重建、冻结证据读取和正式采用所需的审核端口。 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(name = "DATABASE_URL")
class ReviewConfiguration {

    @Bean
    AgentUpdatesEvidenceReader agentUpdatesEvidenceReader(ObjectMapper json) {
        return new JooqAgentUpdatesEvidenceReader(json);
    }

    @Bean
    WorkflowStructuredCandidatePreparation structuredCandidatePreparation(ObjectMapper json) {
        var expansion = new JooqAgentUpdatesEvidenceExpansion(json, new JooqAgentUpdatesEvidenceReader(json));
        return new WorkflowStructuredCandidatePreparation() {
            @Override
            public void validate(DSLContext tx, String user, String novel, String run, String bundle,
                    String artifact, int revision, Map<String, Object> output) {
                AgentUpdatesMaterializer.materialize(user, novel, artifact, revision, output,
                        DurableAgentUpdatesReviewEvidence.readSources(tx, json, run, bundle, novel));
            }

            @Override
            public List<WorkflowEvidenceItemPlan> expand(DSLContext tx, String user, String novel, String run,
                    String bundle, EvidenceExpansionRequest request) {
                return expansion.expand(tx, user, novel, run, bundle, request);
            }
        };
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
