package cn.inkforge.core.workflows.infrastructure;

import cn.inkforge.contracts.api.WorkflowClarificationSnapshot;
import cn.inkforge.core.workflows.application.WorkflowExecutionContextReader;
import cn.inkforge.core.workflows.catalog.WorkflowExecutionContext;
import cn.inkforge.core.workflows.catalog.WorkflowIntentSelection;
import cn.inkforge.core.workflows.domain.WorkflowIntentQuestion;
import cn.inkforge.core.workflows.domain.WorkflowIntentAnswer;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
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
        return context;
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
