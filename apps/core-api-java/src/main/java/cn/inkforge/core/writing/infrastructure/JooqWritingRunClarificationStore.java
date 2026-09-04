package cn.inkforge.core.writing.infrastructure;

import cn.inkforge.contracts.api.ClarifyWritingRunRequest;
import cn.inkforge.contracts.api.WritingRunV2Response;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.platform.idempotency.CommandIdempotencyStore;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.workflows.application.WorkflowExecutionContextReader;
import cn.inkforge.core.workflows.catalog.ExecutionPlanSnapshot;
import cn.inkforge.core.workflows.catalog.WorkflowExecutionContext;
import cn.inkforge.core.workflows.domain.WorkflowIntentAnswer;
import cn.inkforge.core.workflows.domain.WorkflowIntentQuestion;
import cn.inkforge.core.workflows.domain.WorkflowMessageMetadata;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import cn.inkforge.core.writing.application.WritingRunClarificationStore;
import cn.inkforge.core.writing.application.WritingRunQueryRepository;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.jooq.DSLContext;
import org.jooq.Record;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** 同事务追加澄清回答、下一解析器和消息；不修改原问题或 Run 初始调用身份。 */
final class JooqWritingRunClarificationStore implements WritingRunClarificationStore {
    private static final TypeReference<Map<String, Object>> JSON_OBJECT = new TypeReference<>() {};
    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final ObjectMapper json;
    private final CommandIdempotencyStore idempotency;
    private final WorkflowExecutionContextReader contexts;
    private final WritingRunQueryRepository queries;

