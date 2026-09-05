package cn.inkforge.core.workflows.infrastructure;

import cn.inkforge.contracts.api.WorkflowClarificationSnapshot;
import cn.inkforge.core.workflows.application.WorkflowExecutionContextReader;
import cn.inkforge.core.workflows.catalog.WorkflowExecutionContext;
import cn.inkforge.core.workflows.catalog.WorkflowIntentSelection;
import cn.inkforge.core.workflows.domain.WorkflowIntentQuestion;
import cn.inkforge.core.workflows.domain.WorkflowIntentAnswer;
import cn.inkforge.core.platform.text.TextLength;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import cn.inkforge.core.workflows.protocol.ExecutionProtocolDateTime;
import java.time.LocalDateTime;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.jooq.DSLContext;
import org.jooq.Record;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** 同一事务内唯一 selection 与待澄清事实的读取，所有消费者共用相同来源校验。 */
public final class JooqWorkflowExecutionContextReader implements WorkflowExecutionContextReader {

    private static final TypeReference<Map<String, Object>> JSON_OBJECT = new TypeReference<>() {};
    private final ObjectMapper json;

    public JooqWorkflowExecutionContextReader(ObjectMapper json) {
        this.json = Objects.requireNonNull(json);
    }

    @Override
    public WorkflowExecutionContext load(DSLContext transaction, WorkflowExecutionContext.RunIdentity identity,
            Map<String, Object> initialMap) {
        List<Record> values = transaction.fetch("""
                SELECT step.id, step.input, step."inputHash", step.status::text AS status,
                       step."stepType"::text AS step_type, step.lane, step."evidenceBundleId",
                       step."modelProfile", step."modelProfileVersion", step."outputSchema", step."outputSchemaVersion",
                       step."resolvedModelJson", step."budgetJson", step."artifactId",
                       EXISTS (SELECT 1 FROM public."WorkflowBillingReservation" AS reservation
                               WHERE reservation."stepId" = step.id) AS has_reservation
                FROM public."WorkflowStep" AS step
                WHERE step."runId" = ? AND step.purpose = 'intent_selection'
                ORDER BY step.ordinal, step.id LIMIT 2
                """, identity.runId());
        if (values.size() > 1) throw invalid("同一 Run 出现重复 intent_selection，拒绝猜测有效操作");
        if (values.isEmpty()) return WorkflowExecutionContext.fromStored(initialMap, null, null, identity);
        Record value = values.getFirst();
        requireCompletedControl(value, "persistence", "intent_selection");
        Map<String, Object> input = read(value.get("input", String.class));
        WorkflowIntentSelection selection = WorkflowIntentSelection.fromStored(input, value.get("inputHash", String.class));
        WorkflowExecutionContext context = WorkflowExecutionContext.fromStored(initialMap, input,
                value.get("inputHash", String.class), identity);
        requireEvidenceView(value, selection.intentEvidenceBundleId());
        requireResolver(transaction, identity.runId(), selection.resolverStepId(), selection.resolverResultHash(),
                selection.intentEvidenceBundleId());
        if (WorkflowIntentSelection.SCHEMA_V2.equals(selection.schema())) {
            requireSelectionEvidence(transaction, context);
        }
        return context;
    }

