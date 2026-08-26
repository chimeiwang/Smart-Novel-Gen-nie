package cn.inkforge.core.reviews.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.CHAPTERBEATPLAN;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.OUTLINE;
import static cn.inkforge.core.db.generated.Tables.OUTLINENODE;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACT;
import static cn.inkforge.core.db.generated.Tables.SCENEBEAT;
import static cn.inkforge.core.db.generated.Tables.WRITINGEVENTOUTBOX;
import static cn.inkforge.core.db.generated.Tables.WRITINGRUNCOMMAND;
import static cn.inkforge.core.db.generated.Tables.WRITINGTASK;

import cn.inkforge.contracts.api.ArtifactDecisionAcceptedResponse;
import cn.inkforge.contracts.api.ReviewArtifactDecisionRequest;
import cn.inkforge.contracts.api.SourceBinding;
import cn.inkforge.core.db.generated.enums.Reviewartifactstatus;
import cn.inkforge.core.db.generated.enums.Beatplanstatus;
import cn.inkforge.core.db.generated.tables.records.ChapterbeatplanRecord;
import cn.inkforge.core.db.generated.tables.records.ScenebeatRecord;
import cn.inkforge.core.db.generated.enums.Writingtaskphase;
import cn.inkforge.core.db.generated.tables.records.ReviewartifactRecord;
import cn.inkforge.core.db.generated.tables.records.WritingruncommandRecord;
import cn.inkforge.core.db.generated.tables.records.WritingtaskRecord;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.platform.idempotency.CommandIdempotencyStore;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.reviews.application.FormalArtifactWriter;
import cn.inkforge.core.reviews.application.ReviewArtifactState;
import cn.inkforge.core.reviews.domain.ReviewArtifactRules;
import cn.inkforge.core.reviews.domain.ReviewDecisionIdentity;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.jooq.DSLContext;
import org.jooq.Record;
import org.openapitools.jackson.nullable.JsonNullable;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/**
 * 审核决定的单事务协调器：领域正式写入、产物状态和耐久恢复命令同成同败。
 *
 * <p>事务先用用户级 advisory lock 串行化 {@code clientRequestId}，再按小说、章节、任务、Artifact、来源
 * 命令和当前命令锁定。批准时先复核冻结来源，再写正式领域数据；只有这些写入成功后才把 Artifact 标记为
 * applied 并创建恢复命令。Redis 与 Agent 不参与该事务，也不得在恢复时重复应用决定。
 */
final class JooqReviewDecisionStore {

    private static final String ACCEPTED_RESULT_FIELD =
            "_inkforgeArtifactDecisionAcceptedResponse";
    private static final List<String> ACTIVE_COMMAND_STATUSES =
            List.of("pending", "submitted", "processing");
    private static final Set<String> ENVELOPE_FIELDS = Set.of(
            "schemaVersion",
            "clientRequestId",
            "commandKind",
            "resourceIdentity",
            "normalizedBody",
            "requestFingerprint");

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final ObjectMapper json;
    private final FormalArtifactWriter formalWriter;
    private final CommandIdempotencyStore idempotency;

