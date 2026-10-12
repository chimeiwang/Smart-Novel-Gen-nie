package cn.inkforge.core.workflows.infrastructure;

import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.workflows.application.WorkflowEvidenceItemPlan;
import cn.inkforge.core.workflows.application.WorkflowInitialStepPlan;
import cn.inkforge.core.workflows.application.WorkflowRunStartResult;
import cn.inkforge.core.workflows.application.WorkflowStartPlan;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.catalog.IntentExecutionPlanSnapshot;
import cn.inkforge.core.workflows.catalog.WorkflowIntentSelection;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.time.Clock;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import tools.jackson.databind.ObjectMapper;

/** 隔离审核决定层的自然 Run 起点；仅构造已完成解析事实，不替代真实入口/回答/Provider 全链验收。 */
public final class IntentSelectedRunTestFixture {
    private IntentSelectedRunTestFixture() {}

    public static WorkflowRunStartResult start(CoreDatabase database, CuidV1Generator ids, Clock clock,
            ObjectMapper json, ExecutionRegistry registry, WorkflowStartPlan business) {
        var intent = IntentExecutionPlanSnapshot.freeze(registry,
                List.of("long_serial.answer_question", "long_serial.plan_chapter", "long_serial.write_chapter"));
        var resolver = registry.resolveSystemPurpose("resolve_intent");
        var starts = new JooqWorkflowStartRepository(database, ids, clock, json);
        Map<String, Object> original = new LinkedHashMap<>(business.normalizedInput());
        original.put("userInstruction", "原始未明确的请求");
        Map<String, Object> initialInput = Map.of("userInstruction", "原始未明确的请求", "clarifications", List.of());
        var started = starts.start(new WorkflowStartPlan(business.userId(), business.clientRequestId(), business.requestHash(),
                "long_serial", null, registry.catalogVersion(), "chat", business.novelId(), business.chapterId(), business.writingSessionId(),
                "chapter", business.chapterId(), original, resolver.purpose().evidencePolicy(),
                List.of(new WorkflowEvidenceItemPlan("intent_context", business.chapterId(), true, null, DatabaseTimestamp.api(DatabaseTimestamp.now(clock)), null,
                        Map.of("workflow", "long_serial", "novelId", business.novelId(), "chapterId", business.chapterId(), "chapterTitle", "第一章",
                                "availableOperations", intent.operationPlans().stream().map(plan -> Map.of("operation", plan.operation().operation(), "description", "当前章创作操作", "targetType", "chapter", "scopeKind", "chapter")).toList()),
                        null, null, Map.of("role", "intent_context"))),
                intent.runBudget(), null, new WorkflowInitialStepPlan("resolve_intent", "interactive", initialInput,
                        resolver.modelProfile(), resolver.stepBudget(), resolver.outputSchema()), intent));
        return database.transactionResult(tx -> {
            var now = DatabaseTimestamp.now(clock);
            String intentBundle = tx.fetchOne("SELECT \"evidenceBundleId\" FROM public.\"WorkflowStep\" WHERE id = ?", started.stepId()).get(0, String.class);
            tx.execute("""
                    UPDATE public."WorkflowStep" SET status = 'completed', "completedAt" = ?, "resultHash" = ?, "usageJson" = ? WHERE id = ?
                    """, now, "a".repeat(64), json.writeValueAsString(Map.of("usageStatus", "unknown", "providerAttempts", 1, "protocolCorrections", 0, "wallTimeMillis", 1000)), started.stepId());
            var evidence = starts.appendEvidence(tx, started.runId(), 2, business.evidencePolicyVersion(), business.evidenceItems(), now);
            var selection = new WorkflowIntentSelection(started.runId(), business.executionPlan().operation().key(), business.executionPlan().sha256(),
                    started.stepId(), "a".repeat(64), intentBundle, "chapter", business.chapterId(), "chapter",
                    intent.supportsNovelScopes() ? WorkflowIntentSelection.SCHEMA_V2 : WorkflowIntentSelection.SCHEMA);
            String selectionId = ids.next();
            tx.execute("""
                    INSERT INTO public."WorkflowStep" (id, "runId", "agentId", "stepType", status, input, "createdAt", ordinal, purpose, lane,
                      "attemptCount", "fencingToken", "idempotencyKey", "requestHash", "inputHash", "evidenceBundleId", "submittedAt", "updatedAt", "completedAt")
                    VALUES (?, ?, 'core', 'persistence', 'completed', ?, ?, 2, 'intent_selection', 'control', 0, 0, ?, ?, ?, ?, ?, ?, ?)
                    """, selectionId, started.runId(), json.writeValueAsString(selection.stored()), now, started.runId() + "." + selectionId,
                    selection.inputHash(), selection.inputHash(), intentBundle, now, now, now);
            String generationId = ids.next();
            var generator = business.executionPlan().generator();
            String inputHash = ExecutionCanonicalJson.sha256(business.initialStep().input());
            Map<String, Object> material = new LinkedHashMap<>();
            material.put("runId", started.runId());
            material.put("novelId", business.novelId());
            material.put("stepId", generationId);
            material.put("idempotencyKey", started.runId() + "." + generationId);
            material.put("inputHash", inputHash);
            material.put("workflow", business.workflow());
            material.put("operation", business.operation());
            material.put("purpose", "generation");
            material.put("lane", generator.lane());
            material.put("evidenceManifest", Map.of("bundleId", evidence.id(), "bundleVersion", 2,
                    "policyVersion", generator.evidencePolicy(), "manifestSha256", evidence.manifestSha256()));
            material.put("modelProfile", generator.modelProfile().toMap());
            material.put("outputSchema", generator.outputSchema().toMap());
            material.put("budget", generator.stepBudget().budgetMap());
            material.put("artifact", null);
            tx.execute("""
                    INSERT INTO public."WorkflowStep" (id, "runId", "agentId", "stepType", status, input, "createdAt", ordinal, purpose, lane,
                      "attemptCount", "nextAttemptAt", "fencingToken", "idempotencyKey", "requestHash", "inputHash", "evidenceBundleId",
                      "modelProfile", "modelProfileVersion", "outputSchema", "outputSchemaVersion", "budgetJson", "submittedAt", "updatedAt")
                    VALUES (?, ?, ?, 'agent', 'pending', ?, ?, 3, 'generation', ?, 0, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, generationId, started.runId(), generator.modelProfile().profile(), json.writeValueAsString(business.initialStep().input()), now,
                    generator.lane(), now, started.runId() + "." + generationId, ExecutionCanonicalJson.sha256(material), inputHash, evidence.id(),
                    generator.modelProfile().profile(), Integer.toString(generator.modelProfile().version()), generator.outputSchema().name(), Integer.toString(generator.outputSchema().version()),
                    json.writeValueAsString(generator.stepBudget().stored()), now, now);
            tx.execute("UPDATE public.\"WorkflowRun\" SET \"currentEvidenceBundleId\" = ? WHERE id = ?", evidence.id(), started.runId());
            return new WorkflowRunStartResult(started.runId(), business.novelId(), business.chapterId(), business.writingSessionId(), "long_serial",
                    business.operation(), "pending", generationId, started.lastEventSequence(), started.revision(), started.createdAt(), started.updatedAt(), false);
        });
    }
}
