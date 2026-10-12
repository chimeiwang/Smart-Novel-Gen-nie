package cn.inkforge.core.writing.infrastructure;

import cn.inkforge.contracts.api.ChapterScope;
import cn.inkforge.contracts.api.ChapterTarget;
import cn.inkforge.contracts.api.LongSerialStartWritingRunRequest;
import cn.inkforge.contracts.api.NaturalStartWritingRunRequest;
import cn.inkforge.contracts.api.NovelScope;
import cn.inkforge.contracts.api.WorkflowCurrentStepSnapshot;
import cn.inkforge.contracts.api.WritingRunV2Response;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.platform.text.TextLength;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.reviews.application.AgentUpdatesEvidenceReader;
import cn.inkforge.core.reviews.application.ChapterPlanEvidenceReader;
import cn.inkforge.core.reviews.application.ChapterWritingEvidenceReader;
import cn.inkforge.core.writing.application.LongSerialDurableRunStarter;
import cn.inkforge.core.writing.domain.WritingRunCursor;
import cn.inkforge.core.writing.domain.WritingRunOutcomeProjector;
import cn.inkforge.core.writing.domain.WritingRunStatusProjector;
import cn.inkforge.core.workflows.domain.WorkflowMessageMetadata;
import cn.inkforge.core.workflows.application.DurableWorkflowService;
import cn.inkforge.core.workflows.application.WorkflowEvidenceItemPlan;
import cn.inkforge.core.workflows.application.WorkflowInitialStepPlan;
import cn.inkforge.core.workflows.application.WorkflowRunStartResult;
import cn.inkforge.core.workflows.application.WorkflowStartPlan;
import cn.inkforge.core.workflows.application.WorkflowIntentBusinessPreparation;
import cn.inkforge.core.workflows.application.WorkflowIntentBusinessPreparation.Prepared;
import cn.inkforge.core.workflows.application.WorkflowExecutionContextReader;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.catalog.ExecutionPlanSnapshot;
import cn.inkforge.core.workflows.catalog.IntentExecutionPlanSnapshot;
import cn.inkforge.core.workflows.catalog.WorkflowExecutionContext;
import cn.inkforge.core.workflows.catalog.WorkflowStepSnapshotFactory;
import java.time.Clock;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.jooq.DSLContext;
import org.jooq.Record;
import org.openapitools.jackson.nullable.JsonNullable;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.core.type.TypeReference;

/** 按 Catalog key 分派长篇确定性 Evidence Planner 的 V2 Run 入口。 */
final class JooqLongSerialDurableRunStarter implements LongSerialDurableRunStarter {

    private static final Set<String> NATURAL_OPERATIONS = Set.of(
            "long_serial.answer_question", "long_serial.plan_chapter", "long_serial.review_chapter",
            "long_serial.rewrite_scene", "long_serial.write_chapter",
            "long_serial.create_lore", "long_serial.revise_lore", "long_serial.create_outline",
            "long_serial.revise_outline", "long_serial.manage_foreshadowing");

    private final CoreDatabase database;
    private final LongSerialRunAssembler assembler;
    private final DurableWorkflowService workflows;
    private final ExecutionRegistry registry;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final ObjectMapper json;
    private final WorkflowStepSnapshotFactory stepSnapshots;
    private final Map<String, EvidencePlanner> planners;
    private final ChapterPlanEvidenceReader chapterPlanningSources;
    private final ChapterWritingEvidenceReader chapterWritingSources;
    private final AgentUpdatesStartPlanner agentUpdatesPlanner;
    private final WorkflowExecutionContextReader executionContexts;

    JooqLongSerialDurableRunStarter(
            CoreDatabase database,
            LongSerialRunAssembler assembler,
            DurableWorkflowService workflows,
            ExecutionRegistry registry,
            CuidV1Generator ids,
            Clock clock,
            ObjectMapper json,
            ChapterPlanEvidenceReader chapterPlanningSources,
            ChapterWritingEvidenceReader chapterWritingSources) {
        this(database, assembler, workflows, registry, ids, clock, json, chapterPlanningSources, chapterWritingSources, null);
    }

    JooqLongSerialDurableRunStarter(CoreDatabase database, LongSerialRunAssembler assembler,
            DurableWorkflowService workflows, ExecutionRegistry registry, CuidV1Generator ids, Clock clock,
            ObjectMapper json, ChapterPlanEvidenceReader chapterPlanningSources,
            ChapterWritingEvidenceReader chapterWritingSources, WorkflowExecutionContextReader executionContexts) {
        this(database, assembler, workflows, registry, ids, clock, json, chapterPlanningSources,
                chapterWritingSources, executionContexts, null);
    }