    /** 新范围只能来自产生该选择的原始授权快照；旧 v1 的历史读取契约不在此扩大。 */
    private void requireSelectionEvidence(DSLContext transaction, WorkflowExecutionContext context) {
        WorkflowIntentSelection selection = context.selection();
        var identity = context.initialIdentity();
        List<Record> values = transaction.fetch("""
                SELECT item.id, item.ordinal, item."resourceType", item."resourceId", item.exists,
                       item."resourceRevision", item."resourceUpdatedAt", item."contentType", item."contentText",
                       item."contentJson", item."contentSha256", item."byteCount", item."rangeJson", item."metadataJson",
                       bundle.version, bundle."policyVersion", bundle."manifestJson", bundle."manifestSha256", bundle."totalBytes",
                       run."novelId", resolver."modelProfile", resolver."modelProfileVersion"
                FROM public."WorkflowEvidenceBundle" AS bundle
                JOIN public."WorkflowRun" AS run ON run.id = bundle."runId"
                JOIN public."WorkflowStep" AS resolver ON resolver.id = ? AND resolver."runId" = run.id
                JOIN public."WorkflowEvidenceItem" AS item ON item."bundleId" = bundle.id
                WHERE bundle.id = ? AND bundle."runId" = ? ORDER BY item.ordinal LIMIT 2
                """, selection.resolverStepId(), selection.intentEvidenceBundleId(), identity.runId());
        if (values.size() != 1) throw invalid("自然选择必须绑定唯一完整的 intent_context");
        Record item = values.getFirst();
        var resolver = context.initialIntentPlan().resolver();
        if (!resolver.modelProfile().profile().equals(item.get("modelProfile", String.class))
                || !Integer.toString(resolver.modelProfile().version()).equals(item.get("modelProfileVersion", String.class))
                || !resolver.evidencePolicy().equals(item.get("policyVersion", String.class))
                || !Integer.valueOf(1).equals(item.get("ordinal", Integer.class))
                || !"intent_context".equals(item.get("resourceType", String.class))
                || !identity.chapterId().equals(item.get("resourceId", String.class))
                || !Boolean.TRUE.equals(item.get("exists", Boolean.class))
                || !"json".equals(item.get("contentType", String.class))
                || item.get("contentText") != null || item.get("rangeJson") != null) {
            throw invalid("自然选择的解析器或完整来源身份不一致");
        }
        Map<String, Object> content = read(item.get("contentJson", String.class));
        long byteCount = ExecutionCanonicalJson.bytes(content).length;
        String contentHash = ExecutionCanonicalJson.sha256(content);
        if (!contentHash.equals(item.get("contentSha256", String.class))
                || !Long.valueOf(byteCount).equals(item.get("byteCount", Long.class))
                || !Long.valueOf(byteCount).equals(item.get("totalBytes", Long.class))) {
            throw invalid("自然选择的完整授权内容哈希或长度不一致");
        }
        Map<String, Object> manifestItem = new LinkedHashMap<>();
        manifestItem.put("itemId", item.get("id", String.class));
        manifestItem.put("ordinal", 1);
        manifestItem.put("resourceType", "intent_context");
        manifestItem.put("resourceId", identity.chapterId());
        manifestItem.put("exists", true);
        Integer revision = item.get("resourceRevision", Integer.class);
        if (revision != null) manifestItem.put("resourceRevision", revision);
        LocalDateTime updatedAt = item.get("resourceUpdatedAt", LocalDateTime.class);
        if (updatedAt != null) manifestItem.put("resourceUpdatedAt", ExecutionProtocolDateTime.format(DatabaseTimestamp.api(updatedAt)));
        manifestItem.put("contentType", "json");
        manifestItem.put("contentSha256", contentHash);
        manifestItem.put("byteCount", byteCount);
        manifestItem.put("metadata", read(item.get("metadataJson", String.class)));
        Integer version = item.get("version", Integer.class);
        if (version == null || version < 1) throw invalid("自然选择的授权来源版本无效");
        Map<String, Object> manifest = Map.of("bundleId", selection.intentEvidenceBundleId(), "bundleVersion", version,
                "itemCount", 1, "items", List.of(manifestItem));
        String manifestHash = ExecutionCanonicalJson.sha256(manifest);
        if (!manifestHash.equals(item.get("manifestSha256", String.class))
                || !manifestHash.equals(ExecutionCanonicalJson.sha256(read(item.get("manifestJson", String.class))))) {
            throw invalid("自然选择的授权清单与实际来源不一致");
        }
        if (!content.keySet().equals(Set.of("workflow", "novelId", "chapterId", "chapterTitle", "availableOperations"))
                || !identity.workflow().equals(content.get("workflow"))
                || item.get("novelId", String.class) == null
                || !item.get("novelId", String.class).equals(content.get("novelId"))
                || !identity.chapterId().equals(content.get("chapterId"))
                || !(content.get("chapterTitle") instanceof String)
                || !(content.get("availableOperations") instanceof List<?> available)
                || available.isEmpty() || available.size() > 10) {
            throw invalid("自然选择的冻结上下文身份或授权集合无效");
        }
        Set<String> keys = new HashSet<>();
        for (Object raw : available) {
            if (!(raw instanceof Map<?, ?> option)
                    || !option.keySet().equals(Set.of("operation", "description", "targetType", "scopeKind"))
                    || !(option.get("operation") instanceof String operation)
                    || !(option.get("description") instanceof String description) || TextLength.count(description) == 0
                    || !"chapter".equals(option.get("targetType"))) {
                throw invalid("自然选择的冻结授权项字段无效");
            }
            String key = identity.workflow() + "." + operation;
            if (!keys.add(key) || !context.initialIntentPlan().scopeKindForOperation(key).equals(option.get("scopeKind"))) {
                throw invalid("自然选择的冻结授权项重复或范围不一致");
            }
        }
        Set<String> expected = context.initialIntentPlan().operationPlans().stream().map(plan -> plan.operation().key())
                .collect(java.util.stream.Collectors.toUnmodifiableSet());
        if (!keys.equals(expected) || !keys.contains(selection.operationKey())) {
            throw invalid("自然选择必须属于完整冻结计划声明的授权集合");
        }
    }

