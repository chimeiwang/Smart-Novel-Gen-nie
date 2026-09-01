package cn.inkforge.core.writing.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACT;
import static cn.inkforge.core.db.generated.Tables.WRITINGBIBLE;
import static cn.inkforge.core.db.generated.Tables.WRITINGEVENTOUTBOX;
import static cn.inkforge.core.db.generated.Tables.WRITINGMESSAGE;
import static cn.inkforge.core.db.generated.Tables.WRITINGRUNCOMMAND;
import static cn.inkforge.core.db.generated.Tables.WRITINGSESSION;
import static cn.inkforge.core.db.generated.Tables.WRITINGTASK;

import cn.inkforge.contracts.api.LongSerialStartWritingRunRequest;
import cn.inkforge.contracts.api.CancelWritingRunRequest;
import cn.inkforge.contracts.api.CancelWritingRunResponse;
import cn.inkforge.contracts.api.ResumeWritingRunRequest;
import cn.inkforge.contracts.api.ResumeWritingRunResponse;
import cn.inkforge.contracts.api.ShortMediumStartWritingRunRequest;
import cn.inkforge.contracts.api.StartWritingRunRequest;
import cn.inkforge.contracts.api.WritingRunResponse;
import cn.inkforge.core.db.generated.enums.Storylengthprofile;
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
import cn.inkforge.core.writing.application.ParsedWritingRunStartRequest;
import cn.inkforge.core.writing.application.WritingCommandRepository;
import cn.inkforge.core.writing.domain.WritingRecoverability;
import cn.inkforge.core.workflows.domain.WorkflowMessageMetadata;
import cn.inkforge.core.writing.domain.WritingRunOutcomeProjector;
import cn.inkforge.core.writing.domain.WritingRunStatusProjector;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.jooq.DSLContext;
import org.jooq.Record;
import org.jooq.Record2;
import org.openapitools.jackson.nullable.JsonNullable;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/**
 * PostgreSQL 写作命令仓储。
 *
 * <p>任务、首条命令、会话消息和来源快照始终在一个事务内写入；显式长篇使用用户级 advisory lock 与
 * 跨控制面幂等信封，旧请求继续保留冻结的兼容键语义。所有入口先串行化同一用户请求，再做幂等重放，
 * 最后按小说、章节、会话/任务和命令顺序加锁；不能先创建任务再补来源快照。Agent 投递不属于该事务，
 * 只消费已经耐久保存的命令。
 */
final class JooqWritingCommandRepository implements WritingCommandRepository {

    private static final Set<String> ACTIVE_COMMANDS = Set.of("pending", "submitted", "processing");

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final ObjectMapper json;
    private final CommandIdempotencyStore idempotency;
    private final WritingSourceBindingCapture sourceBindings;
    private final LongSerialRunAssembler longSerial;
    private final ShortMediumRunAssembler shortMedium;
    private final WritingRunStatusProjector statusProjector;

    JooqWritingCommandRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock clock,
            ObjectMapper json,
            CommandIdempotencyStore idempotency) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
        this.idempotency = Objects.requireNonNull(idempotency);
        this.sourceBindings = new WritingSourceBindingCapture(json);
        this.longSerial = new LongSerialRunAssembler(json, sourceBindings);
        this.shortMedium = new ShortMediumRunAssembler(json);
        this.statusProjector = new WritingRunStatusProjector(
                json, new WritingRunOutcomeProjector(), clock);
    }

    @Override
    public WritingRunResponse start(String userId, ParsedWritingRunStartRequest request) {
        if (request instanceof ParsedWritingRunStartRequest.LongSerial value) {
            return startLongSerial(userId, value.request());
        }
        if (request instanceof ParsedWritingRunStartRequest.Legacy value) {
            return startLegacy(userId, value.request());
        }
        return startShortMedium(
                userId, ((ParsedWritingRunStartRequest.ShortMedium) request).request());
    }

    @Override
    public ResumeWritingRunResponse resume(
            String userId, String taskId, ResumeWritingRunRequest request) {
        Map<String, Object> normalizedBody = new LinkedHashMap<>();
        normalizedBody.put("writingSessionId", nullable(request.getWritingSessionId()));
        normalizedBody.put("userMessage", nullable(request.getUserMessage()));
        Map<String, Object> resourceIdentity = Map.of("taskId", taskId);
        String fingerprint = CommandIdempotency.requestFingerprint(
                "resume", resourceIdentity, normalizedBody, json);
        String key = CommandIdempotency.envelopedKey(userId, request.getClientRequestId());
        return database.transactionResult(transaction -> {
            // advisory lock 先于任何跨表锁，避免两个相同请求各自读到“尚无命令”后重复创建。
            advisoryLock(transaction, userId, request.getClientRequestId());
            ResumeWritingRunResponse replay = resumeReplay(
                    transaction,
                    userId,
                    taskId,
                    request.getClientRequestId(),
                    fingerprint);
            if (replay != null) return replay;
            TaskIdentity identity = taskIdentity(transaction, userId, taskId);
            WritingtaskRecord task = lockTask(
                    transaction, userId, identity.novelId(), identity.chapterId(), taskId);
            WritingruncommandRecord current = currentCommand(transaction, taskId, true);
            // 等待锁期间可能已有并发请求提交，所以在完整业务锁内必须再做一次重放解析。
            replay = resumeReplay(
                    transaction,
                    userId,
                    taskId,
                    request.getClientRequestId(),
                    fingerprint);
            if (replay != null) return replay;
            if (task.getPhase() == Writingtaskphase.completed
                    || task.getPhase() == Writingtaskphase.error) {
                throw new ApiException(
                        409, "WRITING_TASK_TERMINAL", "已完成或失败的任务不能继续恢复");
            }
            String requestedSession = nullable(request.getWritingSessionId());
            if (requestedSession != null
                    && !requestedSession.equals(task.getWritingsessionid())) {
                throw new ApiException(
                        409, "WRITING_SESSION_MISMATCH", "当前任务不属于所选写作会话");
            }
            requireNoActiveCommand(transaction, taskId);
            String awaitingArtifact = transaction.select(REVIEWARTIFACT.ID)
                    .from(REVIEWARTIFACT)
                    .where(
                            REVIEWARTIFACT.TASKID.eq(taskId),
                            REVIEWARTIFACT.NOVELID.eq(task.getNovelid()),
                            REVIEWARTIFACT.CHAPTERID.eq(task.getChapterid()),
                            REVIEWARTIFACT.STATUS.eq(
                                    cn.inkforge.core.db.generated.enums.Reviewartifactstatus.awaiting_user))
                    .fetchAny(REVIEWARTIFACT.ID);
            if (awaitingArtifact != null) {
                throw new ApiException(
                        409,
                        "ARTIFACT_DECISION_REQUIRED",
                        "存在等待用户决策的审核产物，必须先提交审核决定");
            }
            String visibleMessage = Objects.toString(nullable(request.getUserMessage()), "").strip();
            List<WritingruncommandRecord> commands = transaction.selectFrom(WRITINGRUNCOMMAND)
                    .where(WRITINGRUNCOMMAND.TASKID.eq(taskId))
                    .orderBy(WRITINGRUNCOMMAND.CREATEDAT.desc(), WRITINGRUNCOMMAND.ID.desc())
                    .fetch();
            if (visibleMessage.isEmpty()
                    && WritingRecoverability.resolve(task, commands, json) == null) {
                throw new ApiException(
                        409,
                        "WRITING_RUN_NOT_RECOVERABLE",
                        "当前写作任务没有可恢复的持久检查点");
            }
            if (!visibleMessage.isEmpty() && task.getWritingsessionid() != null) {
                insertMessage(
                        transaction,
                        task.getWritingsessionid(),
                        taskId,
                        visibleMessage,
                        null);
            }
            Map<String, Object> resumeInput = new LinkedHashMap<>();
            String userMessage = nullable(request.getUserMessage());
            if (userMessage != null) resumeInput.put("userMessage", userMessage);
            Map<String, Object> job = resumeJob(transaction, task, resumeInput);
            Map<String, Object> metadata = new LinkedHashMap<>();
            metadata.put("schemaVersion", 1);
            metadata.put("clientRequestId", request.getClientRequestId());
            metadata.put("commandKind", "resume");
            metadata.put("resourceIdentity", resourceIdentity);
            metadata.put("normalizedBody", normalizedBody);
            metadata.put("requestFingerprint", fingerprint);
            Map<String, Object> envelope = new LinkedHashMap<>();
            envelope.put("_inkforgeCommand", metadata);
            envelope.put("job", job);
            LocalDateTime now = DatabaseTimestamp.now(clock);
            WritingruncommandRecord command = transaction.newRecord(WRITINGRUNCOMMAND);
            command.setId(ids.next());
            command.setTaskid(taskId);
            command.setKind("resume");
            command.setPayloadjson(json.writeValueAsString(envelope));
            command.setIdempotencykey(key);
            command.setStatus("pending");
            command.setAttemptcount(0);
            command.setNextattemptat(now);
            command.setCreatedat(now);
            command.setUpdatedat(now);
            command.store();
            // 新命令已成为权威入口，旧 waiting 边界若晚发布会制造已经失效的审核按钮。
            supersedeWaiting(transaction, taskId, now);
            return resumeResponse(command);
        });
    }

    @Override
    public CancelWritingRunResponse cancel(
            String userId, String taskId, CancelWritingRunRequest request) {
        Map<String, Object> resourceIdentity = Map.of("taskId", taskId);
        Map<String, Object> normalizedBody = Map.of();
        String fingerprint = CommandIdempotency.requestFingerprint(
                "cancel", resourceIdentity, normalizedBody, json);
        String key = CommandIdempotency.envelopedKey(userId, request.getClientRequestId());
        return database.transactionResult(transaction -> {
            // 取消与恢复共享用户级幂等命名空间，必须在读取当前命令前先串行化。
            advisoryLock(transaction, userId, request.getClientRequestId());
            CancelWritingRunResponse replay = cancelReplay(
                    transaction,
                    userId,
                    taskId,
                    request.getClientRequestId(),
                    fingerprint);
            if (replay != null) return replay;
            TaskIdentity identity = taskIdentity(transaction, userId, taskId);
            WritingtaskRecord task = lockTask(
                    transaction, userId, identity.novelId(), identity.chapterId(), taskId);
            ReviewartifactRecord awaitingArtifact = transaction.selectFrom(REVIEWARTIFACT)
                    .where(
                            REVIEWARTIFACT.TASKID.eq(taskId),
                            REVIEWARTIFACT.STATUS.eq(
                                    cn.inkforge.core.db.generated.enums.Reviewartifactstatus.awaiting_user))
                    .orderBy(REVIEWARTIFACT.CREATEDAT.desc(), REVIEWARTIFACT.ID.desc())
                    .limit(1)
                    .forUpdate()
                    .fetchOne();
            WritingruncommandRecord current = currentCommand(transaction, taskId, true);
            replay = cancelReplay(
                    transaction,
                    userId,
                    taskId,
                    request.getClientRequestId(),
                    fingerprint);
            if (replay != null) return replay;
            if (awaitingArtifact != null) {
                throw new ApiException(
                        409,
                        "ARTIFACT_DECISION_REQUIRED",
                        "存在等待用户决策的审核产物，必须先提交审核决策");
            }
            List<WritingruncommandRecord> commands = transaction.selectFrom(WRITINGRUNCOMMAND)
                    .where(WRITINGRUNCOMMAND.TASKID.eq(taskId))
                    .orderBy(WRITINGRUNCOMMAND.CREATEDAT.desc(), WRITINGRUNCOMMAND.ID.desc())
                    .fetch();
            List<ReviewartifactRecord> artifacts = transaction.selectFrom(REVIEWARTIFACT)
                    .where(REVIEWARTIFACT.TASKID.eq(taskId))
                    .orderBy(REVIEWARTIFACT.CREATEDAT.desc(), REVIEWARTIFACT.ID.desc())
                    .fetch();
            // 无效取消必须能恢复取消前公开结果，因此把当下权威投影冻结到取消命令结果中。
            Map<String, Object> priorOutcome = priorOutcome(task, commands, artifacts);
            boolean terminal = task.getPhase() == Writingtaskphase.completed
                    || task.getPhase() == Writingtaskphase.error;
            String cancelId = ids.next();
            String cancelledCommandId = null;
            String cancelledJobId = null;
            LocalDateTime now = DatabaseTimestamp.now(clock);
            if (!terminal && current != null) {
                cancelledCommandId = current.getId();
                cancelledJobId = current.getId();
                retireForCancel(transaction, current, cancelId, cancelledJobId, now);
            } else {
                terminal = true;
            }
            Map<String, Object> job = new LinkedHashMap<>();
            job.put("cancelledCommandId", cancelledCommandId);
            job.put("cancelledJobId", cancelledJobId);
            Map<String, Object> metadata = new LinkedHashMap<>();
            metadata.put("schemaVersion", 1);
            metadata.put("clientRequestId", request.getClientRequestId());
            metadata.put("commandKind", "cancel");
            metadata.put("resourceIdentity", resourceIdentity);
            metadata.put("normalizedBody", normalizedBody);
            metadata.put("requestFingerprint", fingerprint);
            Map<String, Object> payload = new LinkedHashMap<>();
            payload.put("_inkforgeCommand", metadata);
            payload.put("job", job);
            WritingruncommandRecord command = transaction.newRecord(WRITINGRUNCOMMAND);
            command.setId(cancelId);
            command.setTaskid(taskId);
            // 冻结数据库 kind 仍使用兼容值，逻辑 kind 只从版本化信封读取。
            command.setKind("resume");
            command.setPayloadjson(json.writeValueAsString(payload));
            if (terminal) {
                Map<String, Object> result = new LinkedHashMap<>();
                result.put("effective", false);
                result.put("priorOutcome", priorOutcome);
                command.setResultjson(json.writeValueAsString(result));
            }
            command.setIdempotencykey(key);
            command.setStatus(terminal ? "succeeded" : "pending");
            command.setAttemptcount(0);
            command.setNextattemptat(now);
            command.setCompletedat(terminal ? now : null);
            command.setCreatedat(now);
            command.setUpdatedat(now);
            command.store();
            return cancelResponse(
                    command,
                    !terminal,
                    terminal,
                    cancelledCommandId,
                    cancelledJobId);
        });
    }

    private WritingRunResponse startLegacy(String userId, StartWritingRunRequest request) {
        String key = CommandIdempotency.legacyKey(userId, request.getClientRequestId());
        return database.transactionResult(transaction -> {
            // legacy key 是已发布兼容面；只能保留原规则，不能改用新版 envelope 后重新解释旧请求。
            advisoryLock(transaction, userId, request.getClientRequestId());
            WritingRunResponse replay = legacyReplay(transaction, key);
            if (replay != null) return replay;
            requireOwnedChapter(
                    transaction, userId, request.getNovelId(), request.getChapterId(), true);
            Storylengthprofile profile = storyProfile(transaction, request.getNovelId(), true);
            String sessionId = nullable(request.getWritingSessionId());
            if (sessionId != null) {
                requireSession(
                        transaction,
                        userId,
                        sessionId,
                        request.getNovelId(),
                        request.getChapterId());
            }
            replay = legacyReplay(transaction, key);
            if (replay != null) return replay;

            Map<String, Object> payload = new LinkedHashMap<>();
            payload.put("version", 1);
            payload.put("resume", false);
            payload.put("chapterId", request.getChapterId());
            payload.put("writingSessionId", sessionId);
            payload.put("resumeInput", null);
            if (profile == Storylengthprofile.long_serial) {
                requireNoActiveLongMutation(transaction, request.getChapterId());
                payload.put(
                        "sourceBindings",
                        sourceBindings.capture(
                                transaction, request.getNovelId(), request.getChapterId()));
            }
            List<String> agents = request.getSelectedAgents().stream()
                    .map(StartWritingRunRequest.SelectedAgentsEnum::getValue)
                    .toList();
            List<Map<String, Object>> conversation =
                    List.of(Map.of("role", "user", "content", request.getUserMessage()));
            Created created = insertTaskAndCommand(
                    transaction,
                    request.getNovelId(),
                    request.getChapterId(),
                    sessionId,
                    request.getTargetWordCount(),
                    agents,
                    conversation,
                    null,
                    "start",
                    key,
                    payload);
            if (sessionId != null) {
                insertMessage(
                        transaction,
                        sessionId,
                        created.task().getId(),
                        request.getUserMessage(),
                        null);
            }
            return response(created.task(), created.command());
        });
    }

    private WritingRunResponse startLongSerial(
            String userId, LongSerialStartWritingRunRequest request) {
        LongSerialRunAssembler.Normalized normalized = longSerial.normalize(request);
        String key = CommandIdempotency.envelopedKey(userId, request.getClientRequestId());
        return database.transactionResult(transaction -> {
            // 来源冻结、任务、首命令和首条用户消息必须同成同败，Agent 只能看见提交后的完整 job。
            advisoryLock(transaction, userId, request.getClientRequestId());
            WritingRunResponse replay = explicitReplay(
                    transaction,
                    userId,
                    request.getClientRequestId(),
                    normalized.fingerprint());
            if (replay != null) return replay;
            requireOwnedChapter(
                    transaction, userId, request.getNovelId(), request.getChapterId(), true);
            if (storyProfile(transaction, request.getNovelId(), true)
                    != Storylengthprofile.long_serial) {
                throw new ApiException(
                        409,
                        "LONG_WORKFLOW_MISMATCH",
                        "目标小说不是长篇作品",
                        Map.of("novelId", request.getNovelId()));
            }
            String sessionId = nullable(request.getWritingSessionId());
            if (sessionId != null) {
                requireSession(
                        transaction,
                        userId,
                        sessionId,
                        request.getNovelId(),
                        request.getChapterId());
            }
            replay = explicitReplay(
                    transaction,
                    userId,
                    request.getClientRequestId(),
                    normalized.fingerprint());
            if (replay != null) return replay;
            if (normalized.definition().mutating()) {
                requireNoActiveLongMutation(transaction, request.getChapterId());
            }
            LongSerialRunAssembler.Assembled assembled = longSerial.assemble(
                    transaction, userId, request, normalized.definition());
            LocalDateTime now = DatabaseTimestamp.now(clock);
            String taskId = ids.next();
            Map<String, Object> graph = new LinkedHashMap<>(assembled.job());
            graph.put("taskId", taskId);
            graph.put("userId", userId);
            graph.put("novelId", request.getNovelId());
            graph.put("chapterId", request.getChapterId());
            graph.put("targetWordCount", assembled.targetWordCount());
            graph.put("conversationHistory", assembled.conversation());
            graph.put("eventSequence", 0);
            graph.put("phase", "active");
            Map<String, Object> envelope = new LinkedHashMap<>();
            Map<String, Object> metadata = new LinkedHashMap<>();
            metadata.put("schemaVersion", 1);
            metadata.put("clientRequestId", request.getClientRequestId());
            metadata.put("commandKind", "start");
            metadata.put("resourceIdentity", normalized.resourceIdentity());
            metadata.put("normalizedBody", normalized.body());
            metadata.put("requestFingerprint", normalized.fingerprint());
            envelope.put("_inkforgeCommand", metadata);
            envelope.put("job", assembled.job());
            Created created = insertTaskAndCommand(
                    transaction,
                    taskId,
                    request.getNovelId(),
                    request.getChapterId(),
                    sessionId,
                    assembled.targetWordCount(),
                    assembled.selectedAgents(),
                    assembled.conversation(),
                    graph,
                    "start",
                    key,
                    envelope,
                    now);
            if (sessionId != null) {
                insertMessage(
                        transaction,
                        sessionId,
                        taskId,
                        request.getUserInstruction(),
                        assembled.selectionAttachmentMetadata());
            }
            return response(created.task(), created.command());
        });
    }

    private WritingRunResponse startShortMedium(
            String userId, ShortMediumStartWritingRunRequest request) {
        String key = CommandIdempotency.legacyKey(userId, request.getClientRequestId());
        // Python 基线允许先快速命中已提交结果；真正创建仍在第二个完整事务内复核并锁定工作稿。
        WritingRunResponse outsideReplay = database.transactionResult(transaction ->
                legacyReplay(transaction, key));
        if (outsideReplay != null) return outsideReplay;
        return database.transactionResult(transaction -> {
            WritingRunResponse replay = legacyReplay(transaction, key);
            if (replay != null) return replay;
            ShortMediumRunAssembler.Assembled assembled =
                    shortMedium.assemble(transaction, userId, request);
            requireNoActiveShortDocumentRun(transaction, userId, request.getNovelId());
            List<Map<String, Object>> conversation = List.of(Map.of(
                    "role", "user", "content", assembled.visibleMessage()));
            Map<String, Object> graph = new LinkedHashMap<>(assembled.payload());
            graph.put("eventSequence", 0);
            graph.put("phase", "active");
            Created created = insertTaskAndCommand(
                    transaction,
                    request.getNovelId(),
                    assembled.chapterId(),
                    null,
                    assembled.targetTotalWordCount(),
                    List.of(assembled.selectedAgent()),
                    conversation,
                    graph,
                    "start",
                    key,
                    assembled.payload());
            return response(created.task(), created.command());
        });
    }

    private Created insertTaskAndCommand(
            DSLContext transaction,
            String novelId,
            String chapterId,
            String sessionId,
            int targetWordCount,
            List<String> agents,
            List<Map<String, Object>> conversation,
            Map<String, Object> graph,
            String commandKind,
            String key,
            Map<String, Object> payload) {
        return insertTaskAndCommand(
                transaction,
                ids.next(),
                novelId,
                chapterId,
                sessionId,
                targetWordCount,
                agents,
                conversation,
                graph,
                commandKind,
                key,
                payload,
                DatabaseTimestamp.now(clock));
    }

    private Created insertTaskAndCommand(
            DSLContext transaction,
            String taskId,
            String novelId,
            String chapterId,
            String sessionId,
            int targetWordCount,
            List<String> agents,
            List<Map<String, Object>> conversation,
            Map<String, Object> graph,
            String commandKind,
            String key,
            Map<String, Object> payload,
            LocalDateTime now) {
        WritingtaskRecord task = transaction.newRecord(WRITINGTASK);
        task.setId(taskId);
        task.setNovelid(novelId);
        task.setChapterid(chapterId);
        task.setTargetwordcount(targetWordCount);
        task.setSelectedagents(String.join(",", agents));
        task.setPhase(Writingtaskphase.idle);
        task.setConversationhistory(json.writeValueAsString(conversation));
        task.setGraphstatejson(graph == null ? null : json.writeValueAsString(graph));
        task.setWritingsessionid(sessionId);
        task.setCreatedat(now);
        task.setUpdatedat(now);
        task.store();
        WritingruncommandRecord command = transaction.newRecord(WRITINGRUNCOMMAND);
        command.setId(ids.next());
        command.setTaskid(taskId);
        command.setKind(commandKind);
        command.setPayloadjson(json.writeValueAsString(payload));
        command.setIdempotencykey(key);
        command.setStatus("pending");
        command.setAttemptcount(0);
        command.setNextattemptat(now);
        command.setCreatedat(now);
        command.setUpdatedat(now);
        command.store();
        return new Created(task, command);
    }

    private void insertMessage(
            DSLContext transaction,
            String sessionId,
            String taskId,
            String content,
            Map<String, Object> selectionAttachment) {
        LocalDateTime now = DatabaseTimestamp.now(clock);
        String metadata = WorkflowMessageMetadata.serialize(
                taskId,
                "user",
                content,
                null,
                selectionAttachment == null ? "workflow" : selectionAttachment,
                json);
        transaction.insertInto(WRITINGMESSAGE)
                .set(WRITINGMESSAGE.ID, ids.next())
                .set(WRITINGMESSAGE.SESSIONID, sessionId)
                .set(WRITINGMESSAGE.ROLE, "user")
                .set(WRITINGMESSAGE.CONTENT, content)
                .set(WRITINGMESSAGE.METADATA, metadata)
                .set(WRITINGMESSAGE.CREATEDAT, now)
                .execute();
        transaction.update(WRITINGSESSION)
                .set(WRITINGSESSION.UPDATEDAT, now)
                .where(WRITINGSESSION.ID.eq(sessionId))
                .execute();
    }

    private WritingRunResponse legacyReplay(DSLContext transaction, String key) {
        Record row = transaction.select(WRITINGRUNCOMMAND.fields())
                .select(WRITINGTASK.fields())
                .from(WRITINGRUNCOMMAND)
                .join(WRITINGTASK)
                .on(WRITINGTASK.ID.eq(WRITINGRUNCOMMAND.TASKID))
                .where(WRITINGRUNCOMMAND.IDEMPOTENCYKEY.eq(key))
                .fetchOne();
        if (row == null) return null;
        return response(
                row.into(WRITINGTASK).into(WritingtaskRecord.class),
                row.into(WRITINGRUNCOMMAND).into(WritingruncommandRecord.class));
    }

    private WritingRunResponse explicitReplay(
            DSLContext transaction,
            String userId,
            String clientRequestId,
            String fingerprint) {
        CommandIdempotencyStore.Resolution resolution = idempotency.resolve(
                transaction, userId, clientRequestId, fingerprint);
        if (resolution == null) return null;
        if (resolution.recordKind() != CommandIdempotencyStore.RecordKind.WRITING_COMMAND) {
            throw CommandIdempotencyStore.reused(clientRequestId);
        }
        Record row = transaction.select(WRITINGRUNCOMMAND.fields())
                .select(WRITINGTASK.fields())
                .select(NOVEL.USERID)
                .from(WRITINGRUNCOMMAND)
                .join(WRITINGTASK)
                .on(WRITINGTASK.ID.eq(WRITINGRUNCOMMAND.TASKID))
                .join(NOVEL)
                .on(NOVEL.ID.eq(WRITINGTASK.NOVELID))
                .where(WRITINGRUNCOMMAND.ID.eq(resolution.recordId()))
                .fetchOne();
        if (row == null) throw CommandIdempotencyStore.reused(clientRequestId);
        WritingruncommandRecord command =
                row.into(WRITINGRUNCOMMAND).into(WritingruncommandRecord.class);
        WritingtaskRecord task = row.into(WRITINGTASK).into(WritingtaskRecord.class);
        Map<String, Object> payload = object(command.getPayloadjson());
        Object job = payload.get("job");
        if (!userId.equals(row.get(NOVEL.USERID))
                || !"start".equals(command.getKind())
                || !(job instanceof Map<?, ?> map)
                || !"long_serial".equals(map.get("workflow"))) {
            throw CommandIdempotencyStore.reused(clientRequestId);
        }
        return response(task, command);
    }

    private ResumeWritingRunResponse resumeReplay(
            DSLContext transaction,
            String userId,
            String taskId,
            String clientRequestId,
            String fingerprint) {
        CommandIdempotencyStore.Resolution resolution = idempotency.resolve(
                transaction, userId, clientRequestId, fingerprint);
        if (resolution == null) return null;
        if (resolution.recordKind() != CommandIdempotencyStore.RecordKind.WRITING_COMMAND) {
            throw CommandIdempotencyStore.reused(clientRequestId);
        }
        Record row = transaction.select(WRITINGRUNCOMMAND.fields())
                .select(WRITINGTASK.fields())
                .select(NOVEL.USERID)
                .from(WRITINGRUNCOMMAND)
                .join(WRITINGTASK)
                .on(WRITINGTASK.ID.eq(WRITINGRUNCOMMAND.TASKID))
                .join(NOVEL)
                .on(NOVEL.ID.eq(WRITINGTASK.NOVELID))
                .where(WRITINGRUNCOMMAND.ID.eq(resolution.recordId()))
                .fetchOne();
        if (row == null) throw CommandIdempotencyStore.reused(clientRequestId);
        WritingruncommandRecord command =
                row.into(WRITINGRUNCOMMAND).into(WritingruncommandRecord.class);
        Map<String, Object> payload = object(command.getPayloadjson());
        Object job = payload.get("job");
        if (!userId.equals(row.get(NOVEL.USERID))
                || !taskId.equals(command.getTaskid())
                || !"resume".equals(command.getKind())
                || !payload.keySet().equals(Set.of("_inkforgeCommand", "job"))
                || !(job instanceof Map<?, ?> map)
                || !Boolean.TRUE.equals(map.get("resume"))) {
            throw CommandIdempotencyStore.reused(clientRequestId);
        }
        return resumeResponse(command);
    }

    private CancelWritingRunResponse cancelReplay(
            DSLContext transaction,
            String userId,
            String taskId,
            String clientRequestId,
            String fingerprint) {
        CommandIdempotencyStore.Resolution resolution = idempotency.resolve(
                transaction, userId, clientRequestId, fingerprint);
        if (resolution == null) return null;
        if (resolution.recordKind() != CommandIdempotencyStore.RecordKind.WRITING_COMMAND
                || !"cancel".equals(resolution.metadata().commandKind())) {
            throw CommandIdempotencyStore.reused(clientRequestId);
        }
        Record row = transaction.select(WRITINGRUNCOMMAND.fields())
                .select(NOVEL.USERID)
                .from(WRITINGRUNCOMMAND)
                .join(WRITINGTASK)
                .on(WRITINGTASK.ID.eq(WRITINGRUNCOMMAND.TASKID))
                .join(NOVEL)
                .on(NOVEL.ID.eq(WRITINGTASK.NOVELID))
                .where(WRITINGRUNCOMMAND.ID.eq(resolution.recordId()))
                .fetchOne();
        if (row == null) throw CommandIdempotencyStore.reused(clientRequestId);
        WritingruncommandRecord command =
                row.into(WRITINGRUNCOMMAND).into(WritingruncommandRecord.class);
        Map<String, Object> payload;
        try {
            payload = object(command.getPayloadjson());
        } catch (RuntimeException exception) {
            throw CommandIdempotencyStore.reused(clientRequestId);
        }
        Object jobValue = payload.get("job");
        if (!userId.equals(row.get(NOVEL.USERID))
                || !taskId.equals(command.getTaskid())
                || !payload.keySet().equals(Set.of("_inkforgeCommand", "job"))
                || !(jobValue instanceof Map<?, ?> rawJob)) {
            throw CommandIdempotencyStore.reused(clientRequestId);
        }
        Map<String, Object> job = stringMap(rawJob);
        if (job == null
                || !job.keySet().equals(Set.of("cancelledCommandId", "cancelledJobId"))
                || !nullableString(job.get("cancelledCommandId"))
                || !nullableString(job.get("cancelledJobId"))) {
            throw CommandIdempotencyStore.reused(clientRequestId);
        }
        Map<String, Object> result = objectOrEmpty(command.getResultjson());
        Object effective = result.get("effective");
        return cancelResponse(
                command,
                Boolean.TRUE.equals(effective) || !"succeeded".equals(command.getStatus()),
                Boolean.FALSE.equals(effective),
                (String) job.get("cancelledCommandId"),
                (String) job.get("cancelledJobId"));
    }

    private Map<String, Object> priorOutcome(
            WritingtaskRecord task,
            List<WritingruncommandRecord> commands,
            List<ReviewartifactRecord> artifacts) {
        // 只保存取消恢复所需的最小耐久投影，避免把瞬时 SSE 或完整正文复制进控制命令。
        var outcome = statusProjector.project(task, commands, artifacts).getOutcome();
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("kind", outcome.getResult().getKind().getValue());
        result.put("ready", outcome.getResult().getReady());
        result.put("id", outcome.getResult().getId());
        Map<String, Object> current = null;
        if (outcome.getCurrentCommand() != null) {
            current = new LinkedHashMap<>();
            current.put("id", outcome.getCurrentCommand().getId());
            current.put("kind", outcome.getCurrentCommand().getKind());
            current.put("status", outcome.getCurrentCommand().getStatus().getValue());
            current.put("updatedAt", outcome.getCurrentCommand().getUpdatedAt());
        }
        Map<String, Object> projected = new LinkedHashMap<>();
        projected.put("state", outcome.getState().getValue());
        projected.put("code", outcome.getCode());
        projected.put("result", result);
        projected.put("currentCommand", current);
        return projected;
    }

    private void retireForCancel(
            DSLContext transaction,
            WritingruncommandRecord command,
            String cancelCommandId,
            String cancelledJobId,
            LocalDateTime now) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("code", "WRITING_RUN_CANCELLED_BY_USER");
        result.put("cancelCommandId", cancelCommandId);
        result.put("cancelledJobId", cancelledJobId);
        if ("artifact_decision".equals(command.getKind())) {
            Map<String, Object> persisted = objectOrEmpty(command.getResultjson());
            Object accepted = persisted.get("_inkforgeArtifactDecisionAcceptedResponse");
            if (!(accepted instanceof Map<?, ?>)) accepted = persisted;
            if (accepted instanceof Map<?, ?> map && !map.isEmpty()) {
                result.put("_inkforgeArtifactDecisionAcceptedResponse", accepted);
            }
        }
        transaction.update(WRITINGRUNCOMMAND)
                .set(WRITINGRUNCOMMAND.STATUS, "failed")
                .set(WRITINGRUNCOMMAND.RESULTJSON, json.writeValueAsString(result))
                .set(WRITINGRUNCOMMAND.LASTERROR, "WRITING_RUN_CANCELLED_BY_USER")
                .set(WRITINGRUNCOMMAND.COMPLETEDAT, now)
                .set(WRITINGRUNCOMMAND.UPDATEDAT, now)
                .where(WRITINGRUNCOMMAND.ID.eq(command.getId()))
                .execute();
        command.setStatus("failed");
        command.setResultjson(json.writeValueAsString(result));
        command.setLasterror("WRITING_RUN_CANCELLED_BY_USER");
        command.setCompletedat(now);
        command.setUpdatedat(now);
    }

    private static CancelWritingRunResponse cancelResponse(
            WritingruncommandRecord command,
            boolean effective,
            boolean alreadyTerminal,
            String cancelledCommandId,
            String cancelledJobId) {
        return new CancelWritingRunResponse(
                alreadyTerminal,
                cancelledCommandId,
                cancelledJobId,
                command.getId(),
                CancelWritingRunResponse.CommandStatusEnum.fromValue(command.getStatus()),
                effective,
                1,
                command.getTaskid(),
                command.getTaskid());
    }

    private static boolean nullableString(Object value) {
        return value == null || value instanceof String;
    }

    private Map<String, Object> resumeJob(
            DSLContext transaction,
            WritingtaskRecord task,
            Map<String, Object> resumeInput) {
        // 恢复必须从最初冻结 job 派生；重新读取当前章节或工作区会让同一任务在重试时改变输入。
        String startPayload = transaction.select(WRITINGRUNCOMMAND.PAYLOADJSON)
                .from(WRITINGRUNCOMMAND)
                .where(
                        WRITINGRUNCOMMAND.TASKID.eq(task.getId()),
                        WRITINGRUNCOMMAND.KIND.eq("start"))
                .orderBy(WRITINGRUNCOMMAND.CREATEDAT.asc(), WRITINGRUNCOMMAND.ID.asc())
                .limit(1)
                .fetchOne(WRITINGRUNCOMMAND.PAYLOADJSON);
        if (startPayload != null) {
            Map<String, Object> payload = object(startPayload);
            Object metadataValue = payload.get("_inkforgeCommand");
            Object jobValue = payload.get("job");
            boolean declaresLong = metadataValue instanceof Map<?, ?> metadata
                            && metadata.get("normalizedBody") instanceof Map<?, ?> body
                            && "long_serial".equals(body.get("workflow"))
                    || jobValue instanceof Map<?, ?> job
                            && "long_serial".equals(job.get("workflow"));
            if (declaresLong) {
                if (!(metadataValue instanceof Map<?, ?> metadata)
                        || !"start".equals(metadata.get("commandKind"))
                        || !payload.keySet().equals(Set.of("_inkforgeCommand", "job"))
                        || !(jobValue instanceof Map<?, ?> rawJob)) {
                    throw new IllegalStateException("显式长篇启动命令缺少权威 job");
                }
                Map<String, Object> job = stringMap(rawJob);
                if (job == null
                        || !Integer.valueOf(1).equals(job.get("version"))
                        || !"long_serial".equals(job.get("workflow"))
                        || !Objects.equals(job.get("chapterId"), task.getChapterid())
                        || !Objects.equals(job.get("writingSessionId"), task.getWritingsessionid())
                        || !Boolean.FALSE.equals(job.get("resume"))
                        || job.get("resumeInput") != null
                        || !(job.get("target") instanceof Map<?, ?> target)
                        || !Objects.equals(target.get("id"), task.getChapterid())) {
                    throw new IllegalStateException("显式长篇启动命令与任务身份不一致");
                }
                Map<String, Object> resumed = deepCopy(job);
                resumed.put("resume", true);
                resumed.put("resumeInput", new LinkedHashMap<>(resumeInput));
                return Collections.unmodifiableMap(resumed);
            }
        }
        // 只有没有版本化长篇 envelope 的历史任务才回退到旧 resume 形状。
        Map<String, Object> legacy = new LinkedHashMap<>();
        legacy.put("version", 1);
        legacy.put("resume", true);
        legacy.put("chapterId", task.getChapterid());
        legacy.put("writingSessionId", task.getWritingsessionid());
        legacy.put("resumeInput", new LinkedHashMap<>(resumeInput));
        return Collections.unmodifiableMap(legacy);
    }

    private TaskIdentity taskIdentity(
            DSLContext transaction, String userId, String taskId) {
        Record2<String, String> row = transaction
                .select(WRITINGTASK.NOVELID, WRITINGTASK.CHAPTERID)
                .from(WRITINGTASK)
                .join(NOVEL)
                .on(NOVEL.ID.eq(WRITINGTASK.NOVELID))
                .where(WRITINGTASK.ID.eq(taskId), NOVEL.USERID.eq(userId))
                .fetchOne();
        if (row == null) {
            throw new ApiException(404, "WRITING_TASK_NOT_FOUND", "写作任务不存在");
        }
        return new TaskIdentity(row.value1(), row.value2());
    }

    private WritingtaskRecord lockTask(
            DSLContext transaction,
            String userId,
            String novelId,
            String chapterId,
            String taskId) {
        String novel = transaction.select(NOVEL.ID)
                .from(NOVEL)
                .where(NOVEL.ID.eq(novelId), NOVEL.USERID.eq(userId))
                .forUpdate()
                .fetchOne(NOVEL.ID);
        if (novel == null) {
            throw new ApiException(404, "NOVEL_NOT_FOUND", "小说不存在");
        }
        if (chapterId != null) {
            String chapter = transaction.select(CHAPTER.ID)
                    .from(CHAPTER)
                    .where(CHAPTER.ID.eq(chapterId), CHAPTER.NOVELID.eq(novelId))
                    .forUpdate()
                    .fetchOne(CHAPTER.ID);
            if (chapter == null) {
                throw new ApiException(404, "CHAPTER_NOT_FOUND", "章节不存在或不属于该小说");
            }
        }
        WritingtaskRecord task = transaction.selectFrom(WRITINGTASK)
                .where(WRITINGTASK.ID.eq(taskId), WRITINGTASK.NOVELID.eq(novelId))
                .forUpdate()
                .fetchOne();
        if (task == null
                || (chapterId != null && !chapterId.equals(task.getChapterid()))) {
            throw new ApiException(404, "WRITING_TASK_NOT_FOUND", "写作任务不存在");
        }
        return task;
    }

    private WritingruncommandRecord currentCommand(
            DSLContext transaction, String taskId, boolean lock) {
        var query = transaction.selectFrom(WRITINGRUNCOMMAND)
                .where(WRITINGRUNCOMMAND.TASKID.eq(taskId))
                .orderBy(WRITINGRUNCOMMAND.CREATEDAT.desc(), WRITINGRUNCOMMAND.ID.desc())
                .limit(1);
        return lock ? query.forUpdate().fetchOne() : query.fetchOne();
    }

    private static void requireNoActiveCommand(DSLContext transaction, String taskId) {
        String commandId = transaction.select(WRITINGRUNCOMMAND.ID)
                .from(WRITINGRUNCOMMAND)
                .where(
                        WRITINGRUNCOMMAND.TASKID.eq(taskId),
                        WRITINGRUNCOMMAND.STATUS.in(ACTIVE_COMMANDS))
                .fetchAny(WRITINGRUNCOMMAND.ID);
        if (commandId != null) {
            throw new ApiException(
                    409,
                    "WRITING_COMMAND_ACTIVE",
                    "该写作任务已有正在处理的命令",
                    Map.of("taskId", taskId));
        }
    }

    private static void supersedeWaiting(
            DSLContext transaction, String taskId, LocalDateTime now) {
        transaction.update(WRITINGEVENTOUTBOX)
                .set(WRITINGEVENTOUTBOX.DELIVERYSTATE, "superseded")
                .set(WRITINGEVENTOUTBOX.LASTERRORCODE, "OUTBOX_WAITING_SUPERSEDED")
                .setNull(WRITINGEVENTOUTBOX.LEASETOKEN)
                .setNull(WRITINGEVENTOUTBOX.LEASEEXPIRESAT)
                .set(WRITINGEVENTOUTBOX.UPDATEDAT, now)
                .where(
                        WRITINGEVENTOUTBOX.TASKID.eq(taskId),
                        WRITINGEVENTOUTBOX.EVENTTYPE.eq("artifact_awaiting_user_approval"),
                        WRITINGEVENTOUTBOX.DELIVERYSTATE.in("pending", "delivering", "blocked"))
                .execute();
    }

    private static ResumeWritingRunResponse resumeResponse(
            WritingruncommandRecord command) {
        return new ResumeWritingRunResponse(
                true,
                command.getId(),
                ResumeWritingRunResponse.CommandStatusEnum.fromValue(command.getStatus()),
                1,
                command.getTaskid(),
                command.getTaskid());
    }

    private Map<String, Object> deepCopy(Map<String, Object> value) {
        return json.convertValue(value, new TypeReference<>() {});
    }

    private static Map<String, Object> stringMap(Map<?, ?> value) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : value.entrySet()) {
            if (!(entry.getKey() instanceof String key)) return null;
            result.put(key, entry.getValue());
        }
        return result;
    }

    private void requireNoActiveShortDocumentRun(
            DSLContext transaction, String userId, String novelId) {
        List<String> payloads = transaction.select(WRITINGRUNCOMMAND.PAYLOADJSON)
                .from(WRITINGRUNCOMMAND)
                .join(WRITINGTASK)
                .on(WRITINGTASK.ID.eq(WRITINGRUNCOMMAND.TASKID))
                .join(NOVEL)
                .on(NOVEL.ID.eq(WRITINGTASK.NOVELID))
                .where(
                        NOVEL.USERID.eq(userId),
                        WRITINGTASK.NOVELID.eq(novelId),
                        WRITINGRUNCOMMAND.STATUS.in(ACTIVE_COMMANDS))
                .forUpdate()
                .of(WRITINGRUNCOMMAND)
                .fetch(WRITINGRUNCOMMAND.PAYLOADJSON);
        for (String serialized : payloads) {
            Map<String, Object> payload = objectOrEmpty(serialized);
            Object operation = payload.get("operation");
            if ("short_medium".equals(payload.get("workflow"))
                    && operation instanceof String
                    && Set.of("generate_outline", "generate_manuscript", "replace_selection")
                            .contains(operation)) {
                throw new ApiException(
                        409,
                        "SHORT_MEDIUM_DOCUMENT_RUN_ACTIVE",
                        "该中短篇作品已有文档任务正在处理");
            }
        }
    }

    private void requireNoActiveLongMutation(DSLContext transaction, String chapterId) {
        // 只读 review_chapter 可并存；未知或损坏的旧 payload 按写任务处理，采用保守失败语义。
        List<Record2<String, String>> rows = transaction
                .select(WRITINGTASK.ID, WRITINGRUNCOMMAND.PAYLOADJSON)
                .from(WRITINGTASK)
                .leftJoin(WRITINGRUNCOMMAND)
                .on(
                        WRITINGRUNCOMMAND.TASKID.eq(WRITINGTASK.ID),
                        WRITINGRUNCOMMAND.KIND.eq("start"))
                .where(
                        WRITINGTASK.CHAPTERID.eq(chapterId),
                        WRITINGTASK.PHASE.notIn(Writingtaskphase.completed, Writingtaskphase.error))
                .orderBy(WRITINGTASK.CREATEDAT.asc(), WRITINGTASK.ID.asc())
                .forUpdate()
                .of(WRITINGTASK)
                .fetch();
        Set<String> seen = new java.util.HashSet<>();
        for (Record2<String, String> row : rows) {
            if (!seen.add(row.value1())) continue;
            if (startPayloadMutating(row.value2())) {
                throw new ApiException(
                        409,
                        "WRITING_TARGET_BUSY",
                        "该章节已有正在进行的写入任务",
                        Map.of("taskId", row.value1()));
            }
        }
    }

    private boolean startPayloadMutating(String serialized) {
        if (serialized == null) return true;
        Map<String, Object> payload = objectOrEmpty(serialized);
        Object metadata = payload.get("_inkforgeCommand");
        if (!(metadata instanceof Map<?, ?> map)
                || !"start".equals(map.get("commandKind"))) {
            return true;
        }
        Object job = payload.get("job");
        if (!(job instanceof Map<?, ?> value)
                || !"long_serial".equals(value.get("workflow"))
                || !(value.get("operation") instanceof String operation)) {
            return true;
        }
        return !"review_chapter".equals(operation);
    }

    private static void requireOwnedChapter(
            DSLContext transaction,
            String userId,
            String novelId,
            String chapterId,
            boolean lock) {
        var novelQuery = transaction.select(NOVEL.ID)
                .from(NOVEL)
                .where(NOVEL.ID.eq(novelId), NOVEL.USERID.eq(userId));
        String ownedNovel = lock
                ? novelQuery.forUpdate().fetchOne(NOVEL.ID)
                : novelQuery.fetchOne(NOVEL.ID);
        if (ownedNovel == null) {
            throw new ApiException(404, "CHAPTER_NOT_FOUND", "章节不存在或不属于该小说");
        }
        var chapterQuery = transaction.select(CHAPTER.ID)
                .from(CHAPTER)
                .where(CHAPTER.ID.eq(chapterId), CHAPTER.NOVELID.eq(novelId));
        String found = lock
                ? chapterQuery.forUpdate().fetchOne(CHAPTER.ID)
                : chapterQuery.fetchOne(CHAPTER.ID);
        if (found == null) {
            throw new ApiException(404, "CHAPTER_NOT_FOUND", "章节不存在或不属于该小说");
        }
    }

    private static Storylengthprofile storyProfile(
            DSLContext transaction, String novelId, boolean lock) {
        var query = transaction.select(WRITINGBIBLE.STORYLENGTHPROFILE)
                .from(WRITINGBIBLE)
                .where(WRITINGBIBLE.NOVELID.eq(novelId));
        return lock
                ? query.forUpdate().fetchOne(WRITINGBIBLE.STORYLENGTHPROFILE)
                : query.fetchOne(WRITINGBIBLE.STORYLENGTHPROFILE);
    }

    private static void requireSession(
            DSLContext transaction,
            String userId,
            String sessionId,
            String novelId,
            String chapterId) {
        String found = transaction.select(WRITINGSESSION.ID)
                .from(WRITINGSESSION)
                .join(NOVEL)
                .on(NOVEL.ID.eq(WRITINGSESSION.NOVELID))
                .where(
                        WRITINGSESSION.ID.eq(sessionId),
                        WRITINGSESSION.NOVELID.eq(novelId),
                        WRITINGSESSION.CHAPTERID.eq(chapterId),
                        NOVEL.USERID.eq(userId))
                .fetchOne(WRITINGSESSION.ID);
        if (found == null) {
            throw new ApiException(
                    409, "WRITING_SESSION_MISMATCH", "写作会话与当前小说或章节不匹配");
        }
    }

    private void advisoryLock(DSLContext transaction, String userId, String requestId) {
        transaction.fetch(
                "SELECT pg_advisory_xact_lock(?)",
                CommandIdempotency.advisoryLockKey(userId, requestId));
    }

    private WritingRunResponse response(
            WritingtaskRecord task, WritingruncommandRecord command) {
        WritingRunResponse result = new WritingRunResponse();
        result.setId(task.getId());
        result.setEngineVersion(1);
        result.setRunId(task.getId());
        result.setTaskId(task.getId());
        result.setNovelId(task.getNovelid());
        result.setChapterId(task.getChapterid());
        result.setWritingSessionId(task.getWritingsessionid());
        result.setPhase(task.getPhase().getLiteral());
        result.setTargetWordCount(task.getTargetwordcount());
        result.setSelectedAgents(task.getSelectedagents() == null
                ? List.of()
                : java.util.Arrays.stream(task.getSelectedagents().split(","))
                        .filter(value -> !value.isEmpty())
                        .toList());
        result.setCreatedAt(DatabaseTimestamp.api(task.getCreatedat()));
        result.setUpdatedAt(DatabaseTimestamp.api(task.getUpdatedat()));
        result.setCommandId(command.getId());
        result.setCommandStatus(
                WritingRunResponse.CommandStatusEnum.fromValue(command.getStatus()));
        return result;
    }

    private Map<String, Object> object(String serialized) {
        try {
            Object parsed = json.readValue(serialized, new TypeReference<Object>() {});
            if (!(parsed instanceof Map<?, ?> map)) throw new IllegalStateException();
            Map<String, Object> result = new LinkedHashMap<>();
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                if (!(entry.getKey() instanceof String key)) throw new IllegalStateException();
                result.put(key, entry.getValue());
            }
            return result;
        } catch (RuntimeException exception) {
            throw new IllegalStateException("写作命令持久 JSON 无效");
        }
    }

    private Map<String, Object> objectOrEmpty(String serialized) {
        try {
            return object(serialized);
        } catch (RuntimeException exception) {
            return Map.of();
        }
    }

    private static <T> T nullable(JsonNullable<T> value) {
        return value != null && value.isPresent() ? value.orElse(null) : null;
    }

    private record Created(WritingtaskRecord task, WritingruncommandRecord command) {}

    private record TaskIdentity(String novelId, String chapterId) {}
}