    JooqLongSerialDurableRunStarter(CoreDatabase database, LongSerialRunAssembler assembler,
            DurableWorkflowService workflows, ExecutionRegistry registry, CuidV1Generator ids, Clock clock,
            ObjectMapper json, ChapterPlanEvidenceReader chapterPlanningSources,
            ChapterWritingEvidenceReader chapterWritingSources, WorkflowExecutionContextReader executionContexts,
            AgentUpdatesEvidenceReader agentUpdatesSources) {
        this.database = Objects.requireNonNull(database);
        this.assembler = Objects.requireNonNull(assembler);
        this.workflows = Objects.requireNonNull(workflows);
        this.registry = Objects.requireNonNull(registry);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
        this.chapterPlanningSources = Objects.requireNonNull(chapterPlanningSources);
        this.chapterWritingSources = Objects.requireNonNull(chapterWritingSources);
        this.agentUpdatesPlanner = agentUpdatesSources == null ? null : new AgentUpdatesStartPlanner(agentUpdatesSources);
        this.executionContexts = executionContexts;
        this.stepSnapshots = new WorkflowStepSnapshotFactory(json);
        Map<String, EvidencePlanner> configured = new LinkedHashMap<>();
        configured.put("long_serial.answer_question", this::planAnswerQuestion);
        configured.put("long_serial.plan_chapter", this::planChapter);
        configured.put("long_serial.review_chapter", this::planChapterReview);
        configured.put("long_serial.rewrite_scene", this::planSceneRewrite);
        configured.put("long_serial.write_chapter", this::planChapterWriting);
        configured.put("long_serial.rewrite_chapter_selection", this::planChapterSelectionRewrite);
        configured.put("long_serial.rewrite_outline_selection", this::planOutlineSelectionRewrite);
        if (agentUpdatesPlanner != null) {
            AgentUpdatesStartPlanner.OPERATION_KEYS.forEach(
                    key -> configured.put(key, this::planAgentUpdates));
        }
        this.planners = Map.copyOf(configured);
    }

    @Override
    public Set<String> supportedOperationKeys() {
        return planners.keySet();
    }

    public Prepared prepare(String userId, String novelId, String chapterId, String writingSessionId,
            String userInstruction, int targetWordCount, ExecutionPlanSnapshot operationPlan) {
        if (!NATURAL_OPERATIONS.contains(operationPlan.operation().key()) || writingSessionId == null
                || userInstruction == null || TextLength.count(userInstruction) == 0
                || targetWordCount < 1 || targetWordCount > 10_000_000) {
            throw new ApiException(422, "VALIDATION_ERROR", "自然入口的业务准备身份不完整");
        }
        return database.transactionResult(transaction -> {
            requireLongSerialOwner(transaction, userId, novelId, chapterId, writingSessionId);
            // 仅复用确定性 Evidence Planner；绝不调用 startFresh，也不重新解析当前 Registry。
            var request = new LongSerialStartWritingRunRequest()
                    .novelId(novelId).chapterId(chapterId).writingSessionId(writingSessionId)
                    .operation(LongSerialStartWritingRunRequest.OperationEnum.fromValue(operationPlan.operation().operation()))
                    .userInstruction(userInstruction).targetWordCount(targetWordCount);
            LongSerialRunAssembler.Normalized normalized = null;
            if (AgentUpdatesStartPlanner.OPERATION_KEYS.contains(operationPlan.operation().key())) {
                request.workflow("long_serial").target(new ChapterTarget(chapterId, "chapter"));
                String scopeKind = IntentExecutionPlanSnapshot.defaultScopeKind(operationPlan.operation().key());
                request.scope("novel".equals(scopeKind)
                        ? new NovelScope("novel")
                        : new ChapterScope(chapterId, "chapter"));
                normalized = assembler.normalize(request);
            }
            PreparedStart prepared = planners.get(operationPlan.operation().key())
                    .prepare(transaction, userId, request, normalized);
            return new Prepared(prepared.input(), prepared.evidenceItems(), operationPlan.generator());
        });
    }

    @Override
    public WritingRunV2Response replayNatural(String userId, NaturalStartWritingRunRequest request) {
        NaturalInput normalized = normalizeNatural(request);
        return database.transactionResult(transaction -> {
            WritingRunV2Response replay = replay(transaction, userId, request.getClientRequestId(), normalized.fingerprint());
            if (replay == null) throw new IllegalStateException("既有自然 Run 不可见，禁止重新创建");
            return replay;
        });
    }