    JooqReviewDecisionStore(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock clock,
            ObjectMapper json,
            FormalArtifactWriter formalWriter) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
        this.formalWriter = Objects.requireNonNull(formalWriter);
        this.idempotency = new CommandIdempotencyStore(json);
    }

    ArtifactDecisionAcceptedResponse decide(
            String userId,
            String artifactId,
            ReviewArtifactDecisionRequest request) {
        ReviewDecisionIdentity identity =
                ReviewDecisionIdentity.create(artifactId, request, json);
        return database.transactionResult(transaction -> {
            // 全局命名空间先串行化请求；第一次 replay 可以在不触碰业务行锁时快速返回已提交决定。
            transaction.fetchValue(
                    "SELECT pg_advisory_xact_lock(?)",
                    CommandIdempotency.advisoryLockKey(
                            userId, request.getClientRequestId()));
            ArtifactDecisionAcceptedResponse replay = replay(
                    transaction,
                    userId,
                    request.getClientRequestId(),
                    identity.fingerprint());
            if (replay != null) return replay;

            LockedDecision locked = lockScope(transaction, userId, artifactId);
            // 等待业务锁期间另一事务可能刚提交同一请求，锁内第二次 replay 不能省略。
            replay = replay(
                    transaction,
                    userId,
                    request.getClientRequestId(),
                    identity.fingerprint());
            if (replay != null) return replay;
            ReviewartifactRecord artifact = locked.artifact();
            WritingtaskRecord task = locked.task();
            // 非 discard 决定会在这里按冻结命令重新锁定来源；过期正文/大纲不能进入正式写入阶段。
            requireDecisionPreconditions(transaction, artifact, request);

            ReviewArtifactState state = new ReviewArtifactState(
                    artifact.getId(),
                    artifact.getNovelid(),
                    artifact.getChapterid(),
                    artifact.getTaskid(),
                    artifact.getArtifactkey(),
                    artifact.getKind().getLiteral(),
                    artifact.getRevision(),
                    parseObject(artifact.getPayloadjson()));
            String decision = request.getDecision().getValue();
            int savedCount = 0;
            boolean deleted = false;
            LocalDateTime now = DatabaseTimestamp.now(clock);
            if ("discard".equals(decision)) {
                transaction.deleteFrom(REVIEWARTIFACT)
                        .where(REVIEWARTIFACT.ID.eq(artifactId))
                        .execute();
                deleted = true;
            } else if ("revise".equals(decision)) {
                transition(transaction, artifactId, Reviewartifactstatus.awaiting_user,
                        Reviewartifactstatus.draft, now, false);
            } else {
                // applying 是同一事务内的中间态；异常会整体回滚，外部永远看不到半应用结果。
                transition(transaction, artifactId, Reviewartifactstatus.awaiting_user,
                        Reviewartifactstatus.applying, now, false);
                try {
                    savedCount = formalWriter.apply(userId, state, request);
                } catch (ApiException exception) {
                    throw exception;
                } catch (RuntimeException exception) {
                    throw new ApiException(
                            409,
                            "ARTIFACT_APPLY_FAILED",
                            "草案正式写入失败，已恢复为等待确认");
                }
                transition(transaction, artifactId, Reviewartifactstatus.applying,
                        Reviewartifactstatus.applied, now, true);
            }

            String commandId = ids.next();
            ArtifactDecisionAcceptedResponse accepted =
                    new ArtifactDecisionAcceptedResponse(
                                    artifactId,
                                    commandId,
                                    ArtifactDecisionAcceptedResponse.DecisionEnum.fromValue(decision),
                                    ArtifactDecisionAcceptedResponse.StatusEnum.PENDING,
                                    task.getId())
                            .savedCount(savedCount)
                            .deleted(deleted);
            // 决定命令与正式数据同事务提交，Agent 后续只恢复图，不再执行上面的写入。
            persistCommand(
                    transaction,
                    userId,
                    artifactId,
                    task,
                    request,
                    identity,
                    accepted,
                    now);
            return accepted;
        });
    }

    private LockedDecision lockScope(
            DSLContext transaction, String userId, String artifactId) {
        Record identity = transaction.select(
                        REVIEWARTIFACT.NOVELID,
                        REVIEWARTIFACT.CHAPTERID,
                        REVIEWARTIFACT.TASKID)
                .from(REVIEWARTIFACT)
                .join(NOVEL)
                .on(NOVEL.ID.eq(REVIEWARTIFACT.NOVELID))
                .where(REVIEWARTIFACT.ID.eq(artifactId), NOVEL.USERID.eq(userId))
                .fetchOne();
        if (identity == null) throw forbidden();
        String novelId = identity.get(REVIEWARTIFACT.NOVELID);
        String chapterId = identity.get(REVIEWARTIFACT.CHAPTERID);
        String taskId = identity.get(REVIEWARTIFACT.TASKID);
        if (taskId == null) {
            throw new ApiException(
                    409, "ARTIFACT_TASK_MISSING", "待审核草案没有关联写作任务");
        }
        String owner = transaction.select(NOVEL.USERID)
                .from(NOVEL)
                .where(NOVEL.ID.eq(novelId))
                .forUpdate()
                .fetchOne(NOVEL.USERID);
        if (!userId.equals(owner)) throw forbidden();
        if (chapterId != null) {
            transaction.select(CHAPTER.ID)
                    .from(CHAPTER)
                    .where(CHAPTER.ID.eq(chapterId), CHAPTER.NOVELID.eq(novelId))
                    .forUpdate()
                    .fetch();
        }
        WritingtaskRecord task = transaction.selectFrom(WRITINGTASK)
                .where(WRITINGTASK.ID.eq(taskId), WRITINGTASK.NOVELID.eq(novelId))
                .forUpdate()
                .fetchOne();
        ReviewartifactRecord artifact = transaction.selectFrom(REVIEWARTIFACT)
                .where(
                        REVIEWARTIFACT.ID.eq(artifactId),
                        REVIEWARTIFACT.NOVELID.eq(novelId),
                        REVIEWARTIFACT.TASKID.eq(taskId))
                .forUpdate()
                .fetchOne();
        if (task == null || artifact == null) throw forbidden();
        List<WritingruncommandRecord> commands = transaction.selectFrom(WRITINGRUNCOMMAND)
                .where(WRITINGRUNCOMMAND.TASKID.eq(taskId))
                .orderBy(WRITINGRUNCOMMAND.CREATEDAT.asc(), WRITINGRUNCOMMAND.ID.asc())
                .forUpdate()
                .fetch();
        WritingruncommandRecord active = commands.stream()
                .filter(value -> ACTIVE_COMMAND_STATUSES.contains(value.getStatus()))
                .findFirst()
                .orElse(null);
        if (active != null) {
            throw new ApiException(
                    409,
                    "WRITING_COMMAND_ACTIVE",
                    "该写作任务已有正在处理的命令",
                    Map.of("taskId", taskId));
        }
        if (task.getPhase() != Writingtaskphase.awaiting_user_review) {
            throw new ApiException(
                    409,
                    "ARTIFACT_NOT_AWAITING_USER",
                    "当前写作任务不在等待草案决定状态");
        }
        return new LockedDecision(artifact, task);
    }

    private void requireDecisionPreconditions(
            DSLContext transaction,
            ReviewartifactRecord artifact,
            ReviewArtifactDecisionRequest request) {
        if (!artifact.getRevision().equals(request.getExpectedRevision())) {
            throw new ApiException(
                    409,
                    "ARTIFACT_REVISION_CONFLICT",
                    "待审核草案修订号已变化",
                    Map.of(
                            "expectedRevision", request.getExpectedRevision(),
                            "currentRevision", artifact.getRevision()));
        }
        if (artifact.getStatus() != Reviewartifactstatus.awaiting_user) {
            throw new ApiException(
                    409,
                    "ARTIFACT_NOT_AWAITING_USER",
                    "当前草案状态不能接受用户决定");
        }
        if (artifact.getArtifactkey() != null
                && artifact.getArtifactkey().startsWith("short-medium:")) {
            throw new ApiException(
                    409,
                    "SHORT_MEDIUM_VERSION_ROUTE_REQUIRED",
                    "中短篇版本只能通过专用版本接口操作");
        }
        if (request.getDecision() != ReviewArtifactDecisionRequest.DecisionEnum.DISCARD
                && requiresSourceBindings(transaction, artifact)) {
            verifySourceBindings(transaction, artifact);
        }
    }

    private void persistCommand(
            DSLContext transaction,
            String userId,
            String artifactId,
            WritingtaskRecord task,
            ReviewArtifactDecisionRequest request,
            ReviewDecisionIdentity identity,
            ArtifactDecisionAcceptedResponse accepted,
            LocalDateTime now) {
        Map<String, Object> resumeInput = new LinkedHashMap<>();
        resumeInput.put("artifactId", artifactId);
        resumeInput.put("decision", request.getDecision().getValue());
        String userMessage = nullable(request.getUserMessage());
        if (userMessage != null) resumeInput.put("userMessage", userMessage);
        Map<String, Object> job = resumeJob(transaction, task, resumeInput);
        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("schemaVersion", 1);
        metadata.put("clientRequestId", request.getClientRequestId());
        metadata.put("commandKind", "artifact_decision");
        metadata.put("resourceIdentity", Map.of("artifactId", artifactId));
        metadata.put("normalizedBody", identity.normalizedBody());
        metadata.put("requestFingerprint", identity.fingerprint());
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("_inkforgeCommand", metadata);
        payload.put("job", job);

        Map<String, Object> acceptedMap = acceptedMap(accepted);
        Map<String, Object> result = new LinkedHashMap<>(acceptedMap);
        result.put(ACCEPTED_RESULT_FIELD, new LinkedHashMap<>(acceptedMap));
        transaction.insertInto(WRITINGRUNCOMMAND)
                .set(WRITINGRUNCOMMAND.ID, accepted.getCommandId())
                .set(WRITINGRUNCOMMAND.TASKID, task.getId())
                .set(WRITINGRUNCOMMAND.KIND, "artifact_decision")
                .set(WRITINGRUNCOMMAND.ARTIFACTID, artifactId)
                .set(WRITINGRUNCOMMAND.DECISION, request.getDecision().getValue())
                .set(WRITINGRUNCOMMAND.PAYLOADJSON, json.writeValueAsString(payload))
                .set(WRITINGRUNCOMMAND.RESULTJSON, json.writeValueAsString(result))
                .set(
                        WRITINGRUNCOMMAND.IDEMPOTENCYKEY,
                        CommandIdempotency.envelopedKey(
                                userId, request.getClientRequestId()))
                .set(WRITINGRUNCOMMAND.STATUS, "pending")
                .set(WRITINGRUNCOMMAND.ATTEMPTCOUNT, 0)
                .set(WRITINGRUNCOMMAND.NEXTATTEMPTAT, now)
                .set(WRITINGRUNCOMMAND.CREATEDAT, now)
                .set(WRITINGRUNCOMMAND.UPDATEDAT, now)
                .execute();
        // 新决定已取代旧 waiting 边界；若旧事件稍后发布，会重新制造已经失效的操作入口。
        transaction.update(WRITINGEVENTOUTBOX)
                .set(WRITINGEVENTOUTBOX.DELIVERYSTATE, "superseded")
                .set(WRITINGEVENTOUTBOX.LASTERRORCODE, "OUTBOX_WAITING_SUPERSEDED")
                .setNull(WRITINGEVENTOUTBOX.LEASETOKEN)
                .setNull(WRITINGEVENTOUTBOX.LEASEEXPIRESAT)
                .set(WRITINGEVENTOUTBOX.UPDATEDAT, now)
                .where(
                        WRITINGEVENTOUTBOX.TASKID.eq(task.getId()),
                        WRITINGEVENTOUTBOX.EVENTTYPE.eq(
                                "artifact_awaiting_user_approval"),
                        WRITINGEVENTOUTBOX.DELIVERYSTATE.in(
                                "pending", "delivering", "blocked"))
                .execute();
    }

    private Map<String, Object> resumeJob(
            DSLContext transaction,
            WritingtaskRecord task,
            Map<String, Object> resumeInput) {
        // 继续沿用最初 start 的冻结 job，不能从当前工作区重建后改变本次任务的证据范围。
        String startJson = transaction.select(WRITINGRUNCOMMAND.PAYLOADJSON)
                .from(WRITINGRUNCOMMAND)
                .where(
                        WRITINGRUNCOMMAND.TASKID.eq(task.getId()),
                        WRITINGRUNCOMMAND.KIND.eq("start"))
                .orderBy(WRITINGRUNCOMMAND.CREATEDAT.asc(), WRITINGRUNCOMMAND.ID.asc())
                .limit(1)
                .fetchOne(WRITINGRUNCOMMAND.PAYLOADJSON);
        Map<String, Object> payload = parseObjectOrNull(startJson);
        if (payload == null || !payload.containsKey("_inkforgeCommand")) {
            return basicResumeJob(task, resumeInput);
        }
        Map<String, Object> metadata = strictEnvelope(payload.get("_inkforgeCommand"));
        Object rawJob = payload.get("job");
        Map<String, Object> startJob = rawJob instanceof Map<?, ?> value
                ? stringMap(value)
                : null;
        Object normalized = metadata.get("normalizedBody");
        boolean declaresLongSerial = normalized instanceof Map<?, ?> body
                && "long_serial".equals(body.get("workflow"));
        if (!declaresLongSerial
                && (startJob == null || !"long_serial".equals(startJob.get("workflow")))) {
            return basicResumeJob(task, resumeInput);
        }
        boolean valid = "start".equals(metadata.get("commandKind"))
                && payload.keySet().equals(Set.of("_inkforgeCommand", "job"))
                && startJob != null
                && "long_serial".equals(startJob.get("workflow"))
                && Boolean.FALSE.equals(startJob.get("resume"))
                && Objects.equals(startJob.get("chapterId"), task.getChapterid())
                && Objects.equals(startJob.get("writingSessionId"), task.getWritingsessionid())
                && startJob.get("target") instanceof Map<?, ?> target
                && "chapter".equals(target.get("type"))
                && Objects.equals(target.get("id"), task.getChapterid());
        if (!valid) throw new IllegalStateException("显式长篇启动命令与任务身份不一致");
        Map<String, Object> result = new LinkedHashMap<>(startJob);
        result.put("resume", true);
        result.put("resumeInput", new LinkedHashMap<>(resumeInput));
        if (result.get("selectionTarget") == null) {
            result.remove("selectionTarget");
            result.remove("selectionSnapshot");
        }
        return result;
    }

    private static Map<String, Object> basicResumeJob(
            WritingtaskRecord task, Map<String, Object> resumeInput) {
        Map<String, Object> job = new LinkedHashMap<>();
        job.put("version", 1);
        job.put("resume", true);
        job.put("chapterId", task.getChapterid());
        job.put("writingSessionId", task.getWritingsessionid());
        job.put("resumeInput", new LinkedHashMap<>(resumeInput));
        return job;
    }

    private static Map<String, Object> strictEnvelope(Object raw) {
        if (!(raw instanceof Map<?, ?> value)) {
            throw new IllegalStateException("显式长篇启动命令 envelope 无效");
        }
        Map<String, Object> metadata = stringMap(value);
        boolean valid = metadata.keySet().equals(ENVELOPE_FIELDS)
                && Integer.valueOf(1).equals(metadata.get("schemaVersion"))
                && metadata.get("clientRequestId") instanceof String client
                && !client.isEmpty()
                && metadata.get("commandKind") instanceof String commandKind
                && !commandKind.isEmpty()
                && metadata.get("resourceIdentity") instanceof Map<?, ?>
                && metadata.get("normalizedBody") instanceof Map<?, ?>
                && metadata.get("requestFingerprint") instanceof String fingerprint
                && fingerprint.matches("[0-9a-f]{64}");
        if (!valid) throw new IllegalStateException("显式长篇启动命令 envelope 无效");
        return metadata;
    }

    private ArtifactDecisionAcceptedResponse replay(
            DSLContext transaction,
            String userId,
            String clientRequestId,
            String fingerprint) {
        CommandIdempotencyStore.Resolution match = idempotency.resolve(
                transaction, userId, clientRequestId, fingerprint);
        if (match == null) return null;
        if (match.recordKind() != CommandIdempotencyStore.RecordKind.WRITING_COMMAND
                || !"artifact_decision".equals(match.metadata().commandKind())) {
            throw idempotencyReused(clientRequestId);
        }
        WritingruncommandRecord command = transaction.selectFrom(WRITINGRUNCOMMAND)
                .where(WRITINGRUNCOMMAND.ID.eq(match.recordId()))
                .fetchOne();
        if (command == null || !"artifact_decision".equals(command.getKind())) {
            throw idempotencyReused(clientRequestId);
        }
        Map<String, Object> persisted = parseObjectOrNull(command.getResultjson());
        if (persisted == null) throw idempotencyReused(clientRequestId);
        Object nested = persisted.get(ACCEPTED_RESULT_FIELD);
        Map<String, Object> source = nested instanceof Map<?, ?> value
                ? stringMap(value)
                : persisted;
        return acceptedResponse(source);
    }

    private ArtifactDecisionAcceptedResponse acceptedResponse(Map<String, Object> source) {
        try {
            String artifactId = requiredString(source, "artifactId");
            String commandId = requiredString(source, "commandId");
            String decision = requiredString(source, "decision");
            String status = requiredString(source, "status");
            String taskId = requiredString(source, "taskId");
            int savedCount = source.get("savedCount") instanceof Number value
                    ? value.intValue()
                    : 0;
            boolean deleted = source.get("deleted") instanceof Boolean value && value;
            return new ArtifactDecisionAcceptedResponse(
                            artifactId,
                            commandId,
                            ArtifactDecisionAcceptedResponse.DecisionEnum.fromValue(decision),
                            ArtifactDecisionAcceptedResponse.StatusEnum.fromValue(status),
                            taskId)
                    .savedCount(savedCount)
                    .deleted(deleted);
        } catch (RuntimeException exception) {
            throw new ApiException(
                    409,
                    "WRITING_COMMAND_RESULT_INVALID",
                    "写作命令受理结果无效");
        }
    }

    private boolean requiresSourceBindings(
            DSLContext context, ReviewartifactRecord artifact) {
        String kind = artifact.getKind().getLiteral();
        if ("beat_plan".equals(kind) || "chapter_draft".equals(kind)) return true;
        if (!"outline_draft".equals(kind) || artifact.getTaskid() == null) return false;
        String payloadJson = context.select(WRITINGRUNCOMMAND.PAYLOADJSON)
                .from(WRITINGRUNCOMMAND)
                .where(
                        WRITINGRUNCOMMAND.TASKID.eq(artifact.getTaskid()),
                        WRITINGRUNCOMMAND.KIND.eq("start"))
                .orderBy(WRITINGRUNCOMMAND.CREATEDAT.asc(), WRITINGRUNCOMMAND.ID.asc())
                .limit(1)
                .fetchOne(WRITINGRUNCOMMAND.PAYLOADJSON);
        Map<String, Object> payload = parseObjectOrNull(payloadJson);
        Object jobValue = payload == null ? null : payload.get("job");
        Map<?, ?> source = jobValue instanceof Map<?, ?> job ? job : payload;
        return source != null
                && "long_serial".equals(source.get("workflow"))
                && "rewrite_outline_selection".equals(source.get("operation"));
    }

    private void verifySourceBindings(
            DSLContext transaction, ReviewartifactRecord artifact) {
        Map<String, Object> payload = parseObject(artifact.getPayloadjson());
        Object controlValue = payload.get("_inkforgeControl");
        String sourceCommandId = controlValue instanceof Map<?, ?> control
                        && control.get("sourceCommandId") instanceof String value
                ? value
                : null;
        if (sourceCommandId == null || artifact.getTaskid() == null) {
            throw new ApiException(
                    409,
                    "ARTIFACT_SOURCE_BINDINGS_MISSING",
                    "待审核草案缺少权威来源绑定");
        }
        String commandPayload = transaction.select(WRITINGRUNCOMMAND.PAYLOADJSON)
                .from(WRITINGRUNCOMMAND)
                .where(
                        WRITINGRUNCOMMAND.ID.eq(sourceCommandId),
                        WRITINGRUNCOMMAND.TASKID.eq(artifact.getTaskid()),
                        WRITINGRUNCOMMAND.KIND.eq("start"))
                .forUpdate()
                .fetchOne(WRITINGRUNCOMMAND.PAYLOADJSON);
        Map<String, Object> command = parseObjectOrNull(commandPayload);
        Object jobValue = command == null ? null : command.get("job");
        Map<?, ?> source = jobValue instanceof Map<?, ?> job ? job : command;
        Object rawBindings = source == null ? null : source.get("sourceBindings");
        if (!(rawBindings instanceof List<?> values) || values.isEmpty()) {
            throw new ApiException(
                    409,
                    "ARTIFACT_SOURCE_BINDINGS_MISSING",
                    "待审核草案缺少权威来源绑定");
        }
        // 按资源类型与 ID 排序后加锁，使多个来源的批准请求保持确定的跨表锁顺序。
        List<SourceBinding> bindings = values.stream()
                .map(value -> json.convertValue(value, SourceBinding.class))
                .sorted(java.util.Comparator.comparing(SourceBinding::getResourceType)
                        .thenComparing(SourceBinding::getResourceId))
                .toList();
        for (SourceBinding binding : bindings) verifySourceBinding(transaction, binding);
    }

    private void verifySourceBinding(DSLContext transaction, SourceBinding binding) {
        switch (binding.getResourceType()) {
            case "chapter", "chapter_content" -> verifyExistingText(
                    binding,
                    transaction.select(CHAPTER.CONTENT, CHAPTER.UPDATEDAT)
                            .from(CHAPTER)
                            .where(CHAPTER.ID.eq(binding.getResourceId()))
                            .forUpdate()
                            .fetchOne(),
                    CHAPTER.CONTENT,
                    CHAPTER.UPDATEDAT);
            case "outline_content" -> verifyExistingText(
                    binding,
                    transaction.select(OUTLINE.CONTENT, OUTLINE.UPDATEDAT)
                            .from(OUTLINE)
                            .where(OUTLINE.ID.eq(binding.getResourceId()))
                            .forUpdate()
                            .fetchOne(),
                    OUTLINE.CONTENT,
                    OUTLINE.UPDATEDAT);
            case "outline_node_content" -> verifyExistingText(
                    binding,
                    transaction.select(OUTLINENODE.CONTENT, OUTLINENODE.UPDATEDAT)
                            .from(OUTLINENODE)
                            .where(OUTLINENODE.ID.eq(binding.getResourceId()))
                            .forUpdate()
                            .fetchOne(),
                    OUTLINENODE.CONTENT,
                    OUTLINENODE.UPDATEDAT);
            case "outline" -> verifyOutline(transaction, binding);
            case "approved_beat_plan" -> verifyApprovedBeatPlan(transaction, binding);
            default -> throw invalidSourceBinding(binding);
        }
    }

    private <R extends org.jooq.Record, T extends org.jooq.Record> void verifyExistingText(
            SourceBinding binding,
            R record,
            org.jooq.TableField<T, String> contentField,
            org.jooq.TableField<T, LocalDateTime> updatedAtField) {
        String content = record == null ? null : record.get(contentField);
        LocalDateTime updatedAt = record == null ? null : record.get(updatedAtField);
        boolean matches = Boolean.TRUE.equals(binding.getExists())
                && binding.getAbsenceSentinel() == null
                && binding.getRevision() == null
                && content != null
                && updatedAt != null
                && Objects.equals(DatabaseTimestamp.api(updatedAt), binding.getUpdatedAt())
                && Objects.equals(
                        ReviewArtifactRules.sha256(content), binding.getContentSha256());
        if (!matches) throw sourceConflict(binding);
    }

    private void verifyOutline(DSLContext transaction, SourceBinding binding) {
        if (Boolean.TRUE.equals(binding.getExists())) {
            verifyExistingText(
                    binding,
                    transaction.select(OUTLINE.CONTENT, OUTLINE.UPDATEDAT)
                            .from(OUTLINE)
                            .where(OUTLINE.ID.eq(binding.getResourceId()))
                            .forUpdate()
                            .fetchOne(),
                    OUTLINE.CONTENT,
                    OUTLINE.UPDATEDAT);
            return;
        }
        var sentinel = binding.getAbsenceSentinel();
        boolean valid = sentinel != null
                && "novel".equals(sentinel.getResourceType())
                && ("novel:" + sentinel.getResourceId() + ":outline")
                        .equals(binding.getResourceId())
                && transaction.select(OUTLINE.ID)
                        .from(OUTLINE)
                        .where(OUTLINE.NOVELID.eq(sentinel.getResourceId()))
                        .forUpdate()
                        .fetchOne(OUTLINE.ID) == null;
        if (!valid) throw sourceConflict(binding);
    }

    private void verifyApprovedBeatPlan(
            DSLContext transaction, SourceBinding binding) {
        if (!Boolean.TRUE.equals(binding.getExists())) {
            var sentinel = binding.getAbsenceSentinel();
            if (sentinel == null
                    || !"chapter".equals(sentinel.getResourceType())
                    || !("chapter:" + sentinel.getResourceId() + ":approved_beat_plan")
                            .equals(binding.getResourceId())) {
                throw sourceConflict(binding);
            }
            List<ChapterbeatplanRecord> approved = approvedPlans(
                    transaction, sentinel.getResourceId());
            if (approved.size() > 1) throw ambiguousBeatPlan(sentinel.getResourceId());
            if (!approved.isEmpty()) throw sourceConflict(binding);
            return;
        }
        ChapterbeatplanRecord plan = transaction.selectFrom(CHAPTERBEATPLAN)
                .where(
                        CHAPTERBEATPLAN.ID.eq(binding.getResourceId()),
                        CHAPTERBEATPLAN.STATUS.eq(Beatplanstatus.approved))
                .forUpdate()
                .fetchOne();
        if (plan == null) throw sourceConflict(binding);
        List<ChapterbeatplanRecord> approved = approvedPlans(transaction, plan.getChapterid());
        if (approved.size() > 1) throw ambiguousBeatPlan(plan.getChapterid());
        if (approved.size() != 1 || !approved.getFirst().getId().equals(plan.getId())) {
            throw sourceConflict(binding);
        }
        List<ScenebeatRecord> beats = transaction.selectFrom(SCENEBEAT)
                .where(SCENEBEAT.BEATPLANID.eq(plan.getId()))
                .orderBy(SCENEBEAT.ORDER.asc(), SCENEBEAT.ID.asc())
                .forUpdate()
                .fetch();
        String hash = CommandIdempotency.sha256(
                CommandIdempotency.canonicalJsonBytes(beatPlanPayload(plan, beats), json));
        boolean matches = binding.getAbsenceSentinel() == null
                && binding.getRevision() == null
                && Objects.equals(DatabaseTimestamp.api(plan.getUpdatedat()), binding.getUpdatedAt())
                && Objects.equals(hash, binding.getContentSha256());
        if (!matches) throw sourceConflict(binding);
    }

    private static List<ChapterbeatplanRecord> approvedPlans(
            DSLContext transaction, String chapterId) {
        return transaction.selectFrom(CHAPTERBEATPLAN)
                .where(
                        CHAPTERBEATPLAN.CHAPTERID.eq(chapterId),
                        CHAPTERBEATPLAN.STATUS.eq(Beatplanstatus.approved))
                .orderBy(CHAPTERBEATPLAN.ID.asc())
                .forUpdate()
                .fetch();
    }

    private static Map<String, Object> beatPlanPayload(
            ChapterbeatplanRecord plan, List<ScenebeatRecord> beats) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("id", plan.getId());
        payload.put("chapterId", plan.getChapterid());
        payload.put("goalId", plan.getGoalid());
        payload.put("status", plan.getStatus().getLiteral());
        payload.put("chapterGoal", plan.getChaptergoal());
        payload.put("mainPlotConnection", plan.getMainplotconnection());
        payload.put("chapterAcceptanceCriteria", plan.getChapteracceptancecriteria());
        payload.put("totalEstimatedWords", plan.getTotalestimatedwords());
        payload.put("generatedBy", plan.getGeneratedby());
        payload.put("createdAt", DatabaseTimestamp.api(plan.getCreatedat()));
        payload.put("updatedAt", DatabaseTimestamp.api(plan.getUpdatedat()));
        List<Map<String, Object>> sceneValues = new ArrayList<>();
        for (ScenebeatRecord beat : beats) {
            Map<String, Object> scene = new LinkedHashMap<>();
            scene.put("id", beat.getId());
            scene.put("order", beat.getOrder());
            scene.put("goal", beat.getGoal());
            scene.put("conflict", beat.getConflict());
            scene.put("characters", beat.getCharacters());
            scene.put("foreshadowingRefs", beat.getForeshadowingrefs());
            scene.put("estimatedWords", beat.getEstimatedwords());
            scene.put("acceptanceCriteria", beat.getAcceptancecriteria());
            sceneValues.add(scene);
        }
        payload.put("sceneBeats", sceneValues);
        return payload;
    }

    private static ApiException invalidSourceBinding(SourceBinding binding) {
        return new ApiException(
                409,
                "ARTIFACT_SOURCE_BINDING_INVALID",
                "审核产物包含不受支持的来源绑定",
                Map.of(
                        "resourceType", binding.getResourceType(),
                        "resourceId", binding.getResourceId()));
    }

    private static ApiException sourceConflict(SourceBinding binding) {
        return new ApiException(
                409,
                "ARTIFACT_SOURCE_VERSION_CONFLICT",
                "审核产物的来源版本已变化",
                Map.of(
                        "resourceType", binding.getResourceType(),
                        "resourceId", binding.getResourceId()));
    }

    private static ApiException ambiguousBeatPlan(String chapterId) {
        return new ApiException(
                409,
                "BEAT_PLAN_SOURCE_AMBIGUOUS",
                "章节存在多个已批准计划，无法确定权威来源",
                Map.of("chapterId", chapterId));
    }

    private static void transition(
            DSLContext transaction,
            String artifactId,
            Reviewartifactstatus current,
            Reviewartifactstatus target,
            LocalDateTime now,
            boolean applied) {
        var update = transaction.update(REVIEWARTIFACT)
                .set(REVIEWARTIFACT.STATUS, target)
                .set(REVIEWARTIFACT.UPDATEDAT, now);
        if (applied) update.set(REVIEWARTIFACT.APPLIEDAT, now);
        int changed = update.where(
                        REVIEWARTIFACT.ID.eq(artifactId),
                        REVIEWARTIFACT.STATUS.eq(current))
                .execute();
        if (changed != 1) {
            throw new ApiException(
                    409,
                    "ARTIFACT_STATUS_CONFLICT",
                    "待审核草案状态已被其他请求修改");
        }
    }

    private Map<String, Object> parseObject(String value) {
        Map<String, Object> result = parseObjectOrNull(value);
        if (result == null) {
            throw new ApiException(
                    409,
                    "ARTIFACT_PAYLOAD_INVALID",
                    "待审核草案持久化内容格式错误");
        }
        return result;
    }

    private Map<String, Object> parseObjectOrNull(String value) {
        if (value == null) return null;
        try {
            return json.readValue(value, new TypeReference<>() {});
        } catch (RuntimeException exception) {
            return null;
        }
    }

    private static Map<String, Object> acceptedMap(
            ArtifactDecisionAcceptedResponse accepted) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("artifactId", accepted.getArtifactId());
        value.put("taskId", accepted.getTaskId());
        value.put("commandId", accepted.getCommandId());
        value.put("decision", accepted.getDecision().getValue());
        value.put("status", accepted.getStatus().getValue());
        value.put("savedCount", accepted.getSavedCount());
        value.put("deleted", accepted.getDeleted());
        return value;
    }

    private static Map<String, Object> stringMap(Map<?, ?> value) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : value.entrySet()) {
            if (!(entry.getKey() instanceof String key)) {
                throw new IllegalArgumentException("JSON 对象键必须是字符串");
            }
            result.put(key, entry.getValue());
        }
        return result;
    }

    private static String requiredString(Map<String, Object> source, String field) {
        if (source.get(field) instanceof String value && !value.isEmpty()) return value;
        throw new IllegalArgumentException("缺少字段 " + field);
    }

    private static <T> T nullable(JsonNullable<T> value) {
        return value == null || value.isUndefined() ? null : value.orElse(null);
    }

    private static ApiException forbidden() {
        return new ApiException(
                403, "REVIEW_ARTIFACT_FORBIDDEN", "无权访问该待审核草案");
    }

    private static ApiException idempotencyReused(String clientRequestId) {
        return new ApiException(
                409,
                "IDEMPOTENCY_KEY_REUSED",
                "同一幂等标识已绑定其他请求",
                Map.of("clientRequestId", clientRequestId));
    }

    private record LockedDecision(
            ReviewartifactRecord artifact, WritingtaskRecord task) {}

}
