package cn.inkforge.core.writing.infrastructure;

import cn.inkforge.contracts.api.ShortMediumStartWritingRunRequest;
import cn.inkforge.contracts.api.WritingRunStatusPublicResponse;
import cn.inkforge.contracts.api.WritingRunV2Response;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.writing.application.ShortMediumDurableRunStarter;
import cn.inkforge.core.writing.application.WritingRunQueryRepository;
import cn.inkforge.core.workflows.application.DurableWorkflowService;
import cn.inkforge.core.workflows.application.WorkflowEvidenceItemPlan;
import cn.inkforge.core.workflows.application.WorkflowInitialStepPlan;
import cn.inkforge.core.workflows.application.WorkflowRunStartResult;
import cn.inkforge.core.workflows.application.WorkflowStartPlan;
import cn.inkforge.core.workflows.catalog.ExecutionPlanSnapshot;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.jooq.DSLContext;
import org.jooq.Record;
import org.openapitools.jackson.nullable.JsonNullable;
import tools.jackson.databind.ObjectMapper;

/** 把四项中短篇公共请求冻结为不依赖 V1 Task/Command 的 V2 Run。 */
final class JooqShortMediumDurableRunStarter implements ShortMediumDurableRunStarter {

    private static final Set<String> OPERATION_KEYS = Set.of(
            "short_medium.generate_outline",
            "short_medium.generate_manuscript",
            "short_medium.replace_selection",
            "short_medium.full_check");

    private final CoreDatabase database;
    private final ShortMediumRunAssembler assembler;
    private final DurableWorkflowService workflows;
    private final ExecutionRegistry registry;
    private final WritingRunQueryRepository queries;
    private final ObjectMapper json;

    JooqShortMediumDurableRunStarter(
            CoreDatabase database,
            ShortMediumRunAssembler assembler,
            DurableWorkflowService workflows,
            ExecutionRegistry registry,
            WritingRunQueryRepository queries,
            ObjectMapper json) {
        this.database = Objects.requireNonNull(database);
        this.assembler = Objects.requireNonNull(assembler);
        this.workflows = Objects.requireNonNull(workflows);
        this.registry = Objects.requireNonNull(registry);
        this.queries = Objects.requireNonNull(queries);
        this.json = Objects.requireNonNull(json);
    }

    @Override
    public Set<String> supportedOperationKeys() {
        return OPERATION_KEYS;
    }

    @Override
    public WritingRunV2Response replayExisting(
            String userId, ShortMediumStartWritingRunRequest request) {
        Normalized normalized = normalize(request);
        return database.transactionResult(transaction -> {
            WritingRunV2Response replay = replay(
                    transaction,
                    userId,
                    request.getClientRequestId(),
                    normalized.fingerprint());
            if (replay == null) {
                throw new IllegalStateException("既有中短篇 V2 幂等身份不可见，拒绝创建新 Run");
            }
            return replay;
        });
    }

    @Override
    public WritingRunV2Response startFresh(
            String userId, ShortMediumStartWritingRunRequest request) {
        Normalized normalized = normalize(request);
        return database.transactionResult(transaction -> {
            WritingRunV2Response replay = replay(
                    transaction,
                    userId,
                    request.getClientRequestId(),
                    normalized.fingerprint());
            if (replay != null) return replay;

            ShortMediumRunAssembler.Assembled assembled =
                    assembler.assemble(transaction, userId, request);
            String operationKey = operationKey(request);
            if (!OPERATION_KEYS.contains(operationKey)) {
                throw new ApiException(
                        409,
                        "DURABLE_OPERATION_NOT_ENABLED",
                        "该中短篇操作尚未切换到耐久执行引擎");
            }
            ExecutionRegistry.ResolvedOperation operation =
                    registry.resolve(operationKey, false);
            ExecutionPlanSnapshot executionPlan =
                    registry.freezePlan(operationKey, false);
            Target target = target(request, assembled.chapterId());
            String scopeKind = request.getOperation()
                            == ShortMediumStartWritingRunRequest.OperationEnum.REPLACE_SELECTION
                    ? "document_selection"
                    : "novel";
            requireCatalogIdentity(operation.operation(), target.type(), scopeKind);

            int segmentCount = request.getOperation()
                            == ShortMediumStartWritingRunRequest.OperationEnum.GENERATE_MANUSCRIPT
                    ? Math.max(1, Math.floorDiv(assembled.targetTotalWordCount() + 14_999, 15_000))
                    : 1;
            Map<String, Object> stepInput = Map.of(
                    "segmentIndex", 0,
                    "segmentCount", segmentCount);
            String runKind = request.getOperation()
                            == ShortMediumStartWritingRunRequest.OperationEnum.FULL_CHECK
                    ? "quality_check"
                    : "chapter_generation";
            String chapterId = request.getDocumentType()
                            == ShortMediumStartWritingRunRequest.DocumentTypeEnum.MANUSCRIPT
                    ? assembled.chapterId()
                    : null;
            WorkflowStartPlan plan = new WorkflowStartPlan(
                    userId,
                    request.getClientRequestId(),
                    normalized.fingerprint(),
                    operation.operation().workflow(),
                    operation.operation().operation(),
                    registry.catalogVersion(),
                    runKind,
                    request.getNovelId(),
                    chapterId,
                    null,
                    target.type(),
                    target.id(),
                    normalized.body(),
                    operation.operation().evidencePolicy(),
                    List.of(new WorkflowEvidenceItemPlan(
                            "short_medium_context",
                            request.getNovelId(),
                            true,
                            null,
                            null,
                            null,
                            assembled.payload(),
                            null,
                            null,
                            Map.of("role", "short_medium_context"))),
                    operation.operation().runBudget(),
                    executionPlan,
                    new WorkflowInitialStepPlan(
                            "generation",
                            operation.operation().lane(),
                            stepInput,
                            operation.generatorProfile(),
                            operation.generatorStepBudget(),
                            operation.outputSchema()));
            WorkflowRunStartResult result = workflows.startFresh(plan);
            WritingRunV2Response response = publicResponse(userId, result.runId());
            if (!result.runId().equals(response.getRunId())) {
                throw new IllegalStateException("中短篇 V2 Run 创建后的权威投影身份不一致");
            }
            return response;
        });
    }