    @Override
    public WorkflowClarificationSnapshot pendingClarification(DSLContext transaction, String runId, String status) {
        if (!"waiting_user".equals(status)) return null;
        List<Record> questions = controlFacts(transaction, runId, "intent_clarification");
        if (questions.size() > 2) throw invalid("同一 Run 的澄清问题超过冻结上限");
        Map<String, WorkflowIntentQuestion> pending = new LinkedHashMap<>();
        for (Record value : questions) {
            requireCompletedControl(value, "user_confirmation", "intent_clarification");
            WorkflowIntentQuestion question;
            try {
                question = WorkflowIntentQuestion.fromStored(read(value.get("input", String.class)), value.get("inputHash", String.class));
            } catch (IllegalArgumentException exception) {
                throw new IllegalStateException("持久化澄清问题的完整材料或来源指纹无效", exception);
            }
            if (!runId.equals(question.runId())) throw invalid("澄清问题与当前 Run 不一致");
            requireEvidenceView(value, question.intentEvidenceBundleId());
            requireResolver(transaction, runId, question.resolverStepId(), question.resolverResultHash(), question.intentEvidenceBundleId());
            pending.put(value.get("id", String.class), question);
        }
        List<Record> answers = controlFacts(transaction, runId, "intent_clarification_answer");
        if (answers.size() > 2) throw invalid("同一 Run 的澄清回答超过冻结上限");
        for (Record value : answers) {
            requireCompletedControl(value, "user_confirmation", "intent_clarification_answer");
            if (!Long.valueOf(1).equals(value.get("fencingToken", Long.class))) throw invalid("澄清回答控制事实必须冻结 fence=1");
            WorkflowIntentAnswer answer;
            Map<String, Object> receipt = read(value.get("output", String.class));
            try {
                answer = WorkflowIntentAnswer.fromStored(read(value.get("input", String.class)), value.get("inputHash", String.class));
                answer.requireReceipt(receipt, value.get("resultHash", String.class));
            } catch (IllegalArgumentException exception) {
                throw new IllegalStateException("持久化澄清回答的完整输入或冻结回执无效", exception);
            }
            WorkflowIntentQuestion question = pending.remove(answer.decisionStepId());
            if (!runId.equals(answer.runId()) || question == null || !answer.inputHash().equals(value.get("requestHash", String.class))) {
                throw invalid("澄清回答不匹配同 Run 唯一问题或原请求指纹");
            }
            requireEvidenceView(value, question.intentEvidenceBundleId());
            Object current = receipt.get("currentStep");
            String resolverId = (String) ((Map<?, ?>) current).get("stepId");
            Record resumed = transaction.fetchOne("""
                    SELECT ordinal FROM public."WorkflowStep"
                    WHERE id = ? AND "runId" = ? AND purpose = 'resolve_intent'
                    """, resolverId, runId);
            if (resumed == null || resumed.get("ordinal", Integer.class) <= value.get("ordinal", Integer.class)) {
                throw invalid("澄清回答回执未绑定随后创建的同 Run 解析器");
            }
        }
        if (pending.size() > 1) throw invalid("同一 Run 存在多个未回答澄清，拒绝猜测当前问题");
        if (pending.isEmpty()) return null;
        var entry = pending.entrySet().iterator().next();
        return new WorkflowClarificationSnapshot(entry.getValue().clarificationCode(), entry.getKey(), entry.getValue().prompt());
    }

