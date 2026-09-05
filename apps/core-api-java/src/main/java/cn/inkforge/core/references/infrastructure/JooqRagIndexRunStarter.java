package cn.inkforge.core.references.infrastructure;

import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.references.application.RagIndexRunStarter;
import cn.inkforge.core.references.application.RagIndexRegistrationUnavailable;
import cn.inkforge.core.references.domain.RagJobIdentity;
import cn.inkforge.core.references.domain.RagRules;
import cn.inkforge.core.workflows.application.DurableWorkflowService;
import cn.inkforge.core.workflows.application.WorkflowEvidenceItemPlan;
import cn.inkforge.core.workflows.application.WorkflowInitialStepPlan;
import cn.inkforge.core.workflows.application.WorkflowStartPlan;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.function.Supplier;
import org.jooq.DSLContext;

/** 新有效非空代次在原资料事务中确定引擎，真正派发由原 Workflow dispatcher 承担。 */
final class JooqRagIndexRunStarter implements RagIndexRunStarter {
    private final Supplier<DurableWorkflowService> workflows;
    private final ExecutionRegistry registry;
    private final CoreSettings settings;

    JooqRagIndexRunStarter(Supplier<DurableWorkflowService> workflows, ExecutionRegistry registry, CoreSettings settings) {
        this.workflows = Objects.requireNonNull(workflows);
        this.registry = Objects.requireNonNull(registry);
        this.settings = Objects.requireNonNull(settings);
    }

    @Override
    public void bindNewGeneration(DSLContext transaction, String userId, String novelId, String referenceId,
            String content, String contentHash, OffsetDateTime generation) {
        if (!settings.ragIndexEnabled() || !settings.routesNewDurableAgentRun(userId, novelId)
                || !registry.enabledOperationKeys("rag", false).contains("rag.embedding")) return;
        DurableWorkflowService service = workflows.get();
        if (service == null) throw new RagIndexRegistrationUnavailable();
        var operation = registry.resolve("rag.embedding", false);
        Map<String, Object> input = Map.of("referenceId", referenceId, "contentHash", contentHash,
                "indexGeneration", RagJobIdentity.generationText(generation));
        Map<String, Object> context = new LinkedHashMap<>(input);
        context.put("content", content); context.put("chunkCount", RagRules.chunks(content).size());
        DurableRagIndexRun.validateContext(context, referenceId, contentHash, (String) input.get("indexGeneration"));
        Map<String, Object> fingerprint = new LinkedHashMap<>(input); fingerprint.put("novelId", novelId);
        var plan = new WorkflowStartPlan(userId, RagJobIdentity.create(referenceId, contentHash, generation).runId(),
                ExecutionCanonicalJson.sha256(fingerprint), "rag", "embedding", registry.catalogVersion(), "chat",
                novelId, null, null, "reference", referenceId, input, operation.operation().evidencePolicy(),
                List.of(new WorkflowEvidenceItemPlan("rag_embedding_context", referenceId, true, null, null,
                        null, context, null, null, Map.of("role", "rag_embedding_context"))), operation.operation().runBudget(),
                registry.freezePlan("rag.embedding", false), new WorkflowInitialStepPlan("generation", operation.operation().lane(),
                        Map.of("batchIndex", 0), operation.generatorProfile(), operation.generatorStepBudget(), operation.outputSchema()),
                null, new WorkflowStartPlan.SourceBinding(DurableRagIndexRun.SOURCE_TYPE, referenceId));
        service.startFresh(plan);
    }
}