    private WritingRunV2Response replay(
            DSLContext transaction,
            String userId,
            String clientRequestId,
            String requestHash) {
        Record run = transaction.fetchOne(
                """
                SELECT id, workflow, operation, "requestHash"
                FROM public."WorkflowRun"
                WHERE "engineVersion" = 2 AND "userId" = ? AND "idempotencyKey" = ?
                FOR UPDATE
                """,
                userId,
                clientRequestId);
        if (run == null) return null;
        if (!requestHash.equals(run.get("requestHash", String.class))
                || !"short_medium".equals(run.get("workflow", String.class))) {
            throw new ApiException(
                    409,
                    "IDEMPOTENCY_KEY_REUSED",
                    "同一 clientRequestId 已用于不同 Agent 请求");
        }
        return publicResponse(userId, run.get("id", String.class));
    }

    private WritingRunV2Response publicResponse(String userId, String runId) {
        WritingRunStatusPublicResponse response = queries.getPublic(userId, runId);
        if (!(response instanceof WritingRunV2Response durable)) {
            throw new IllegalStateException("中短篇 V2 Run 被错误投影为 V1 状态");
        }
        return durable;
    }

    private Normalized normalize(ShortMediumStartWritingRunRequest request) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("workflow", request.getWorkflow());
        body.put("novelId", request.getNovelId());
        body.put("operation", request.getOperation().getValue());
        body.put("documentType", request.getDocumentType().getValue());
        body.put("chapterId", nullable(request.getChapterId()));
        body.put("baseVersionId", nullable(request.getBaseVersionId()));
        body.put("sourceOutlineVersionId", nullable(request.getSourceOutlineVersionId()));
        body.put("selectionStart", nullable(request.getSelectionStart()));
        body.put("selectionEnd", nullable(request.getSelectionEnd()));
        body.put("selectedTextHash", nullable(request.getSelectedTextHash()));
        body.put("userInstruction", nullable(request.getUserInstruction()));
        Map<String, Object> resource = new LinkedHashMap<>();
        resource.put("novelId", request.getNovelId());
        resource.put("chapterId", nullable(request.getChapterId()));
        return new Normalized(
                Collections.unmodifiableMap(body),
                CommandIdempotency.requestFingerprint("start", resource, body, json));
    }

    private static Target target(
            ShortMediumStartWritingRunRequest request, String resolvedChapterId) {
        if (request.getDocumentType()
                == ShortMediumStartWritingRunRequest.DocumentTypeEnum.OUTLINE) {
            return new Target("short_medium_outline", request.getNovelId());
        }
        return new Target("short_medium_manuscript", resolvedChapterId);
    }

    private static void requireCatalogIdentity(
            ExecutionRegistry.Operation operation, String targetType, String scopeKind) {
        if (!"short_medium".equals(operation.workflow())
                || !operation.targetKinds().contains(targetType)
                || !operation.scopeKinds().contains(scopeKind)) {
            throw new IllegalStateException("中短篇 Operation Catalog 的 target/scope 与启动计划不一致");
        }
    }

    private static String operationKey(ShortMediumStartWritingRunRequest request) {
        return "short_medium." + request.getOperation().getValue();
    }

    private static <T> T nullable(JsonNullable<T> value) {
        return value != null && value.isPresent() ? value.orElse(null) : null;
    }

    private record Normalized(Map<String, Object> body, String fingerprint) {}

    private record Target(String type, String id) {}
}
