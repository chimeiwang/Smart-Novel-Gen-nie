package cn.inkforge.core.reviews.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;

import cn.inkforge.contracts.api.ArtifactDecisionPublicResponse;
import cn.inkforge.contracts.api.ReviewArtifactDecisionRequest;
import cn.inkforge.contracts.api.WorkflowArtifactSnapshot;
import cn.inkforge.contracts.api.WorkflowCurrentStepSnapshot;
import cn.inkforge.contracts.api.WritingRunV2Response;
import cn.inkforge.core.db.generated.tables.records.ChapterRecord;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.idempotency.CommandIdempotencyStore;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.reviews.application.FormalArtifactWriter;
import cn.inkforge.core.reviews.application.ReviewArtifactState;
import cn.inkforge.core.reviews.domain.ReviewArtifactRules;
import cn.inkforge.core.reviews.domain.ReviewDecisionIdentity;
import cn.inkforge.core.workflows.catalog.ExecutionPlanSnapshot;
import cn.inkforge.core.workflows.catalog.WorkflowStepSnapshotFactory;
import cn.inkforge.core.workflows.domain.DurableSelectionArtifact;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.jooq.DSLContext;
import org.jooq.Record;
import org.openapitools.jackson.nullable.JsonNullable;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** V2 Artifact 决定的 Run 权威单事务实现。 */
final class JooqDurableReviewDecisionStore {

    private static final String DECISION_KEY_PREFIX = "decision:";
    private static final TypeReference<Map<String, Object>> JSON_OBJECT =
            new TypeReference<>() {};

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final ObjectMapper json;
    private final WorkflowStepSnapshotFactory stepSnapshots;
    private final FormalArtifactWriter formalWriter;
    private final CommandIdempotencyStore globalIdempotency;