    @Override
    public WritingRunV2Response startNatural(String userId, NaturalStartWritingRunRequest request) {
        NaturalInput normalized = normalizeNatural(request);
        if (executionContexts == null) throw new IllegalStateException("自然入口的有效执行上下文未装配");
        return database.transactionResult(transaction -> {
            WritingRunV2Response replay = replay(transaction, userId, request.getClientRequestId(), normalized.fingerprint());
            if (replay != null) return replay;
            requireLongSerialOwner(transaction, userId, request.getNovelId(), request.getChapterId(), request.getWritingSessionId());
            List<String> operationKeys = registry.enabledOperationKeys("long_serial", false).stream()
                    .filter(NATURAL_OPERATIONS::contains).sorted().toList();
            if (operationKeys.isEmpty()) throw new ApiException(409, "DURABLE_NATURAL_ENTRY_NOT_ENABLED", "没有已授权的自然入口操作");
            IntentExecutionPlanSnapshot plan = IntentExecutionPlanSnapshot.freeze(registry, operationKeys);
            var system = registry.resolveSystemPurpose("resolve_intent");
            Record chapter = transaction.fetchOne("SELECT title, \"updatedAt\" FROM public.\"Chapter\" WHERE id = ? AND \"novelId\" = ?",
                    request.getChapterId(), request.getNovelId());
            List<Map<String, Object>> available = operationKeys.stream().map(key -> {
                String operation = plan.requireOperationPlan(key).operation().operation();
                String scopeKind = plan.scopeKindForOperation(key);
                String description = naturalDescription(operation, scopeKind);
                return Map.<String, Object>of("operation", operation, "description", description,
                        "targetType", "chapter", "scopeKind", scopeKind);
            }).toList();
            Map<String, Object> intentContext = Map.of("workflow", "long_serial", "novelId", request.getNovelId(),
                    "chapterId", request.getChapterId(), "chapterTitle", chapter.get("title", String.class), "availableOperations", available);
            var initial = new WorkflowInitialStepPlan("resolve_intent", system.purpose().lane(),
                    Map.of("userInstruction", request.getUserInstruction(), "clarifications", List.of()),
                    system.modelProfile(), system.stepBudget(), system.outputSchema());
            WorkflowRunStartResult result = workflows.startFresh(new WorkflowStartPlan(userId, request.getClientRequestId(),
                    normalized.fingerprint(), "long_serial", null, registry.catalogVersion(), "chat", request.getNovelId(),
                    request.getChapterId(), request.getWritingSessionId(), "chapter", request.getChapterId(), normalized.body(),
                    system.purpose().evidencePolicy(), List.of(new WorkflowEvidenceItemPlan("intent_context", request.getChapterId(),
                            true, null, DatabaseTimestamp.api(chapter.get("updatedAt", LocalDateTime.class)), null,
                            intentContext, null, null, Map.of("role", "intent_context"))), plan.runBudget(), null, initial, plan));
            persistUserMessage(transaction, result, request.getUserInstruction(), null);
            WritingRunV2Response response = replay(transaction, userId, request.getClientRequestId(), normalized.fingerprint());
            if (response == null) throw new IllegalStateException("自然 Run 创建后不可见");
            return response;
        });
    }

    private NaturalInput normalizeNatural(NaturalStartWritingRunRequest request) {
        Map<String, Object> body = Map.of("inputMode", "natural", "workflow", "long_serial",
                "novelId", request.getNovelId(), "chapterId", request.getChapterId(),
                "writingSessionId", request.getWritingSessionId(), "userInstruction", request.getUserInstruction(),
                "targetWordCount", request.getTargetWordCount() == null ? 4000 : request.getTargetWordCount());
        return new NaturalInput(body, CommandIdempotency.requestFingerprint("start",
                Map.of("novelId", request.getNovelId(), "chapterId", request.getChapterId()), body, json));
    }

    private record NaturalInput(Map<String, Object> body, String fingerprint) {}