    private static List<Record> controlFacts(DSLContext transaction, String runId, String purpose) {
        return transaction.fetch("""
                SELECT step.id, step.input, step."inputHash", step."requestHash", step.output, step."resultHash",
                       step.ordinal, step."fencingToken", step.status::text AS status,
                       step."stepType"::text AS step_type, step.lane, step."evidenceBundleId",
                       step."modelProfile", step."modelProfileVersion", step."outputSchema", step."outputSchemaVersion",
                       step."resolvedModelJson", step."budgetJson", step."artifactId",
                       EXISTS (SELECT 1 FROM public."WorkflowBillingReservation" AS reservation
                               WHERE reservation."stepId" = step.id) AS has_reservation
                FROM public."WorkflowStep" AS step
                WHERE step."runId" = ? AND step.purpose = ?
                ORDER BY step.ordinal, step.id LIMIT 3
                """, runId, purpose);
    }

    private static void requireCompletedControl(Record value, String stepType, String purpose) {
        if (!"completed".equals(value.get("status", String.class)) || !stepType.equals(value.get("step_type", String.class))
                || !"control".equals(value.get("lane", String.class)) || Boolean.TRUE.equals(value.get("has_reservation", Boolean.class))) {
            throw invalid(purpose + " 必须是已完成且无计费的控制事实");
        }
        for (String field : List.of("modelProfile", "modelProfileVersion", "outputSchema", "outputSchemaVersion",
                "resolvedModelJson", "budgetJson", "artifactId")) {
            if (value.get(field) != null) throw invalid(purpose + " 不得夹带模型、预算或 Artifact 身份");
        }
    }

    private static void requireEvidenceView(Record value, String evidenceBundleId) {
        String bound = value.get("evidenceBundleId", String.class);
        if (bound != null && !bound.equals(evidenceBundleId)) throw invalid("控制事实的 Evidence 绑定不一致");
    }

    private static void requireResolver(DSLContext transaction, String runId, String resolverStepId,
            String resultHash, String evidenceBundleId) {
        Record resolver = transaction.fetchOne("""
                SELECT step.status::text AS status, step.purpose, step."resultHash", step."evidenceBundleId"
                FROM public."WorkflowStep" AS step
                JOIN public."WorkflowEvidenceBundle" AS bundle ON bundle.id = step."evidenceBundleId" AND bundle."runId" = step."runId"
                WHERE step.id = ? AND step."runId" = ?
                """, resolverStepId, runId);
        if (resolver == null || !"completed".equals(resolver.get("status", String.class))
                || !"resolve_intent".equals(resolver.get("purpose", String.class))
                || !resultHash.equals(resolver.get("resultHash", String.class))
                || !evidenceBundleId.equals(resolver.get("evidenceBundleId", String.class))) {
            throw invalid("意图控制事实未绑定同 Run 已完成的 resolver 结果与 Evidence");
        }
    }

    private Map<String, Object> read(String serialized) {
        try {
            Map<String, Object> value = json.readValue(serialized, JSON_OBJECT);
            if (value == null) throw invalid("意图控制事实输入不能为空");
            return value;
        } catch (RuntimeException exception) {
            throw new IllegalStateException("意图控制事实输入不是完整 JSON 对象", exception);
        }
    }

    private static IllegalStateException invalid(String message) { return new IllegalStateException(message); }
}