    JooqDurableReviewDecisionStore(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock clock,
            ObjectMapper json,
            FormalArtifactWriter formalWriter) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
        this.stepSnapshots = new WorkflowStepSnapshotFactory(json);
        this.formalWriter = Objects.requireNonNull(formalWriter);
        this.globalIdempotency = new CommandIdempotencyStore(json, true);
    }

    ArtifactDecisionPublicResponse replay(
            DSLContext transaction,
            String userId,
            String clientRequestId,
            String requestHash) {
        List<Record> values = transaction.fetch(
                """
                SELECT step."requestHash", step.output
                FROM public."WorkflowStep" AS step
                JOIN public."WorkflowRun" AS run ON run.id = step."runId"
                WHERE run."engineVersion" = 2 AND run."userId" = ?
                  AND step."stepType" = CAST('user_confirmation' AS "WorkflowStepType")
                  AND step.purpose = 'user_decision' AND step."idempotencyKey" = ?
                """,
                userId,
                decisionKey(clientRequestId));
        if (values.isEmpty()) return null;
        if (values.size() != 1) throw reused(clientRequestId);
        Record value = values.getFirst();
        if (!Objects.equals(requestHash, value.get("requestHash", String.class))) {
            throw reused(clientRequestId);
        }
        String output = value.get("output", String.class);
        if (output == null) throw invalidReceipt();
        try {
            WritingRunV2Response response = json.readValue(output, WritingRunV2Response.class);
            if (response.getEngineVersion() != 2) throw invalidReceipt();
            return response;
        } catch (ApiException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw invalidReceipt();
        }
    }

    ArtifactDecisionPublicResponse decide(
            DSLContext transaction,
            String userId,
            String artifactId,
            ReviewArtifactDecisionRequest request,
            ReviewDecisionIdentity identity) {
        requireV2RequestShape(request);
        // V1 Command、V2 Run 创建与 V2 决定共用用户级 clientRequestId 命名空间。
        if (globalIdempotency.resolve(
                        transaction,
                        userId,
                        request.getClientRequestId(),
                        identity.fingerprint())
                != null) {
            throw reused(request.getClientRequestId());
        }

        Locked locked = lockScope(
                transaction, userId, artifactId, request.getExpectedRevision());
        requireActionable(locked, request.getExpectedRevision());
        ExecutionPlanSnapshot executionPlan = executionPlan(locked.run());
        requireSupported(locked, executionPlan);
        Source source = lockAndVerifySource(transaction, locked);
        Revision revision = exactRevision(locked, source);
        LocalDateTime now = DatabaseTimestamp.now(clock);
        String decision = request.getDecision().getValue();

        if ("approve".equals(decision)) {
            Revision applied = editedRevision(
                    transaction,
                    locked,
                    revision,
                    source,
                    nullable(request.getEditedReplacement()),
                    now);
            String decisionStepId = insertDecisionStep(
                    transaction, locked, applied, request, identity, now);
            long sequence = appendEvent(
                    transaction,
                    locked.runId(),
                    locked.lastEventSequence(),
                    "applying",
                    Map.of(
                            "artifactId", artifactId,
                            "artifactRevision", applied.number(),
                            "decisionStepId", decisionStepId),
                    "decision:applying:" + decisionStepId,
                    now);
            transitionArtifact(transaction, artifactId, "awaiting_user", "applying", now, false);
            formalWriter.apply(
                    userId,
                    new ReviewArtifactState(
                            artifactId,
                            locked.novelId(),
                            locked.chapterId(),
                            null,
                            locked.artifactKey(),
                            locked.kind(),
                            applied.number(),
                            applied.payload()),
                    request);
            transitionArtifact(transaction, artifactId, "applying", "applied", now, true);
            sequence = appendEvent(
                    transaction,
                    locked.runId(),
                    sequence,
                    "completed",
                    Map.of(
                            "outcomeType", "artifact_applied",
                            "artifactId", artifactId,
                            "artifactRevision", applied.number()),
                    "decision:completed:" + decisionStepId,
                    now);
            completeRun(transaction, locked.runId(), sequence, now);
            WritingRunV2Response response = snapshot(transaction, locked.runId());
            saveDecisionReceipt(transaction, decisionStepId, response);
            return response;
        }

        String decisionStepId = insertDecisionStep(
                transaction, locked, revision, request, identity, now);
        if ("discard".equals(decision)) {
            // 现有 enum 没有 discarded；draft 作为保留审计事实但不再进入待确认托盘的只读 head。
            transitionArtifact(transaction, artifactId, "awaiting_user", "draft", now, false);
            long sequence = appendEvent(
                    transaction,
                    locked.runId(),
                    locked.lastEventSequence(),
                    "completed",
                    Map.of(
                            "outcomeType", "artifact_discarded",
                            "artifactId", artifactId,
                            "artifactRevision", revision.number()),
                    "decision:completed:" + decisionStepId,
                    now);
            // V2 discard 只终结 Run；Artifact、Revision、Evaluation 都保持原样可审计。
            completeRun(transaction, locked.runId(), sequence, now);
            WritingRunV2Response response = snapshot(transaction, locked.runId());
            saveDecisionReceipt(transaction, decisionStepId, response);
            return response;
        }

        transitionArtifact(transaction, artifactId, "awaiting_user", "draft", now, false);
        insertRevisionGenerationStep(
                transaction, locked, executionPlan, revision, request, now);
        transaction.execute(
                """
                UPDATE public."WorkflowRun"
                SET status = CAST('running' AS "WorkflowRunStatus"),
                    revision = revision + 1, "updatedAt" = ?, "errorCode" = NULL,
                    "completedAt" = NULL
                WHERE id = ?
                """,
                now,
                locked.runId());
        WritingRunV2Response response = snapshot(transaction, locked.runId());
        saveDecisionReceipt(transaction, decisionStepId, response);
        return response;
    }

    /** 统一锁顺序：Run → Artifact → 精确 Revision；来源 Chapter 在随后单独锁定。 */
    private Locked lockScope(
            DSLContext transaction,
            String userId,
            String artifactId,
            int expectedRevision) {
        Record identity = transaction.fetchOne(
                "SELECT \"workflowRunId\" FROM public.\"ReviewArtifact\" WHERE id = ?",
                artifactId);
        String runId = identity == null
                ? null
                : identity.get("workflowRunId", String.class);
        if (runId == null) throw forbidden();
        Record run = transaction.fetchOne(
                """
                SELECT id, "userId", "novelId", "chapterId", workflow, operation,
                       "operationCatalogVersion", "modelPolicyJson",
                       status::text AS status, "currentEvidenceBundleId",
                       "lastEventSequence", revision, "cancelRequestedAt"
                FROM public."WorkflowRun"
                WHERE id = ? AND "engineVersion" = 2
                FOR UPDATE
                """,
                runId);
        if (run == null || !userId.equals(run.get("userId", String.class))) {
            throw forbidden();
        }
        Record artifact = transaction.fetchOne(
                """
                SELECT id, "workflowRunId", "novelId", "chapterId", "taskId",
                       "artifactKey", kind::text AS kind, status::text AS status,
                       revision, "payloadJson", "diffJson"
                FROM public."ReviewArtifact"
                WHERE id = ? AND "workflowRunId" = ?
                FOR UPDATE
                """,
                artifactId,
                runId);
        if (artifact == null) throw forbidden();
        Record revision = transaction.fetchOne(
                """
                SELECT id, "artifactId", revision, summary, "payloadJson", "diffJson",
                       "createdByAgent", "createdAt"
                FROM public."ReviewArtifactRevision"
                WHERE "artifactId" = ? AND revision = ?
                FOR UPDATE
                """,
                artifactId,
                expectedRevision);
        if (revision == null) throw revisionConflict(expectedRevision, artifact.get("revision", Integer.class));
        return new Locked(run, artifact, revision);
    }

    private static void requireActionable(Locked locked, int expectedRevision) {
        String runStatus = locked.run().get("status", String.class);
        if (List.of("completed", "failed", "cancelled").contains(runStatus)) {
            throw new ApiException(
                    409,
                    "RUN_TERMINAL",
                    "工作流已经终结，不能再次提交草案决定",
                    Map.of("runId", locked.runId(), "status", runStatus));
        }
        if (!"waiting_user".equals(runStatus)
                || locked.run().get("cancelRequestedAt", LocalDateTime.class) != null) {
            throw new ApiException(
                    409, "RUN_NOT_WAITING_USER", "工作流当前不接受草案决定");
        }
        int currentRevision = locked.artifact().get("revision", Integer.class);
        if (currentRevision != expectedRevision) {
            throw revisionConflict(expectedRevision, currentRevision);
        }
        if (!"awaiting_user".equals(locked.artifact().get("status", String.class))) {
            throw new ApiException(
                    409, "ARTIFACT_NOT_AWAITING_USER", "当前草案状态不能接受用户决定");
        }
    }

    private static void requireSupported(
            Locked locked, ExecutionPlanSnapshot executionPlan) {
        boolean supported = "long_serial".equals(locked.run().get("workflow", String.class))
                && "rewrite_chapter_selection"
                        .equals(locked.run().get("operation", String.class))
                && "chapter_draft".equals(locked.kind())
                && locked.artifact().get("taskId", String.class) == null
                && Objects.equals(
                        locked.run().get("novelId", String.class),
                        locked.artifact().get("novelId", String.class))
                && Objects.equals(
                        locked.run().get("chapterId", String.class),
                        locked.artifact().get("chapterId", String.class))
                && "long_serial.rewrite_chapter_selection"
                        .equals(executionPlan.operation().key())
                && "apply.chapter_selection.v1"
                        .equals(executionPlan.operation().applyHandler());
        if (!supported) {
            throw new ApiException(
                    409,
                    "DURABLE_ARTIFACT_KIND_NOT_ENABLED",
                    "该 V2 草案类型尚未开放用户决定");
        }
    }

    private Source lockAndVerifySource(DSLContext transaction, Locked locked) {
        String bundleId = locked.run().get("currentEvidenceBundleId", String.class);
        if (bundleId == null) throw sourceConflict(locked.chapterId());
        Record evidence = transaction.fetchOne(
                """
                SELECT item.id, item."resourceId", item."resourceUpdatedAt", item."contentText",
                       item."contentSha256", item."rangeJson", item."metadataJson"
                FROM public."WorkflowEvidenceItem" AS item
                JOIN public."WorkflowEvidenceBundle" AS bundle
                  ON bundle.id = item."bundleId"
                WHERE bundle.id = ? AND bundle."runId" = ?
                  AND item."resourceType" = 'chapter_content'
                  AND item."resourceId" = ? AND item.exists
                  AND item."contentType" = 'text'
                """,
                bundleId,
                locked.runId(),
                locked.chapterId());
        if (evidence == null) throw sourceConflict(locked.chapterId());
        ChapterRecord chapter = transaction.selectFrom(CHAPTER)
                .where(
                        CHAPTER.ID.eq(locked.chapterId()),
                        CHAPTER.NOVELID.eq(locked.novelId()))
                .forUpdate()
                .fetchOne();
        if (chapter == null || chapter.getContent() == null || chapter.getUpdatedat() == null) {
            throw sourceConflict(locked.chapterId());
        }
        String current = chapter.getContent();
        LocalDateTime evidenceUpdatedAt = evidence.get("resourceUpdatedAt", LocalDateTime.class);
        String evidenceHash = evidence.get("contentSha256", String.class);
        Map<String, Object> range = readObject(evidence.get("rangeJson", String.class));
        int start = integer(range, "startCodePoint");
        int end = integer(range, "endCodePoint");
        int length = ReviewArtifactRules.codePointLength(current);
        if (!Objects.equals(chapter.getUpdatedat(), evidenceUpdatedAt)
                || !Objects.equals(ReviewArtifactRules.sha256(current), evidenceHash)
                || start < 0
                || end <= start
                || end > length) {
            throw sourceConflict(locked.chapterId());
        }
        String selected = ReviewArtifactRules.slice(current, start, end);
        String selectedHash = ReviewArtifactRules.sha256(selected);
        Map<String, Object> metadata = readObject(evidence.get("metadataJson", String.class));
        if (!Objects.equals(metadata.get("baseContentHash"), evidenceHash)
                || !Objects.equals(metadata.get("selectedTextHash"), selectedHash)
                || !Objects.equals(evidence.get("contentText", String.class), current)) {
            throw sourceConflict(locked.chapterId());
        }
        return new Source(
                bundleId,
                evidence.get("id", String.class),
                locked.chapterId(),
                current,
                chapter.getUpdatedat(),
                evidenceHash,
                start,
                end,
                selected,
                selectedHash,
                ReviewArtifactRules.slice(current, 0, start),
                ReviewArtifactRules.slice(current, end, length));
    }

    private Revision exactRevision(Locked locked, Source source) {
        Map<String, Object> storedPayload = readObject(
                locked.revision().get("payloadJson", String.class));
        Map<String, Object> storedDiff = readObject(
                locked.revision().get("diffJson", String.class));
        Map<String, Object> headPayload = readObject(
                locked.artifact().get("payloadJson", String.class));
        Map<String, Object> headDiff = readObject(
                locked.artifact().get("diffJson", String.class));
        if (!storedPayload.equals(headPayload) || !storedDiff.equals(headDiff)) {
            throw new ApiException(
                    409,
                    "ARTIFACT_REVISION_HEAD_INCONSISTENT",
                    "待审核草案 head 与精确修订事实不一致");
        }
        DurableSelectionArtifact.Materialized materialized =
                DurableSelectionArtifact.reconstruct(
                        storedPayload, storedDiff, durableEvidence(source));
        requireCandidate(
                materialized.payload(),
                materialized.diff(),
                locked.chapterId(),
                source);
        return new Revision(
                locked.revision().get("revision", Integer.class),
                materialized.payload(),
                materialized.diff(),
                storedPayload,
                storedDiff);
    }

    private Revision editedRevision(
            DSLContext transaction,
            Locked locked,
            Revision base,
            Source source,
            String editedReplacement,
            LocalDateTime now) {
        if (editedReplacement == null) return base;
        if (editedReplacement.isBlank()) {
            throw new ApiException(
                    422, "VALIDATION_ERROR", "V2 editedReplacement 不能为空白");
        }
        String candidate = source.prefix() + editedReplacement + source.suffix();
        DurableSelectionArtifact.Stored stored = DurableSelectionArtifact.withCandidateHash(
                DurableSelectionArtifact.edit(
                        new DurableSelectionArtifact.Stored(
                                base.storedPayload(), base.storedDiff()),
                        editedReplacement),
                ReviewArtifactRules.sha256(candidate));
        DurableSelectionArtifact.Materialized materialized =
                DurableSelectionArtifact.reconstruct(
                        stored.payload(), stored.diff(), durableEvidence(source));
        requireCandidate(
                materialized.payload(),
                materialized.diff(),
                locked.chapterId(),
                source);

        int revision = Math.addExact(base.number(), 1);
        transaction.execute(
                """
                INSERT INTO public."ReviewArtifactRevision" (
                  id, "artifactId", revision, summary, "payloadJson", "diffJson",
                  "createdByAgent", "createdAt"
                ) VALUES (?, ?, ?, '用户编辑后批准', ?, ?, '用户', ?)
                """,
                ids.next(),
                locked.artifactId(),
                revision,
                canonicalJson(stored.payload()),
                canonicalJson(stored.diff()),
                now);
        int changed = transaction.execute(
                """
                UPDATE public."ReviewArtifact"
                SET revision = ?, "payloadJson" = ?, "diffJson" = ?,
                    "updatedByAgent" = '用户', "updatedAt" = ?
                WHERE id = ? AND revision = ? AND status = CAST('awaiting_user' AS "ReviewArtifactStatus")
                """,
                revision,
                canonicalJson(stored.payload()),
                canonicalJson(stored.diff()),
                now,
                locked.artifactId(),
                base.number());
        if (changed != 1) throw revisionConflict(base.number(), revision);
        return new Revision(
                revision,
                materialized.payload(),
                materialized.diff(),
                stored.payload(),
                stored.diff());
    }

    private static DurableSelectionArtifact.Evidence durableEvidence(Source source) {
        return new DurableSelectionArtifact.Evidence(
                source.bundleId(),
                source.itemId(),
                "chapter_content",
                source.resourceId(),
                DatabaseTimestamp.api(source.updatedAt()),
                source.content(),
                source.contentHash(),
                source.start(),
                source.end());
    }

    private static void requireCandidate(
            Map<String, Object> payload,
            Map<String, Object> diff,
            String chapterId,
            Source source) {
        Map<String, Object> target = map(payload.get("target"), "target");
        String replacement = string(payload, "replacement");
        String candidate = source.prefix() + replacement + source.suffix();
        boolean valid = "chapter_draft".equals(payload.get("kind"))
                && "replace_selection".equals(target.get("mode"))
                && "chapter_content".equals(target.get("resourceType"))
                && chapterId.equals(target.get("resourceId"))
                && "chapter_content".equals(payload.get("resourceType"))
                && chapterId.equals(payload.get("resourceId"))
                && timestampEquals(payload.get("baseUpdatedAt"), source.updatedAt())
                && source.contentHash().equals(payload.get("baseContentHash"))
                && Integer.valueOf(source.start()).equals(payload.get("selectionStart"))
                && Integer.valueOf(source.end()).equals(payload.get("selectionEnd"))
                && source.selectedHash().equals(payload.get("selectedTextHash"))
                && source.selected().equals(payload.get("selectedText"))
                && source.prefix().equals(payload.get("candidatePrefix"))
                && source.suffix().equals(payload.get("candidateSuffix"))
                && candidate.equals(payload.get("candidate"))
                && ReviewArtifactRules.sha256(replacement).equals(payload.get("contentSha256"))
                && "selection".equals(diff.get("type"))
                && "replace_selection".equals(diff.get("mode"))
                && source.content().equals(diff.get("before"))
                && candidate.equals(diff.get("after"))
                && candidate.equals(diff.get("candidate"))
                && source.prefix().equals(diff.get("prefix"))
                && source.suffix().equals(diff.get("suffix"))
                && replacement.equals(diff.get("replacement"));
        if (!valid) throw sourceConflict(chapterId);
    }

    private String insertDecisionStep(
            DSLContext transaction,
            Locked locked,
            Revision revision,
            ReviewArtifactDecisionRequest request,
            ReviewDecisionIdentity identity,
            LocalDateTime now) {
        int ordinal = nextOrdinal(transaction, locked.runId());
        String stepId = ids.next();
        Map<String, Object> input = new LinkedHashMap<>();
        input.put("schemaVersion", 1);
        input.put("clientRequestId", request.getClientRequestId());
        input.put("artifactId", locked.artifactId());
        input.put("expectedArtifactRevision", request.getExpectedRevision());
        input.put("decidedArtifactRevision", revision.number());
        input.put("decision", request.getDecision().getValue());
        input.put("normalizedBody", identity.normalizedBody());
        transaction.execute(
                """
                INSERT INTO public."WorkflowStep" (
                  id, "runId", "agentId", "stepType", status, input, output,
                  "durationMs", "createdAt", ordinal, purpose, lane, "attemptCount",
                  "nextAttemptAt", "fencingToken", "leaseExpiresAt", "heartbeatAt",
                  "activeJobId", "idempotencyKey", "requestHash", "inputHash",
                  "resultHash", "evidenceBundleId", "artifactId", "artifactRevision",
                  "modelProfile", "modelProfileVersion", "outputSchema",
                  "outputSchemaVersion", "budgetJson", "resolvedModelJson", "usageJson",
                  "lastProgressSequence", "cancelRequestId", "submittedAt", "updatedAt",
                  "completedAt", "errorCode"
                ) VALUES (
                  ?, ?, NULL, CAST('user_confirmation' AS "WorkflowStepType"),
                  CAST('completed' AS "WorkflowStepStatus"), ?, NULL, 0, ?, ?,
                  'user_decision', 'control', 0, NULL, 0, NULL, NULL, NULL, ?, ?, ?,
                  ?, ?, ?, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, ?, ?, ?, NULL
                )
                """,
                stepId,
                locked.runId(),
                canonicalJson(input),
                now,
                ordinal,
                decisionKey(request.getClientRequestId()),
                identity.fingerprint(),
                ExecutionCanonicalJson.sha256(input),
                identity.fingerprint(),
                sourceBundleId(locked),
                locked.artifactId(),
                revision.number(),
                now,
                now,
                now);
        return stepId;
    }

    private void insertRevisionGenerationStep(
            DSLContext transaction,
            Locked locked,
            ExecutionPlanSnapshot executionPlan,
            Revision revision,
            ReviewArtifactDecisionRequest request,
            LocalDateTime now) {
        long existingModelSteps = transaction.fetchOne(
                """
                SELECT count(*) FROM public."WorkflowStep"
                WHERE "runId" = ? AND "stepType" = CAST('agent' AS "WorkflowStepType")
                """,
                locked.runId()).get(0, Long.class);
        long generationSteps = transaction.fetchOne(
                """
                SELECT count(*) FROM public."WorkflowStep"
                WHERE "runId" = ? AND purpose = 'generation'
                """,
                locked.runId()).get(0, Long.class);
        int requiredCalls = 1 + executionPlan.reviewers().size();
        if (generationSteps - 1 >= executionPlan.reviewPolicy().maxAutomaticRevisions()
                || existingModelSteps + requiredCalls
                        > executionPlan.runBudget().maxModelCalls()) {
            throw new ApiException(
                    409,
                    "WORKFLOW_REVISION_BUDGET_EXCEEDED",
                    "当前工作流已用完候选返工预算");
        }
        Record original = transaction.fetchOne(
                """
                SELECT input FROM public."WorkflowStep"
                WHERE "runId" = ? AND purpose = 'generation'
                ORDER BY ordinal ASC LIMIT 1
                """,
                locked.runId());
        if (original == null) throw new IllegalStateException("V2 Run 缺少原始 generation Step");
        Map<String, Object> input = new LinkedHashMap<>(
                readObject(original.get("input", String.class)));
        String originalInstruction = input.get("userInstruction") instanceof String value
                ? value
                : null;
        input.put("originalUserInstruction", originalInstruction);
        input.put("userInstruction", nullable(request.getUserMessage()));
        input.put("previousCandidate", Map.of(
                "artifactId", locked.artifactId(),
                "artifactRevision", revision.number(),
                "replacement", string(revision.payload(), "replacement")));
        String inputHash = ExecutionCanonicalJson.sha256(input);
        String stepId = ids.next();
        String idempotencyKey = locked.runId() + "." + stepId;
        Record bundle = transaction.fetchOne(
                """
                SELECT id, version, "manifestSha256"
                FROM public."WorkflowEvidenceBundle"
                WHERE id = ? AND "runId" = ?
                """,
                sourceBundleId(locked),
                locked.runId());
        if (bundle == null) throw new IllegalStateException("V2 Run 缺少 Evidence bundle");
        ExecutionPlanSnapshot.Step generator = executionPlan.generator();
        Map<String, Object> profile = generator.modelProfile().toMap();
        Map<String, Object> outputSchema = generator.outputSchema().toMap();
        Map<String, Object> budget = generator.stepBudget().budgetMap();
        String requestHash = ExecutionCanonicalJson.sha256(stepRequestMaterial(
                locked,
                stepId,
                idempotencyKey,
                inputHash,
                bundle,
                generator.evidencePolicy(),
                generator.lane(),
                profile,
                outputSchema,
                budget,
                revision));
        Map<String, Object> storedBudget = generator.stepBudget().stored();
        transaction.execute(
                """
                INSERT INTO public."WorkflowStep" (
                  id, "runId", "agentId", "stepType", status, input, "createdAt",
                  ordinal, purpose, lane, "attemptCount", "nextAttemptAt", "fencingToken",
                  "idempotencyKey", "requestHash", "inputHash", "evidenceBundleId",
                  "artifactId", "artifactRevision", "modelProfile", "modelProfileVersion",
                  "outputSchema", "outputSchemaVersion", "budgetJson", "submittedAt", "updatedAt"
                ) VALUES (
                  ?, ?, ?, CAST('agent' AS "WorkflowStepType"),
                  CAST('pending' AS "WorkflowStepStatus"), ?, ?, ?, 'generation', ?, 0, ?, 0,
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                stepId,
                locked.runId(),
                generator.modelProfile().profile(),
                canonicalJson(input),
                now,
                nextOrdinal(transaction, locked.runId()),
                generator.lane(),
                now,
                idempotencyKey,
                requestHash,
                inputHash,
                sourceBundleId(locked),
                locked.artifactId(),
                revision.number(),
                generator.modelProfile().profile(),
                Integer.toString(generator.modelProfile().version()),
                generator.outputSchema().name(),
                Integer.toString(generator.outputSchema().version()),
                json.writeValueAsString(storedBudget),
                now,
                now);
    }

    private static Map<String, Object> stepRequestMaterial(
            Locked locked,
            String stepId,
            String idempotencyKey,
            String inputHash,
            Record bundle,
            String policyVersion,
            String lane,
            Map<String, Object> modelProfile,
            Map<String, Object> outputSchema,
            Map<String, Object> budget,
            Revision revision) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("runId", locked.runId());
        result.put("novelId", locked.novelId());
        result.put("stepId", stepId);
        result.put("idempotencyKey", idempotencyKey);
        result.put("inputHash", inputHash);
        result.put("workflow", locked.run().get("workflow", String.class));
        result.put("operation", locked.run().get("operation", String.class));
        result.put("purpose", "generation");
        result.put("lane", lane);
        result.put("evidenceManifest", Map.of(
                "bundleId", bundle.get("id", String.class),
                "bundleVersion", bundle.get("version", Integer.class),
                "policyVersion", policyVersion,
                "manifestSha256", bundle.get("manifestSha256", String.class)));
        result.put("modelProfile", modelProfile);
        result.put("outputSchema", outputSchema);
        result.put("budget", budget);
        result.put("artifact", Map.of(
                "artifactId", locked.artifactId(),
                "artifactRevision", revision.number()));
        return Collections.unmodifiableMap(result);
    }

    private WritingRunV2Response snapshot(DSLContext transaction, String runId) {
        Record run = transaction.fetchOne(
                """
                SELECT id, "chapterId", workflow, operation,
                       "operationCatalogVersion", "modelPolicyJson",
                       status::text AS status, "cancelRequestedAt",
                       "lastEventSequence", revision
                FROM public."WorkflowRun" WHERE id = ? AND "engineVersion" = 2
                """,
                runId);
        if (run == null) throw new IllegalStateException("V2 Run 决定后消失");
        List<Record> stepRecords = transaction.fetch(
                """
                WITH active_steps AS (
                  SELECT step.id, step."runId", step.ordinal, step.purpose, step.lane,
                         step.status::text AS status, step."attemptCount",
                         step."fencingToken", step."errorCode", step."modelProfile",
                         step."modelProfileVersion", step."resolvedModelJson"
                  FROM public."WorkflowStep" AS step
                  WHERE step."runId" = ? AND step.ordinal IS NOT NULL
                    AND step.status::text IN ('pending', 'running')
                ), latest_progress AS (
                  SELECT DISTINCT ON (event."runId", event."payloadJson"::jsonb ->> 'stepId')
                         event."runId", event."payloadJson"::jsonb ->> 'stepId' AS step_id,
                         event."payloadJson" AS latest_progress_json
                  FROM public."WorkflowEvent" AS event
                  JOIN active_steps AS step
                    ON step."runId" = event."runId"
                   AND step.id = event."payloadJson"::jsonb ->> 'stepId'
                  WHERE event."eventType" = 'step_progress'
                  ORDER BY event."runId", event."payloadJson"::jsonb ->> 'stepId',
                           event.sequence DESC
                )
                SELECT step.*, progress.latest_progress_json
                FROM active_steps AS step
                LEFT JOIN latest_progress AS progress
                  ON progress."runId" = step."runId" AND progress.step_id = step.id
                ORDER BY step.ordinal ASC, step.id ASC
                """,
                runId);
        Record artifact = transaction.fetchOne(
                """
                SELECT id, status::text AS status, revision
                FROM public."ReviewArtifact" WHERE "workflowRunId" = ?
                ORDER BY "updatedAt" DESC, id DESC LIMIT 1
                """,
                runId);
        ExecutionPlanSnapshot executionPlan = stepRecords.isEmpty()
                ? null
                : executionPlan(run);
        List<WorkflowCurrentStepSnapshot> activeSteps = stepRecords.stream()
                .map(step -> stepSnapshot(executionPlan, step))
                .toList();
        WorkflowCurrentStepSnapshot current = activeSteps.isEmpty()
                ? null
                : activeSteps.getFirst();
        WorkflowArtifactSnapshot artifactSnapshot = artifact == null
                ? null
                : new WorkflowArtifactSnapshot(
                        "waiting_user".equals(run.get("status", String.class))
                                && run.get("cancelRequestedAt", LocalDateTime.class) == null
                                && "awaiting_user".equals(artifact.get("status", String.class)),
                        artifact.get("id", String.class),
                        artifact.get("revision", Integer.class),
                        WorkflowArtifactSnapshot.StatusEnum.fromValue(
                                artifact.get("status", String.class)));
        return new WritingRunV2Response(
                        activeSteps,
                        run.get("chapterId", String.class),
                        null,
                        null,
                        2,
                        Math.toIntExact(run.get("lastEventSequence", Long.class)),
                        run.get("revision", Integer.class),
                        runId,
                        WritingRunV2Response.StatusEnum.fromValue(
                                run.get("status", String.class)),
                        null,
                        run.get("workflow", String.class))
                .operation(run.get("operation", String.class))
                .currentStep(current)
                .cancelRequestedAt(DatabaseTimestamp.api(
                        run.get("cancelRequestedAt", LocalDateTime.class)))
                .artifact(artifactSnapshot);
    }

    private WorkflowCurrentStepSnapshot stepSnapshot(
            ExecutionPlanSnapshot executionPlan, Record step) {
        String lane = step.get("lane", String.class);
        if ("control".equals(lane)) {
            return stepSnapshots.controlStep(
                    step.get("id", String.class),
                    step.get("ordinal", Integer.class),
                    step.get("purpose", String.class),
                    step.get("status", String.class),
                    step.get("attemptCount", Integer.class),
                    step.get("fencingToken", Long.class),
                    step.get("errorCode", String.class));
        }
        if (executionPlan == null) {
            throw new IllegalStateException("模型 Step 缺少冻结执行计划");
        }
        return stepSnapshots.modelStep(
                executionPlan,
                step.get("id", String.class),
                step.get("ordinal", Integer.class),
                step.get("purpose", String.class),
                lane,
                step.get("status", String.class),
                step.get("attemptCount", Integer.class),
                step.get("fencingToken", Long.class),
                step.get("errorCode", String.class),
                step.get("modelProfile", String.class),
                Integer.parseInt(step.get("modelProfileVersion", String.class)),
                step.get("resolvedModelJson", String.class),
                step.get("latest_progress_json", String.class));
    }

    private void saveDecisionReceipt(
            DSLContext transaction, String stepId, WritingRunV2Response response) {
        int changed = transaction.execute(
                "UPDATE public.\"WorkflowStep\" SET output = ? WHERE id = ? AND purpose = 'user_decision'",
                json.writeValueAsString(response),
                stepId);
        if (changed != 1) throw new IllegalStateException("V2 决定 Step 回执保存失败");
    }

    private void completeRun(
            DSLContext transaction, String runId, long sequence, LocalDateTime now) {
        transaction.execute(
                """
                UPDATE public."WorkflowRun"
                SET status = CAST('completed' AS "WorkflowRunStatus"),
                    "lastEventSequence" = ?, revision = revision + 1,
                    "completedAt" = ?, "updatedAt" = ?, "errorCode" = NULL
                WHERE id = ?
                """,
                sequence,
                now,
                now,
                runId);
    }

    private long appendEvent(
            DSLContext transaction,
            String runId,
            long previous,
            String eventType,
            Map<String, Object> payload,
            String dedupeKey,
            LocalDateTime now) {
        long sequence = Math.addExact(previous, 1L);
        transaction.execute(
                """
                INSERT INTO public."WorkflowEvent" (
                  id, "runId", sequence, "eventType", "payloadJson", "dedupeKey", "createdAt"
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ids.next(),
                runId,
                sequence,
                eventType,
                canonicalJson(payload),
                dedupeKey,
                now);
        return sequence;
    }

    private static void transitionArtifact(
            DSLContext transaction,
            String artifactId,
            String current,
            String target,
            LocalDateTime now,
            boolean applied) {
        String appliedSql = applied ? ", \"appliedAt\" = ?" : "";
        List<Object> bindings = new ArrayList<>();
        bindings.add(target);
        bindings.add(now);
        if (applied) bindings.add(now);
        bindings.add(artifactId);
        bindings.add(current);
        int changed = transaction.execute(
                "UPDATE public.\"ReviewArtifact\" SET status = CAST(? AS \"ReviewArtifactStatus\"), "
                        + "\"updatedAt\" = ?" + appliedSql
                        + " WHERE id = ? AND status = CAST(? AS \"ReviewArtifactStatus\")",
                bindings.toArray());
        if (changed != 1) {
            throw new ApiException(
                    409, "ARTIFACT_STATUS_CONFLICT", "待审核草案状态已被其他请求修改");
        }
    }

    private static int nextOrdinal(DSLContext transaction, String runId) {
        Record value = transaction.fetchOne(
                "SELECT max(ordinal) FROM public.\"WorkflowStep\" WHERE \"runId\" = ?",
                runId);
        Integer maximum = value == null ? null : value.get(0, Integer.class);
        return Math.addExact(maximum == null ? 0 : maximum, 1);
    }

    private static String sourceBundleId(Locked locked) {
        String value = locked.run().get("currentEvidenceBundleId", String.class);
        if (value == null) throw new IllegalStateException("V2 Run 缺少当前 Evidence bundle");
        return value;
    }

    private static void requireV2RequestShape(ReviewArtifactDecisionRequest request) {
        if (request.getEngineVersion() != ReviewArtifactDecisionRequest.EngineVersionEnum.NUMBER_2) {
            throw new IllegalArgumentException("V2 决定必须显式声明 engineVersion=2");
        }
        if (nullable(request.getEditedContent()) != null
                || nullable(request.getSelectedUpdateRefs()) != null) {
            throw validation("V2 章节选区决定只允许提交 editedReplacement");
        }
        String replacement = nullable(request.getEditedReplacement());
        if (request.getDecision() == ReviewArtifactDecisionRequest.DecisionEnum.APPROVE) {
            if (replacement != null && replacement.isBlank()) {
                throw validation("V2 editedReplacement 不能为空白");
            }
            return;
        }
        if (replacement != null) throw validation("只有 V2 approve 可以提交 editedReplacement");
        if (request.getDecision() == ReviewArtifactDecisionRequest.DecisionEnum.REVISE) {
            String message = nullable(request.getUserMessage());
            if (message == null || message.isBlank()) {
                throw validation("V2 revise 必须携带非空白 userMessage");
            }
        }
    }

    private static boolean timestampEquals(Object value, LocalDateTime expected) {
        if (!(value instanceof String text)) return false;
        try {
            return DatabaseTimestamp.api(expected).toInstant()
                    .equals(OffsetDateTime.parse(text).toInstant());
        } catch (DateTimeParseException exception) {
            return false;
        }
    }

    private Map<String, Object> readObject(String value) {
        if (value == null) throw invalidArtifact();
        try {
            return json.readValue(value, JSON_OBJECT);
        } catch (RuntimeException exception) {
            throw invalidArtifact();
        }
    }

    private ExecutionPlanSnapshot executionPlan(Record run) {
        ExecutionPlanSnapshot result = ExecutionPlanSnapshot.fromStored(
                readObject(run.get("modelPolicyJson", String.class)));
        result.requireOperation(
                run.get("workflow", String.class),
                run.get("operation", String.class),
                run.get("operationCatalogVersion", String.class));
        return result;
    }

    private static Map<String, Object> map(Object value, String label) {
        if (!(value instanceof Map<?, ?> raw)) throw invalidArtifact();
        Map<String, Object> result = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : raw.entrySet()) {
            if (!(entry.getKey() instanceof String key)) throw invalidArtifact();
            result.put(key, entry.getValue());
        }
        return result;
    }

    private static int integer(Map<String, Object> value, String field) {
        if (value.get(field) instanceof Integer result) return result;
        if (value.get(field) instanceof Number result) return Math.toIntExact(result.longValue());
        throw invalidArtifact();
    }

    private static String string(Map<String, Object> value, String field) {
        if (value.get(field) instanceof String result) return result;
        throw invalidArtifact();
    }

    private static String canonicalJson(Map<String, Object> value) {
        return new String(ExecutionCanonicalJson.bytes(value), StandardCharsets.UTF_8);
    }

    private static String decisionKey(String clientRequestId) {
        return DECISION_KEY_PREFIX + clientRequestId;
    }

    private static <T> T nullable(JsonNullable<T> value) {
        return value == null || value.isUndefined() ? null : value.orElse(null);
    }

    private static ApiException sourceConflict(String chapterId) {
        return new ApiException(
                409,
                "ARTIFACT_SOURCE_VERSION_CONFLICT",
                "选区草案的来源版本已变化",
                Map.of("resourceType", "chapter_content", "resourceId", chapterId));
    }

    private static ApiException revisionConflict(int expected, int current) {
        return new ApiException(
                409,
                "ARTIFACT_REVISION_CONFLICT",
                "待审核草案修订号已变化",
                Map.of("expectedRevision", expected, "currentRevision", current));
    }

    private static ApiException validation(String message) {
        return new ApiException(422, "VALIDATION_ERROR", message);
    }

    private static ApiException invalidArtifact() {
        return new ApiException(
                409, "ARTIFACT_PAYLOAD_INVALID", "待审核草案持久化内容格式错误");
    }

    private static ApiException invalidReceipt() {
        return new ApiException(
                409, "WORKFLOW_DECISION_RECEIPT_INVALID", "工作流决定幂等回执无效");
    }

    private static ApiException reused(String clientRequestId) {
        return CommandIdempotencyStore.reused(clientRequestId);
    }

    private static ApiException forbidden() {
        return new ApiException(
                403, "REVIEW_ARTIFACT_FORBIDDEN", "无权访问该待审核草案");
    }

    private record Locked(Record run, Record artifact, Record revision) {
        String runId() {
            return run.get("id", String.class);
        }

        String novelId() {
            return run.get("novelId", String.class);
        }

        String chapterId() {
            return run.get("chapterId", String.class);
        }

        long lastEventSequence() {
            return run.get("lastEventSequence", Long.class);
        }

        String artifactId() {
            return artifact.get("id", String.class);
        }

        String artifactKey() {
            return artifact.get("artifactKey", String.class);
        }

        String kind() {
            return artifact.get("kind", String.class);
        }
    }

    private record Source(
            String bundleId,
            String itemId,
            String resourceId,
            String content,
            LocalDateTime updatedAt,
            String contentHash,
            int start,
            int end,
            String selected,
            String selectedHash,
            String prefix,
            String suffix) {}

    private record Revision(
            int number,
            Map<String, Object> payload,
            Map<String, Object> diff,
            Map<String, Object> storedPayload,
            Map<String, Object> storedDiff) {}

}