    private static String naturalDescription(String operation, String scopeKind) {
        String label = switch (operation) {
            case "answer_question" -> "回答当前章节的问题";
            case "plan_chapter" -> "生成当前章节的剧情规划";
            case "review_chapter" -> "审阅当前章节并生成完整报告";
            case "rewrite_scene" -> "按要求改写场景并形成完整章节候选";
            case "write_chapter" -> "生成当前章节的完整正文草案";
            case "create_lore" -> "新建设定";
            case "revise_lore" -> "修改设定";
            case "create_outline" -> "创建大纲";
            case "revise_outline" -> "修改大纲";
            case "manage_foreshadowing" -> "管理当前章节的伏笔";
            default -> throw new IllegalStateException("自然入口包含未支持操作");
        };
        String range = switch (scopeKind) {
            case "chapter" -> "当前章节";
            case "novel" -> "整部小说";
            default -> throw new IllegalStateException("自然入口包含未支持的默认范围");
        };
        String explicit = "revise_outline".equals(operation) ? "；指定节点请使用显式入口" : "";
        return label + "（默认范围：" + range + explicit + "）";
    }

    @Override
    public WritingRunV2Response replayExisting(
            String userId, LongSerialStartWritingRunRequest request) {
        LongSerialRunAssembler.Normalized normalized = assembler.normalize(request);
        return database.transactionResult(transaction -> {
            WritingRunV2Response replay = replay(
                    transaction,
                    userId,
                    request.getClientRequestId(),
                    normalized.fingerprint());
            if (replay == null) {
                throw new IllegalStateException("既有 V2 幂等身份不可见，拒绝创建新 Run");
            }
            return replay;
        });
    }

    @Override
    public WritingRunV2Response startFresh(
            String userId, LongSerialStartWritingRunRequest request) {
        String operationKey = operationKey(request);
        EvidencePlanner planner = planners.get(operationKey);
        if (planner == null) {
            throw new ApiException(
                    409,
                    "DURABLE_OPERATION_NOT_ENABLED",
                    "该写作操作尚未切换到耐久执行引擎");
        }
        LongSerialRunAssembler.Normalized normalized = assembler.normalize(request);
        return database.transactionResult(transaction -> {
            WritingRunV2Response replay = replay(
                    transaction,
                    userId,
                    request.getClientRequestId(),
                    normalized.fingerprint());
            if (replay != null) return replay;
            requireLongSerialOwner(transaction, userId, request);
            ExecutionRegistry.ResolvedOperation operation = registry.resolve(operationKey, false);
            ExecutionPlanSnapshot executionPlan = registry.freezePlan(operationKey, false);
            PreparedStart prepared = planner.prepare(
                    transaction, userId, request, normalized);

            WorkflowStartPlan plan = new WorkflowStartPlan(
                    userId,
                    request.getClientRequestId(),
                    normalized.fingerprint(),
                    operation.operation().workflow(),
                    operation.operation().operation(),
                    registry.catalogVersion(),
                    prepared.runKind(),
                    request.getNovelId(),
                    request.getChapterId(),
                    nullable(request.getWritingSessionId()),
                    prepared.targetType(),
                    prepared.targetId(),
                    normalized.body(),
                    operation.operation().evidencePolicy(),
                    prepared.evidenceItems(),
                    operation.operation().runBudget(),
                    executionPlan,
                    new WorkflowInitialStepPlan(
                            "generation",
                            operation.operation().lane(),
                            prepared.input(),
                            operation.generatorProfile(),
                            operation.generatorStepBudget(),
                            operation.outputSchema()));
            WorkflowRunStartResult result = workflows.startFresh(plan);
            if (result.replayed()) {
                WritingRunV2Response concurrentReplay = replay(
                        transaction,
                        userId,
                        request.getClientRequestId(),
                        normalized.fingerprint());
                if (concurrentReplay == null) {
                    throw new IllegalStateException("幂等重放的 V2 Run 不可见");
                }
                return concurrentReplay;
            }
            persistUserMessage(
                    transaction,
                    result,
                    request.getUserInstruction(),
                    prepared.userMessageSource());
            return response(result, executionPlan);
        });
    }