    JooqWritingRunClarificationStore(CoreDatabase database, CuidV1Generator ids, Clock clock, ObjectMapper json,
            CommandIdempotencyStore idempotency, WorkflowExecutionContextReader contexts, WritingRunQueryRepository queries) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
        this.idempotency = Objects.requireNonNull(idempotency);
        this.contexts = Objects.requireNonNull(contexts);
        this.queries = Objects.requireNonNull(queries);
    }

    @Override
    public WritingRunV2Response accept(String userId, String runId, ClarifyWritingRunRequest request) {
        WorkflowIntentAnswer answer;
        try {
            if (request == null || request.getExpectedRevision() == null) throw new IllegalArgumentException();
            answer = new WorkflowIntentAnswer(runId, request.getClientRequestId(), request.getExpectedRevision(),
                    request.getDecisionStepId(), request.getUserMessage());
        } catch (IllegalArgumentException exception) {
            throw new ApiException(422, "VALIDATION_ERROR", "澄清回答身份或完整内容无效");
        }
        return database.transactionResult(transaction -> accept(transaction, userId, answer));
    }

    private WritingRunV2Response accept(DSLContext transaction, String userId, WorkflowIntentAnswer answer) {
        transaction.execute("SELECT pg_catalog.pg_advisory_xact_lock(?)",
                CommandIdempotency.advisoryLockKey(userId, answer.clientRequestId()));
        Record run = transaction.fetchOne("""
                SELECT run.id, run."userId", run."novelId", run."chapterId", run."writingSessionId", run.workflow,
                       run.operation, run."operationCatalogVersion", run."targetType", run."targetId", run.input,
                       run."modelPolicyJson", run.status::text AS status, run.revision, run."lastEventSequence",
                       run."cancelRequestedAt", run."currentEvidenceBundleId"
                FROM public."WorkflowRun" AS run
                JOIN public."Novel" AS novel ON novel.id = run."novelId" AND novel."userId" = run."userId"
                WHERE run.id = ? AND run."engineVersion" = 2 AND run."userId" = ?
                FOR UPDATE OF run
                """, answer.runId(), userId);
        if (run == null) throw new ApiException(403, "WRITING_TASK_FORBIDDEN", "无权访问该写作任务");
        var existing = idempotency.resolve(transaction, userId, answer.clientRequestId(), answer.inputHash());
        if (existing != null) {
            if (existing.recordKind() != CommandIdempotencyStore.RecordKind.CONTROL_DECISION
                    || !"intent_clarification_answer".equals(existing.metadata().commandKind())) {
                throw CommandIdempotencyStore.reused(answer.clientRequestId());
            }
            return replay(transaction, existing.recordId(), answer);
        }

        var identity = new WorkflowExecutionContext.RunIdentity(answer.runId(), run.get("workflow", String.class),
                run.get("operation", String.class), run.get("operationCatalogVersion", String.class),
                run.get("chapterId", String.class), run.get("targetType", String.class), run.get("targetId", String.class));
        WorkflowExecutionContext context = contexts.load(transaction, identity, read(run.get("modelPolicyJson", String.class)));
        if (context.initialIntentPlan() == null || context.selection() != null) throw conflict("当前 Run 不在意图澄清阶段");
        if (!"waiting_user".equals(run.get("status", String.class)) || run.get("cancelRequestedAt") != null
                || !Integer.valueOf(answer.expectedRevision()).equals(run.get("revision", Integer.class))) {
            throw conflict("澄清决定已过期、已取消或 Run 状态已变化");
        }
        var pending = contexts.pendingClarification(transaction, answer.runId(), "waiting_user");
        if (pending == null || !answer.decisionStepId().equals(pending.getDecisionStepId())) {
            throw conflict("只能回答当前尚未处理的澄清问题");
        }
        Record questionRow = transaction.fetchOne("SELECT input, \"inputHash\" FROM public.\"WorkflowStep\" WHERE id=? AND \"runId\"=?",
                answer.decisionStepId(), answer.runId());
        WorkflowIntentQuestion question = WorkflowIntentQuestion.fromStored(read(questionRow.get("input", String.class)), questionRow.get("inputHash", String.class));
        Record bundle = transaction.fetchOne("""
                SELECT id, version, "policyVersion", "manifestSha256"
                FROM public."WorkflowEvidenceBundle" WHERE id=? AND "runId"=?
                """, question.intentEvidenceBundleId(), answer.runId());
        if (bundle == null || !context.initialIntentPlan().resolver().evidencePolicy().equals(bundle.get("policyVersion", String.class))) {
            throw invalid("澄清原始 Evidence 与冻结策略不一致");
        }
        List<Map<String, Object>> history = history(transaction, answer.runId(), question.intentEvidenceBundleId());
        if (history.size() >= context.initialIntentPlan().maxClarifications()) throw conflict("最多允许两次澄清回答");
        long resolvers = transaction.fetchOne("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\"=? AND purpose='resolve_intent'", answer.runId()).get(0, Long.class);
        boolean active = transaction.fetchExists(transaction.selectOne().from("public.\"WorkflowStep\"")
                .where("\"runId\"=? AND status IN ('pending','running')", answer.runId()));
        if (resolvers != history.size() + 1 || active) throw invalid("澄清历史与解析器数量或活动状态不一致");
        history.add(Map.of("decisionStepId", answer.decisionStepId(), "prompt", question.prompt(), "userMessage", answer.userMessage()));
        Map<String, Object> initial = read(run.get("input", String.class));
        if (!(initial.get("userInstruction") instanceof String instruction)) throw invalid("自然 Run 缺少原始完整指令");
        Map<String, Object> resolverInput = Map.of("userInstruction", instruction, "clarifications", List.copyOf(history));

        LocalDateTime now = DatabaseTimestamp.now(clock);
        int ordinal = transaction.fetchOne("SELECT COALESCE(max(ordinal),0)+1 FROM public.\"WorkflowStep\" WHERE \"runId\"=?", answer.runId()).get(0, Integer.class);
        String answerStepId = ids.next();
        String resolverId = ids.next();
        insertResolver(transaction, run, bundle, context.initialIntentPlan().resolver(), resolverInput, resolverId, ordinal + 1, now);
        long sequence = run.get("lastEventSequence", Long.class) + 1;
        Map<String, Object> event = new LinkedHashMap<>();
        event.put("stepId", answerStepId);
        event.put("fencingToken", 1);
        event.put("status", "completed");
        event.put("errorCode", null);
        transaction.execute("""
                INSERT INTO public."WorkflowEvent" (id,"runId",sequence,"eventType","payloadJson","dedupeKey","createdAt")
                VALUES (?,?,?,'step_finished',?,?,?)
                """, ids.next(), answer.runId(), sequence, canonical(event), "clarification:" + answerStepId, now);
        transaction.execute("""
                UPDATE public."WorkflowRun" SET status='pending', revision=revision+1,
                  "lastEventSequence"=?, "updatedAt"=? WHERE id=?
                """, sequence, now, answer.runId());
        // 在锁内构造权威受理快照，然后一次写入完整回执；后续重放不随新问题或终态漂移。
        WritingRunV2Response response = (WritingRunV2Response) queries.getPublic(userId, answer.runId());
        Map<String, Object> receipt = json.convertValue(response, JSON_OBJECT);
        answer.requireReceipt(receipt, ExecutionCanonicalJson.sha256(receipt));
        insertAnswer(transaction, answer, answerStepId, ordinal, question.intentEvidenceBundleId(), receipt, now);
        appendMessage(transaction, run, answer, answerStepId, now);
        return response;
    }

    private WritingRunV2Response replay(DSLContext transaction, String stepId, WorkflowIntentAnswer expected) {
        Record row = transaction.fetchOne("SELECT input, output, \"inputHash\", \"resultHash\", status::text AS status, \"fencingToken\" FROM public.\"WorkflowStep\" WHERE id=? AND \"runId\"=?", stepId, expected.runId());
        if (row == null || !"completed".equals(row.get("status", String.class)) || !Long.valueOf(1).equals(row.get("fencingToken", Long.class))) throw invalid("澄清受理回执缺少真实已完成回答");
        WorkflowIntentAnswer stored = WorkflowIntentAnswer.fromStored(read(row.get("input", String.class)), row.get("inputHash", String.class));
        if (!expected.equals(stored)) throw CommandIdempotencyStore.reused(expected.clientRequestId());
        Map<String, Object> receipt = read(row.get("output", String.class));
        stored.requireReceipt(receipt, row.get("resultHash", String.class));
        WritingRunV2Response response = json.convertValue(receipt, WritingRunV2Response.class);
        if (!Integer.valueOf(2).equals(response.getEngineVersion()) || !expected.runId().equals(response.getRunId())
                || !expected.runId().equals(response.getTaskId()) || response.getStatus() != WritingRunV2Response.StatusEnum.PENDING
                || !Integer.valueOf(expected.expectedRevision() + 1).equals(response.getRevision())) throw invalid("澄清受理回执身份无效");
        return response;
    }

    private List<Map<String, Object>> history(DSLContext transaction, String runId, String bundleId) {
        List<Map<String, Object>> result = new ArrayList<>();
        var decisions = new HashSet<String>();
        for (Record row : transaction.fetch("""
                SELECT answer.id, answer.input, answer."inputHash", question.input AS question_input,
                       question."inputHash" AS question_hash, question.ordinal AS question_ordinal, answer.ordinal
                FROM public."WorkflowStep" AS answer
                LEFT JOIN public."WorkflowStep" AS question ON question.id=answer.input::jsonb->>'decisionStepId'
                  AND question."runId"=answer."runId" AND question.purpose='intent_clarification'
                WHERE answer."runId"=? AND answer.purpose='intent_clarification_answer'
                ORDER BY answer.ordinal, answer.id
                """, runId)) {
            WorkflowIntentAnswer answer = WorkflowIntentAnswer.fromStored(read(row.get("input", String.class)), row.get("inputHash", String.class));
            // 共用回执验证，历史中的不完整决定不能被当作一次有效回答。
            replay(transaction, row.get("id", String.class), answer);
            WorkflowIntentQuestion question = WorkflowIntentQuestion.fromStored(read(row.get("question_input", String.class)), row.get("question_hash", String.class));
            if (!runId.equals(answer.runId()) || !runId.equals(question.runId()) || !bundleId.equals(question.intentEvidenceBundleId())
                    || !decisions.add(answer.decisionStepId()) || row.get("question_ordinal", Integer.class) >= row.get("ordinal", Integer.class)) {
                throw invalid("澄清回答历史的来源、顺序或唯一性无效");
            }
            result.add(Map.of("decisionStepId", answer.decisionStepId(), "prompt", question.prompt(), "userMessage", answer.userMessage()));
        }
        return result;
    }

    private void insertResolver(DSLContext transaction, Record run, Record bundle, ExecutionPlanSnapshot.Step step,
            Map<String, Object> input, String stepId, int ordinal, LocalDateTime now) {
        String runId = run.get("id", String.class);
        String key = runId + "." + stepId;
        String inputHash = ExecutionCanonicalJson.sha256(input);
        Map<String, Object> material = new LinkedHashMap<>();
        material.put("runId", runId);
        material.put("novelId", run.get("novelId", String.class));
        material.put("stepId", stepId);
        material.put("idempotencyKey", key);
        material.put("inputHash", inputHash);
        material.put("workflow", run.get("workflow", String.class));
        material.put("operation", null);
        material.put("purpose", step.purpose());
        material.put("lane", step.lane());
        material.put("evidenceManifest", Map.of("bundleId", bundle.get("id", String.class), "bundleVersion", bundle.get("version", Integer.class),
                "policyVersion", bundle.get("policyVersion", String.class), "manifestSha256", bundle.get("manifestSha256", String.class)));
        material.put("modelProfile", step.modelProfile().toMap());
        material.put("outputSchema", step.outputSchema().toMap());
        material.put("budget", step.stepBudget().budgetMap());
        material.put("artifact", null);
        transaction.execute("""
                INSERT INTO public."WorkflowStep" (id,"runId","agentId","stepType",status,input,"createdAt",ordinal,
                  purpose,lane,"attemptCount","nextAttemptAt","fencingToken","idempotencyKey","requestHash","inputHash",
                  "evidenceBundleId","modelProfile","modelProfileVersion","outputSchema","outputSchemaVersion","budgetJson","submittedAt","updatedAt")
                VALUES (?,?,?,'agent','pending',?,?,?,?,?,0,?,0,?,?,?,?,?,?,?,?,?,?,?)
                """, stepId, runId, step.modelProfile().profile(), canonical(input), now, ordinal, step.purpose(), step.lane(), now,
                key, ExecutionCanonicalJson.sha256(material), inputHash, bundle.get("id", String.class), step.modelProfile().profile(),
                Integer.toString(step.modelProfile().version()), step.outputSchema().name(), Integer.toString(step.outputSchema().version()),
                canonical(step.stepBudget().stored()), now, now);
    }

    private void insertAnswer(DSLContext transaction, WorkflowIntentAnswer answer, String id, int ordinal,
            String bundleId, Map<String, Object> receipt, LocalDateTime now) {
        transaction.execute("""
                INSERT INTO public."WorkflowStep" (id,"runId","stepType",status,input,output,"durationMs","createdAt",ordinal,
                  purpose,lane,"attemptCount","fencingToken","idempotencyKey","requestHash","inputHash","resultHash",
                  "evidenceBundleId","submittedAt","updatedAt","completedAt")
                VALUES (?,?,'user_confirmation','completed',?,?,0,?,?,'intent_clarification_answer','control',0,1,?,?,?,?,?,?,?,?)
                """, id, answer.runId(), canonical(answer.stored()), canonical(receipt), now, ordinal,
                "clarification:" + answer.clientRequestId(), answer.inputHash(), answer.inputHash(), ExecutionCanonicalJson.sha256(receipt),
                bundleId, now, now, now);
    }

    private void appendMessage(DSLContext transaction, Record run, WorkflowIntentAnswer answer, String stepId, LocalDateTime now) {
        String sessionId = run.get("writingSessionId", String.class);
        Record session = transaction.fetchOne("SELECT \"updatedAt\" FROM public.\"WritingSession\" WHERE id=? AND \"novelId\"=? AND \"chapterId\"=? FOR UPDATE",
                sessionId, run.get("novelId", String.class), run.get("chapterId", String.class));
        if (session == null) throw invalid("澄清 Run 绑定的会话不存在或目标不一致");
        String metadata = WorkflowMessageMetadata.serialize(answer.runId(), "user", answer.userMessage(), null,
                Map.of("engineVersion", 2, "runId", answer.runId(), "decisionStepId", answer.decisionStepId(), "answerStepId", stepId), json);
        transaction.execute("INSERT INTO public.\"WritingMessage\" (id,\"sessionId\",role,content,metadata,\"createdAt\") VALUES (?,?,'user',?,?,?)",
                ids.next(), sessionId, answer.userMessage(), metadata, now);
        transaction.execute("UPDATE public.\"WritingSession\" SET \"updatedAt\"=? WHERE id=?",
                DatabaseTimestamp.next(clock, session.get("updatedAt", LocalDateTime.class)), sessionId);
    }

    private Map<String, Object> read(String value) {
        if (value == null) throw invalid("澄清不可变 JSON 材料缺失");
        Map<String, Object> result = json.readValue(value, JSON_OBJECT);
        if (result == null) throw invalid("澄清不可变 JSON 材料为空");
        return result;
    }

    private static String canonical(Map<String, Object> value) { return new String(ExecutionCanonicalJson.bytes(value), StandardCharsets.UTF_8); }
    private static IllegalStateException invalid(String message) { return new IllegalStateException(message); }
    private static ApiException conflict(String message) { return new ApiException(409, "WORKFLOW_CLARIFICATION_CONFLICT", message); }
}