    private PreparedStart planChapterSelectionRewrite(
            DSLContext transaction,
            String userId,
            LongSerialStartWritingRunRequest request,
            LongSerialRunAssembler.Normalized normalized) {
        LongSerialRunAssembler.Assembled assembled = assembler.assemble(
                transaction, userId, request, normalized.definition());
        Map<String, Object> snapshot = object(
                assembled.job().get("selectionSnapshot"), "选区快照");
        Map<String, Object> source = object(
                snapshot.get("sourceSnapshot"), "选区完整来源");
        String content = string(source, "content");
        String resourceType = string(snapshot, "resourceType");
        String resourceId = string(snapshot, "resourceId");
        OffsetDateTime updatedAt = OffsetDateTime.parse(string(source, "updatedAt"));
        int selectionStart = integer(snapshot, "selectionStart");
        int selectionEnd = integer(snapshot, "selectionEnd");

        Map<String, Object> input = new LinkedHashMap<>();
        input.put("target", normalized.body().get("target"));
        input.put("selectionTarget", normalized.body().get("selectionTarget"));
        input.put("selectedText", snapshot.get("selectedText"));
        input.put("contextBefore", snapshot.get("contextBefore"));
        input.put("contextAfter", snapshot.get("contextAfter"));
        input.put("userInstruction", request.getUserInstruction());
        return new PreparedStart(
                "chapter_generation",
                resourceType,
                resourceId,
                input,
                List.of(new WorkflowEvidenceItemPlan(
                        resourceType,
                        resourceId,
                        true,
                        null,
                        updatedAt,
                        content,
                        null,
                        selectionStart,
                        selectionEnd,
                        Map.of(
                                "role", "selection_source",
                                "baseContentHash", string(snapshot, "baseContentHash"),
                                "selectedTextHash", string(snapshot, "selectedTextHash")))),
                assembled.selectionAttachmentMetadata());
    }

    private PreparedStart planOutlineSelectionRewrite(
            DSLContext transaction,
            String userId,
            LongSerialStartWritingRunRequest request,
            LongSerialRunAssembler.Normalized normalized) {
        PreparedStart selection = planChapterSelectionRewrite(
                transaction, userId, request, normalized);
        return new PreparedStart(
                selection.runKind(),
                selection.targetType(),
                selection.targetId(),
                Map.of(
                        "userInstruction", request.getUserInstruction(),
                        "selectionTarget", normalized.body().get("selectionTarget")),
                selection.evidenceItems(),
                selection.userMessageSource());
    }

    private PreparedStart planChapterReview(
            DSLContext transaction,
            String userId,
            LongSerialStartWritingRunRequest request,
            LongSerialRunAssembler.Normalized normalized) {
        requireLongSerialOwner(transaction, userId, request);
        var evidence = chapterWritingSources.capture(
                transaction, request.getNovelId(), request.getChapterId(), request.getUserInstruction());
        return new PreparedStart(
                "chat",
                "chapter",
                request.getChapterId(),
                Map.of("userInstruction", request.getUserInstruction()),
                List.of(new WorkflowEvidenceItemPlan(
                        "chapter_writing_context", request.getChapterId(), true, null,
                        evidence.chapterUpdatedAt(), null, evidence.context(), null, null,
                        Map.of("role", "chapter_writing_context"))),
                null);
    }

    private PreparedStart planAgentUpdates(
            DSLContext transaction,
            String userId,
            LongSerialStartWritingRunRequest request,
            LongSerialRunAssembler.Normalized normalized) {
        if (agentUpdatesPlanner == null) {
            throw new IllegalStateException("结构化资料 Evidence Planner 未装配");
        }
        AgentUpdatesStartPlanner.Plan plan = agentUpdatesPlanner.prepare(transaction, request);
        return new PreparedStart(
                "chapter_generation",
                plan.targetType(),
                plan.targetId(),
                plan.input(),
                plan.evidenceItems(),
                null);
    }

    private PreparedStart planSceneRewrite(
            DSLContext transaction,
            String userId,
            LongSerialStartWritingRunRequest request,
            LongSerialRunAssembler.Normalized normalized) {
        return planChapterWriting(transaction, userId, request, normalized);
    }

    private PreparedStart planAnswerQuestion(
            DSLContext transaction,
            String userId,
            LongSerialStartWritingRunRequest request,
            LongSerialRunAssembler.Normalized normalized) {
        String sessionId = nullable(request.getWritingSessionId());
        if (sessionId == null) {
            throw new ApiException(
                    409,
                    "WRITING_SESSION_REQUIRED",
                    "长篇问答必须绑定写作会话");
        }
        Record chapter = transaction.fetchOne(
                """
                SELECT id, content, "updatedAt"
                FROM public."Chapter"
                WHERE id = ? AND "novelId" = ?
                FOR UPDATE
                """,
                request.getChapterId(),
                request.getNovelId());
        if (chapter == null) {
            throw new ApiException(404, "CHAPTER_NOT_FOUND", "章节不存在");
        }
        String content = chapter.get("content", String.class);
        LocalDateTime updatedAt = chapter.get("updatedAt", LocalDateTime.class);
        if (content == null || updatedAt == null) {
            throw new IllegalStateException("长篇问答的章节证据不完整");
        }
        return new PreparedStart(
                "chat",
                "chapter",
                request.getChapterId(),
                Map.of("userInstruction", request.getUserInstruction()),
                List.of(new WorkflowEvidenceItemPlan(
                        "chapter_content",
                        request.getChapterId(),
                        true,
                        null,
                        DatabaseTimestamp.api(updatedAt),
                        content,
                        null,
                        null,
                        null,
                        Map.of("role", "answer_context"))),
                null);
    }

    private PreparedStart planChapter(
            DSLContext transaction,
            String userId,
            LongSerialStartWritingRunRequest request,
            LongSerialRunAssembler.Normalized normalized) {
        ChapterPlanEvidenceReader.Snapshot snapshot = chapterPlanningSources.capture(
                transaction, request.getNovelId(), request.getChapterId(), request.getUserInstruction());
        return new PreparedStart(
                "beat_plan", "chapter", request.getChapterId(),
                Map.of("userInstruction", request.getUserInstruction(), "targetWordCount", request.getTargetWordCount()),
                List.of(new WorkflowEvidenceItemPlan(
                        "chapter_plan_context", request.getChapterId(), true, null, snapshot.chapterUpdatedAt(),
                        null, snapshot.context(), null, null, Map.of("role", "chapter_plan_context"))),
                null);
    }

    private static String operationKey(LongSerialStartWritingRunRequest request) {
        return "long_serial." + request.getOperation().getValue();
    }

    private PreparedStart planChapterWriting(
            DSLContext transaction,
            String userId,
            LongSerialStartWritingRunRequest request,
            LongSerialRunAssembler.Normalized normalized) {
        ChapterWritingEvidenceReader.Snapshot snapshot = chapterWritingSources.capture(
                transaction, request.getNovelId(), request.getChapterId(), request.getUserInstruction());
        return new PreparedStart(
                "chapter_generation", "chapter", request.getChapterId(),
                Map.of("userInstruction", request.getUserInstruction(), "targetWordCount", request.getTargetWordCount()),
                List.of(new WorkflowEvidenceItemPlan(
                        "chapter_writing_context", request.getChapterId(), true, null, snapshot.chapterUpdatedAt(),
                        null, snapshot.context(), null, null, Map.of("role", "chapter_writing_context"))),
                null);
    }

    private void persistUserMessage(
            DSLContext transaction,
            WorkflowRunStartResult result,
            String userInstruction,
            Map<String, Object> selectionAttachmentMetadata) {
        String sessionId = result.writingSessionId();
        if (sessionId == null || result.replayed()) return;
        Map<String, Object> source = new LinkedHashMap<>();
        if (selectionAttachmentMetadata != null) {
            source.putAll(selectionAttachmentMetadata);
        }
        source.put("engineVersion", 2);
        source.put("runId", result.runId());
        source.put("operation", result.operation());
        String metadata = WorkflowMessageMetadata.serialize(
                result.runId(),
                "user",
                userInstruction,
                null,
                source,
                json);
        Record existing = transaction.fetchOne(
                """
                SELECT id FROM public."WritingMessage"
                WHERE "sessionId" = ? AND metadata = ?
                ORDER BY "createdAt", id
                LIMIT 1
                """,
                sessionId,
                metadata);
        if (existing != null) return;
        Record session = transaction.fetchOne(
                """
                SELECT "updatedAt" FROM public."WritingSession"
                WHERE id = ? FOR UPDATE
                """,
                sessionId);
        if (session == null) {
            throw new IllegalStateException("V2 Run 绑定的写作会话不存在");
        }
        LocalDateTime now = DatabaseTimestamp.now(clock);
        transaction.execute(
                """
                INSERT INTO public."WritingMessage" (
                  id, "sessionId", role, "agentId", content, metadata, "createdAt"
                ) VALUES (?, ?, 'user', NULL, ?, ?, ?)
                """,
                ids.next(),
                sessionId,
                userInstruction,
                metadata,
                now);
        LocalDateTime sessionUpdatedAt = DatabaseTimestamp.next(
                clock, session.get("updatedAt", LocalDateTime.class));
        transaction.execute(
                "UPDATE public.\"WritingSession\" SET \"updatedAt\" = ? WHERE id = ?",
                sessionUpdatedAt,
                sessionId);
    }

    private WritingRunV2Response replay(
            DSLContext transaction,
            String userId,
            String clientRequestId,
            String requestHash) {
        Record run = transaction.fetchOne(
                """
                SELECT id, "chapterId", workflow, operation, status::text AS status,
                       "operationCatalogVersion", "requestHash", "modelPolicyJson",
                       "lastEventSequence", revision, "targetType", "targetId", "cancelRequestedAt", "errorCode"
                FROM public."WorkflowRun"
                WHERE "engineVersion" = 2 AND "userId" = ? AND "idempotencyKey" = ?
                FOR UPDATE
                """,
                userId,
                clientRequestId);
        if (run == null) return null;
        if (!requestHash.equals(run.get("requestHash", String.class))) {
            throw new ApiException(
                    409,
                    "IDEMPOTENCY_KEY_REUSED",
                    "同一 clientRequestId 已用于不同 Agent 请求");
        }
        if (executionContexts != null) {
            // 自然 Run 会从问题推进到业务 Artifact，显式整章审阅还需投影完整报告；
            // 生产装配下所有 V2 重放与 GET 共用同一份权威查询。
            return (WritingRunV2Response) new JooqWritingRunQueryRepository(database,
                    new WritingRunStatusProjector(json, new WritingRunOutcomeProjector(), clock),
                    new WritingRunCursor(json), json, true, executionContexts).getPublic(userId, run.get("id", String.class));
        }
        if (IntentExecutionPlanSnapshot.PLAN_VERSION.equals(json.readTree(run.get("modelPolicyJson", String.class))
                .path("planVersion").asText())) {
            throw new IllegalStateException("自然 Run 的重放上下文未装配");
        }
        List<Record> activeStepRecords = transaction.fetch(
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
                run.get("id", String.class));
        return response(transaction, run, activeStepRecords);
    }

    private static void requireLongSerialOwner(
            DSLContext transaction,
            String userId,
            LongSerialStartWritingRunRequest request) {
        requireLongSerialOwner(transaction, userId, request.getNovelId(), request.getChapterId(), nullable(request.getWritingSessionId()));
    }

    private static void requireLongSerialOwner(DSLContext transaction, String userId,
            String novelId, String chapterId, String writingSessionId) {
        // 公共 Router 已按 Novel -> Chapter 取得首轮锁；这里即使被单独调用也保持同序，
        // 再锁附属 WritingBible 与可选 Session，不能从 Chapter 回头等待 Novel。
        Record novel = transaction.fetchOne(
                """
                SELECT id FROM public."Novel"
                WHERE id = ? AND "userId" = ?
                FOR UPDATE
                """,
                novelId,
                userId);
        if (novel == null) {
            throw new ApiException(404, "NOVEL_NOT_FOUND", "小说不存在");
        }
        Record chapter = transaction.fetchOne(
                """
                SELECT id FROM public."Chapter"
                WHERE id = ? AND "novelId" = ? FOR UPDATE
                """,
                chapterId,
                novelId);
        if (chapter == null) {
            throw new ApiException(404, "CHAPTER_NOT_FOUND", "章节不存在");
        }
        Record bible = transaction.fetchOne(
                """
                SELECT "storyLengthProfile"::text AS profile
                FROM public."WritingBible"
                WHERE "novelId" = ?
                FOR UPDATE
                """,
                novelId);
        if (bible == null) {
            throw new ApiException(404, "NOVEL_NOT_FOUND", "小说不存在");
        }
        if (!"long_serial".equals(bible.get("profile", String.class))) {
            throw new ApiException(409, "LONG_WORKFLOW_MISMATCH", "目标小说不是长篇作品");
        }
        String sessionId = writingSessionId;
        if (sessionId != null) {
            Record session = transaction.fetchOne(
                    """
                    SELECT id FROM public."WritingSession"
                    WHERE id = ? AND "novelId" = ? AND "chapterId" = ?
                    FOR UPDATE
                    """,
                    sessionId,
                    novelId,
                    chapterId);
            if (session == null) {
                throw new ApiException(
                        409,
                        "WRITING_SESSION_MISMATCH",
                        "当前请求不属于所选写作会话");
            }
        }
    }

    private WritingRunV2Response response(
            WorkflowRunStartResult result, ExecutionPlanSnapshot executionPlan) {
        ExecutionPlanSnapshot.Step generator = executionPlan.generator();
        WorkflowCurrentStepSnapshot step = stepSnapshots.modelStep(
                executionPlan,
                result.stepId(),
                1,
                generator.purpose(),
                generator.lane(),
                "pending",
                0,
                0,
                null,
                generator.modelProfile().profile(),
                generator.modelProfile().version(),
                null);
        List<WorkflowCurrentStepSnapshot> activeSteps = List.of(step);
        return new WritingRunV2Response(
                        activeSteps,
                        result.chapterId(),
                        null,
                        null,
                        2,
                        Math.toIntExact(result.lastEventSequence()),
                        result.revision(),
                        result.runId(),
                        WritingRunV2Response.StatusEnum.fromValue(result.status()),
                        result.runId(),
                        result.workflow())
                .operation(result.operation())
                .currentStep(step);
    }

    private WritingRunV2Response response(DSLContext transaction, Record run, List<Record> activeStepRecords) {
        Map<String, Object> initial = json.readValue(run.get("modelPolicyJson", String.class), new TypeReference<>() {});
        var identity = new WorkflowExecutionContext.RunIdentity(run.get("id", String.class), run.get("workflow", String.class),
                run.get("operation", String.class), run.get("operationCatalogVersion", String.class), run.get("chapterId", String.class),
                run.get("targetType", String.class), run.get("targetId", String.class));
        WorkflowExecutionContext executionPlan = executionContexts == null
                ? WorkflowExecutionContext.fromStored(initial, null, null, identity)
                : executionContexts.load(transaction, identity, initial);
        List<WorkflowCurrentStepSnapshot> activeSteps = activeStepRecords.stream()
                .map(step -> stepSnapshot(executionPlan, step))
                .toList();
        String status = run.get("status", String.class);
        if (!activeSteps.isEmpty() && !List.of("pending", "running").contains(status)) {
            throw new IllegalStateException("非执行中 V2 WorkflowRun 含活动 Step");
        }
        WorkflowCurrentStepSnapshot current = activeSteps.isEmpty()
                ? null
                : activeSteps.getFirst();
        WritingRunV2Response response = new WritingRunV2Response(
                        activeSteps,
                        run.get("chapterId", String.class),
                        null,
                        null,
                        2,
                        Math.toIntExact(run.get("lastEventSequence", Long.class)),
                        run.get("revision", Integer.class),
                        run.get("id", String.class),
                        WritingRunV2Response.StatusEnum.fromValue(status),
                        run.get("id", String.class),
                        run.get("workflow", String.class))
                .operation(executionPlan.effectiveOperation())
                .currentStep(current)
                .cancelRequestedAt(DatabaseTimestamp.api(run.get("cancelRequestedAt", LocalDateTime.class)));
        if (executionPlan.initialIntentPlan() != null && executionContexts != null) {
            response.clarification(executionContexts.pendingClarification(transaction, run.get("id", String.class), status));
        }
        return response;
    }

    private WorkflowCurrentStepSnapshot stepSnapshot(
            WorkflowExecutionContext executionPlan, Record step) {
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

    @SuppressWarnings("unchecked")
    private static Map<String, Object> object(Object value, String label) {
        if (!(value instanceof Map<?, ?> raw)) {
            throw new IllegalStateException(label + "缺失或类型无效");
        }
        Map<String, Object> result = new LinkedHashMap<>();
        raw.forEach((key, nested) -> {
            if (!(key instanceof String text)) {
                throw new IllegalStateException(label + " key 类型无效");
            }
            result.put(text, nested);
        });
        return result;
    }

    private static String string(Map<String, Object> value, String key) {
        if (!(value.get(key) instanceof String result)) {
            throw new IllegalStateException("选区快照缺少 " + key);
        }
        return result;
    }

    private static int integer(Map<String, Object> value, String key) {
        if (!(value.get(key) instanceof Number result)) {
            throw new IllegalStateException("选区快照缺少 " + key);
        }
        return Math.toIntExact(result.longValue());
    }

    private static <T> T nullable(JsonNullable<T> value) {
        return value != null && value.isPresent() ? value.orElse(null) : null;
    }

    @FunctionalInterface
    private interface EvidencePlanner {

        PreparedStart prepare(
                DSLContext transaction,
                String userId,
                LongSerialStartWritingRunRequest request,
                LongSerialRunAssembler.Normalized normalized);
    }

    private record PreparedStart(
            String runKind,
            String targetType,
            String targetId,
            Map<String, Object> input,
            List<WorkflowEvidenceItemPlan> evidenceItems,
            Map<String, Object> userMessageSource) {

        private PreparedStart {
            runKind = Objects.requireNonNull(runKind);
            targetType = Objects.requireNonNull(targetType);
            targetId = Objects.requireNonNull(targetId);
            input = Map.copyOf(input);
            evidenceItems = List.copyOf(evidenceItems);
            userMessageSource = userMessageSource == null ? null : Map.copyOf(userMessageSource);
        }
    }
}
