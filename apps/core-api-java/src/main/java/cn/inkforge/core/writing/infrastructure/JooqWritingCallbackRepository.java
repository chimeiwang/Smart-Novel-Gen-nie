package cn.inkforge.core.writing.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.OUTLINE;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACT;
import static cn.inkforge.core.db.generated.Tables.WRITINGMESSAGE;
import static cn.inkforge.core.db.generated.Tables.WRITINGRUNCOMMAND;
import static cn.inkforge.core.db.generated.Tables.WRITINGSESSION;
import static cn.inkforge.core.db.generated.Tables.WRITINGTASK;

import cn.inkforge.core.db.generated.enums.Writingtaskphase;
import cn.inkforge.core.db.generated.tables.records.WritingruncommandRecord;
import cn.inkforge.core.db.generated.tables.records.WritingtaskRecord;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.writing.application.WritingCallbackRepository;
import cn.inkforge.core.writing.application.WritingCommandPayload;
import cn.inkforge.core.writing.domain.WritingBoundaryEvent;
import cn.inkforge.core.writing.domain.WritingCallbackAcceptance;
import cn.inkforge.core.writing.domain.WritingGraphSnapshot;
import cn.inkforge.core.writing.domain.WritingMessageMetadata;
import cn.inkforge.core.writing.domain.WritingTaskFailure;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.jooq.DSLContext;
import org.jooq.Record;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/**
 * PostgreSQL 写作回调状态机。
 *
 * <p>每次事务统一按 Novel、Chapter/Outline、Session、Task、Artifact、Command、Outbox 顺序加锁，
 * 从而修复旧实现中完成回调先锁命令、再反向锁工作稿的潜在死锁。等待用户、完成和失败边界在同一事务
 * 登记 Outbox；Redis 发布发生在提交之后，发布失败不能回滚已经形成的任务、候选或终态事实。
 */
final class JooqWritingCallbackRepository implements WritingCallbackRepository {

    private static final Set<String> ACTIVE_COMMANDS =
            Set.of("pending", "submitted", "processing");
    private static final Set<Writingtaskphase> TERMINAL_TASKS =
            Set.of(Writingtaskphase.completed, Writingtaskphase.error);
    private static final String TERMINAL_CALLBACK_RESULT = "_inkforgeTerminalCallbackResult";

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final ObjectMapper json;
    private final WritingBoundaryOutboxRegistrar outbox;
    private final ShortMediumCompletionMaterializer shortMedium;

    JooqWritingCallbackRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock clock,
            ObjectMapper json) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
        this.outbox = new WritingBoundaryOutboxRegistrar(ids, clock, json);
        this.shortMedium = new ShortMediumCompletionMaterializer(ids, clock, json);
    }

    @Override
    public TaskResources resources(String taskId) {
        Record row = database.dsl().select(WRITINGTASK.NOVELID, NOVEL.USERID)
                .from(WRITINGTASK)
                .join(NOVEL)
                .on(NOVEL.ID.eq(WRITINGTASK.NOVELID))
                .where(WRITINGTASK.ID.eq(taskId))
                .fetchOne();
        if (row == null || row.get(NOVEL.USERID) == null) {
            throw new ApiException(
                    404, "WRITING_TASK_NOT_FOUND", "写作任务不存在或缺少归属");
        }
        return new TaskResources(row.get(WRITINGTASK.NOVELID), row.get(NOVEL.USERID));
    }

    @Override
    public WritingCallbackAcceptance authorize(String taskId, String jobId) {
        return database.transactionResult(transaction -> {
            Target target = lockTarget(transaction, taskId, jobId);
            if (target == null) return rejected(0, "WRITING_JOB_MISMATCH");
            return acceptance(
                    target,
                    true,
                    persistedSequence(target.task()),
                    target.alreadyApplied(),
                    null,
                    null);
        });
    }

    @Override
    public WritingCallbackAcceptance markProcessing(
            String taskId, String jobId, int sequence) {
        return database.transactionResult(transaction -> {
            Target target = lockTarget(transaction, taskId, jobId);
            if (target == null) return rejected(0, "WRITING_JOB_MISMATCH");
            int persisted = persistedSequence(target.task());
            if (sequence <= persisted) {
                return acceptance(
                        target,
                        false,
                        persisted,
                        false,
                        "WRITING_CALLBACK_SEQUENCE_STALE",
                        null);
            }
            if (target.alreadyApplied()) {
                return acceptance(
                        target,
                        false,
                        persisted,
                        false,
                        "WRITING_CALLBACK_ALREADY_APPLIED",
                        null);
            }
            transition(target.command(), "processing", null, null);
            if (target.command() != null) target.command().update();
            return acceptance(target, true, persisted, false, null, null);
        });
    }

    @Override
    public WritingCallbackAcceptance saveCheckpoint(
            String taskId,
            String jobId,
            String serialized,
            String phase,
            int sequence,
            WritingBoundaryEvent boundary) {
        return database.transactionResult(transaction -> {
            Target target = lockTarget(transaction, taskId, jobId);
            if (target == null) return rejected(0, "WRITING_JOB_MISMATCH");
            int persisted = persistedSequence(target.task());
            if (sequence < persisted) {
                return rejected(persisted, "WRITING_CALLBACK_SEQUENCE_STALE");
            }
            if (sequence == persisted) {
                // 相同序号只有完整快照和边界事实都一致时才可幂等；序号相同不代表内容相同。
                boolean identical = Objects.equals(target.task().getGraphstatejson(), serialized);
                WritingBoundaryOutboxRegistrar.Registration registration = identical
                        ? outbox.register(
                                transaction,
                                taskId,
                                target.command() == null ? null : target.command().getId(),
                                boundary,
                                null)
                        : new WritingBoundaryOutboxRegistrar.Registration(null, false);
                if (registration.conflict()) {
                    return acceptance(
                            target,
                            false,
                            persisted,
                            false,
                            "WRITING_OUTBOX_BOUNDARY_CONFLICT",
                            null);
                }
                return acceptance(
                        target,
                        identical,
                        persisted,
                        identical,
                        identical ? null : "WRITING_CHECKPOINT_CONFLICT",
                        registration.outboxId());
            }
            if (target.alreadyApplied() || TERMINAL_TASKS.contains(target.task().getPhase())) {
                return rejected(persisted, "WRITING_CALLBACK_ALREADY_APPLIED");
            }
            String persistedPhase = checkpointPhase(target, serialized, phase);
            // 先登记边界、再更新任务；二者位于同一事务，提交后 publisher 才允许触碰 Redis。
            WritingBoundaryOutboxRegistrar.Registration registration = outbox.register(
                    transaction,
                    taskId,
                    target.command() == null ? null : target.command().getId(),
                    boundary,
                    persisted);
            if (registration.conflict()) {
                return acceptance(
                        target,
                        false,
                        persisted,
                        false,
                        "WRITING_OUTBOX_BOUNDARY_CONFLICT",
                        null);
            }
            Writingtaskphase phaseValue = Writingtaskphase.lookupLiteral(persistedPhase);
            if (phaseValue == null) throw snapshotInvalid("写作任务快照阶段无效");
            target.task().setGraphstatejson(serialized);
            target.task().setPhase(phaseValue);
            target.task().setUpdatedat(DatabaseTimestamp.now(clock));
            transition(
                    target.command(),
                    phaseValue == Writingtaskphase.awaiting_user_review
                            ? "succeeded"
                            : "processing",
                    null,
                    null);
            target.task().update();
            if (target.command() != null) target.command().update();
            return acceptance(
                    target, true, persisted, false, null, registration.outboxId());
        });
    }

    @Override
    public WritingCallbackAcceptance complete(
            String taskId,
            String jobId,
            Map<String, Object> incoming,
            String visibleResponse,
            int sequence,
            WritingBoundaryEvent boundary) {
        Map<String, Object> callbackResult = new LinkedHashMap<>(incoming);
        return database.transactionResult(transaction -> {
            Target target = lockTarget(transaction, taskId, jobId);
            if (target == null) return rejected(0, "WRITING_JOB_MISMATCH");
            WritingtaskRecord task = target.task();
            int persisted = persistedSequence(task);
            if (sequence <= persisted) {
                return rejected(persisted, "WRITING_CALLBACK_SEQUENCE_STALE");
            }
            if (target.command() == null && TERMINAL_TASKS.contains(task.getPhase())) {
                if (task.getPhase() != Writingtaskphase.completed) {
                    return rejected(persisted, "WRITING_CALLBACK_STATE_NOOP");
                }
                if (!taskCompletionCompatible(task, incoming)) {
                    return acceptance(
                            target,
                            false,
                            persisted,
                            false,
                            "WRITING_CALLBACK_RESULT_CONFLICT",
                            null);
                }
                WritingBoundaryOutboxRegistrar.Registration registration = outbox.register(
                        transaction, taskId, null, boundary, persisted);
                if (registration.conflict()) return outboxConflict(target, persisted);
                applyCompletionFields(task, incoming, false);
                task.update();
                return acceptance(
                        target,
                        true,
                        persisted,
                        true,
                        null,
                        registration.outboxId());
            }
            if (target.alreadyApplied()) {
                boolean accepted = target.command() != null
                        && "succeeded".equals(target.command().getStatus());
                if (accepted && !completionCompatible(task, target.command(), incoming)) {
                    return acceptance(
                            target,
                            false,
                            persisted,
                            false,
                            "WRITING_CALLBACK_RESULT_CONFLICT",
                            null);
                }
                WritingBoundaryOutboxRegistrar.Registration registration = accepted
                        ? outbox.register(
                                transaction,
                                taskId,
                                target.command().getId(),
                                boundary,
                                persisted)
                        : new WritingBoundaryOutboxRegistrar.Registration(null, false);
                if (registration.conflict()) return outboxConflict(target, persisted);
                return acceptance(
                        target,
                        accepted,
                        persisted,
                        accepted,
                        accepted ? null : "WRITING_CALLBACK_STATE_NOOP",
                        registration.outboxId());
            }
            if (task.getPhase() == Writingtaskphase.error) {
                return rejected(persisted, "WRITING_CALLBACK_STATE_NOOP");
            }
            WritingBoundaryOutboxRegistrar.Registration registration = outbox.register(
                    transaction,
                    taskId,
                    target.command() == null ? null : target.command().getId(),
                    boundary,
                    persisted);
            if (registration.conflict()) return outboxConflict(target, persisted);
            // 中短篇候选/报告必须与任务、命令终态原子物化，禁止形成“完成但候选缺失”。
            Map<String, Object> persistedResult = incoming;
            if (target.command() != null && isShort(target.command())) {
                persistedResult = shortMedium.finalizeResult(
                        transaction, task, target.command(), incoming);
            }
            if (visibleResponse != null && !visibleResponse.isEmpty()) {
                persistMessage(transaction, task, "agent", visibleResponse, "done", null);
            }
            applyCompletionFields(task, incoming, true);
            transition(
                    target.command(), "succeeded", persistedResult, callbackResult);
            task.update();
            if (target.command() != null) target.command().update();
            return acceptance(
                    target, true, persisted, false, null, registration.outboxId());
        });
    }

    @Override
    public WritingCallbackAcceptance fail(
            String taskId,
            String jobId,
            String code,
            int sequence,
            WritingBoundaryEvent boundary) {
        return database.transactionResult(transaction -> {
            Target target = lockTarget(transaction, taskId, jobId);
            if (target == null) return rejected(0, "WRITING_JOB_MISMATCH");
            WritingtaskRecord task = target.task();
            int persisted = persistedSequence(task);
            if (sequence <= persisted) {
                return rejected(persisted, "WRITING_CALLBACK_SEQUENCE_STALE");
            }
            if (target.command() == null && TERMINAL_TASKS.contains(task.getPhase())) {
                boolean accepted = task.getPhase() == Writingtaskphase.error;
                if (accepted && !taskFailureCompatible(task, code)) {
                    return acceptance(
                            target,
                            false,
                            persisted,
                            false,
                            "WRITING_CALLBACK_RESULT_CONFLICT",
                            null);
                }
                WritingBoundaryOutboxRegistrar.Registration registration = accepted
                        ? outbox.register(transaction, taskId, null, boundary, persisted)
                        : new WritingBoundaryOutboxRegistrar.Registration(null, false);
                if (registration.conflict()) return outboxConflict(target, persisted);
                return acceptance(
                        target,
                        accepted,
                        persisted,
                        accepted,
                        accepted ? null : "WRITING_CALLBACK_STATE_NOOP",
                        registration.outboxId());
            }
            if (target.alreadyApplied()) {
                boolean accepted = target.command() != null
                        && "failed".equals(target.command().getStatus());
                if (accepted && !failureCompatible(task, target.command(), code)) {
                    return acceptance(
                            target,
                            false,
                            persisted,
                            false,
                            "WRITING_CALLBACK_RESULT_CONFLICT",
                            null);
                }
                WritingBoundaryOutboxRegistrar.Registration registration = accepted
                        ? outbox.register(
                                transaction,
                                taskId,
                                target.command().getId(),
                                boundary,
                                persisted)
                        : new WritingBoundaryOutboxRegistrar.Registration(null, false);
                if (registration.conflict()) return outboxConflict(target, persisted);
                return acceptance(
                        target,
                        accepted,
                        persisted,
                        accepted,
                        accepted ? null : "WRITING_CALLBACK_STATE_NOOP",
                        registration.outboxId());
            }
            WritingBoundaryOutboxRegistrar.Registration registration = outbox.register(
                    transaction,
                    taskId,
                    target.command() == null ? null : target.command().getId(),
                    boundary,
                    persisted);
            if (registration.conflict()) return outboxConflict(target, persisted);
            LocalDateTime now = DatabaseTimestamp.now(clock);
            WritingTaskFailure.apply(task, code, now, json);
            transition(
                    target.command(),
                    "failed",
                    Map.of("code", code),
                    Map.of("code", code));
            task.update();
            if (target.command() != null) target.command().update();
            return acceptance(
                    target, true, persisted, false, null, registration.outboxId());
        });
    }

    private Target lockTarget(DSLContext transaction, String taskId, String jobId) {
        // 先无锁读取身份只用于确定统一锁顺序；所有身份在取得实际行锁后都会再次核验。
        Record identity = transaction.select(WRITINGTASK.fields())
                .select(NOVEL.USERID)
                .from(WRITINGTASK)
                .join(NOVEL)
                .on(NOVEL.ID.eq(WRITINGTASK.NOVELID))
                .where(WRITINGTASK.ID.eq(taskId))
                .fetchOne();
        if (identity == null) return null;
        WritingtaskRecord observed =
                identity.into(WRITINGTASK).into(WritingtaskRecord.class);
        String ownerId = identity.get(NOVEL.USERID);
        if (transaction.select(NOVEL.ID)
                        .from(NOVEL)
                        .where(NOVEL.ID.eq(observed.getNovelid()))
                        .forUpdate()
                        .fetchOne(NOVEL.ID)
                == null) {
            return null;
        }
        if (transaction.select(CHAPTER.ID)
                        .from(CHAPTER)
                        .where(
                                CHAPTER.ID.eq(observed.getChapterid()),
                                CHAPTER.NOVELID.eq(observed.getNovelid()))
                        .forUpdate()
                        .fetchOne(CHAPTER.ID)
                == null) {
            return null;
        }
        transaction.select(OUTLINE.ID)
                .from(OUTLINE)
                .where(OUTLINE.NOVELID.eq(observed.getNovelid()))
                .forUpdate()
                .fetch();
        if (observed.getWritingsessionid() != null) {
            transaction.select(WRITINGSESSION.ID)
                    .from(WRITINGSESSION)
                    .where(WRITINGSESSION.ID.eq(observed.getWritingsessionid()))
                    .forUpdate()
                    .fetch();
        }
        WritingtaskRecord task = transaction.selectFrom(WRITINGTASK)
                .where(WRITINGTASK.ID.eq(taskId))
                .forUpdate()
                .fetchOne();
        if (task == null
                || !Objects.equals(task.getNovelid(), observed.getNovelid())
                || !Objects.equals(task.getChapterid(), observed.getChapterid())) {
            return null;
        }
        WritingruncommandRecord observedCommand = transaction.selectFrom(WRITINGRUNCOMMAND)
                .where(WRITINGRUNCOMMAND.ID.eq(jobId))
                .fetchOne();
        if (observedCommand != null && isShortSafely(observedCommand)) {
            // 中短篇完成会创建版本 Artifact，必须在锁命令前按统一顺序锁定对应版本链。
            String artifactKey = shortArtifactKey(observedCommand, task);
            if (artifactKey != null) {
                transaction.select(REVIEWARTIFACT.ID)
                        .from(REVIEWARTIFACT)
                        .where(
                                REVIEWARTIFACT.NOVELID.eq(task.getNovelid()),
                                REVIEWARTIFACT.ARTIFACTKEY.eq(artifactKey))
                        .orderBy(REVIEWARTIFACT.CREATEDAT.asc(), REVIEWARTIFACT.ID.asc())
                        .forUpdate()
                        .fetch();
            }
        }
        List<String> activeIds = transaction.select(WRITINGRUNCOMMAND.ID)
                .from(WRITINGRUNCOMMAND)
                .where(
                        WRITINGRUNCOMMAND.TASKID.eq(taskId),
                        WRITINGRUNCOMMAND.STATUS.in(ACTIVE_COMMANDS))
                .fetch(WRITINGRUNCOMMAND.ID);
        if (activeIds.size() > 1) return null;
        String activeId = activeIds.isEmpty() ? null : activeIds.getFirst();
        if (activeId != null && !activeId.equals(jobId)) return null;
        // 没有活动命令时只允许最新终态命令重放；更早 job 永远不能重新获得回调身份。
        String latestId = activeId;
        if (latestId == null) {
            latestId = transaction.select(WRITINGRUNCOMMAND.ID)
                    .from(WRITINGRUNCOMMAND)
                    .where(WRITINGRUNCOMMAND.TASKID.eq(taskId))
                    .orderBy(WRITINGRUNCOMMAND.CREATEDAT.desc(), WRITINGRUNCOMMAND.ID.desc())
                    .limit(1)
                    .fetchOne(WRITINGRUNCOMMAND.ID);
        }
        if (observedCommand != null) {
            if (!taskId.equals(observedCommand.getTaskid()) || !jobId.equals(latestId)) {
                return null;
            }
            WritingruncommandRecord command = transaction.selectFrom(WRITINGRUNCOMMAND)
                    .where(
                            WRITINGRUNCOMMAND.ID.eq(jobId),
                            WRITINGRUNCOMMAND.TASKID.eq(taskId))
                    .forUpdate()
                    .fetchOne();
            if (command == null) return null;
            return new Target(
                    task,
                    command,
                    !ACTIVE_COMMANDS.contains(command.getStatus()),
                    ownerId);
        }
        if (latestId != null || !legacyJobId(task).equals(jobId)) return null;
        return new Target(task, null, TERMINAL_TASKS.contains(task.getPhase()), ownerId);
    }

    private String checkpointPhase(Target target, String serialized, String fallback) {
        Map<String, Object> checkpoint = object(serialized, "WRITING_SNAPSHOT_INVALID");
        Map<String, Object> commandPayload = target.command() == null
                ? Map.of()
                : WritingCommandPayload.parse(
                                target.command().getKind(),
                                target.command().getPayloadjson(),
                                json)
                        .job();
        boolean commandShort = "short_medium".equals(commandPayload.get("workflow"));
        boolean checkpointShort = "short_medium".equals(checkpoint.get("workflow"));
        if (commandShort != checkpointShort) {
            throw new ApiException(
                    409,
                    "WRITING_CHECKPOINT_COMMAND_MISMATCH",
                    "检查点 workflow 与锁定命令不一致");
        }
        if (commandShort) {
            if (!Objects.equals(checkpoint.get("operation"), commandPayload.get("operation"))) {
                throw new ApiException(
                        409,
                        "WRITING_CHECKPOINT_COMMAND_MISMATCH",
                        "检查点 operation 与锁定命令不一致");
            }
            if (!Set.of("generating", "completed").contains(checkpoint.get("phase"))) {
                throw snapshotInvalid("中短篇检查点阶段无效");
            }
            return "active";
        }
        try {
            WritingGraphSnapshot.parse(
                    serialized,
                    json,
                    target.task().getId(),
                    null,
                    target.task().getNovelid(),
                    target.task().getChapterid());
        } catch (IllegalArgumentException exception) {
            throw snapshotInvalid(exception.getMessage());
        }
        // 图内终态 checkpoint 只表示可重放快照；数据库任务要等 complete/fail 回调后才进入终态。
        return Set.of("completed", "error").contains(fallback) ? "active" : fallback;
    }

    private int persistedSequence(WritingtaskRecord task) {
        if (task.getGraphstatejson() == null) return 0;
        try {
            return WritingGraphSnapshot.eventSequence(task.getGraphstatejson(), json);
        } catch (IllegalArgumentException exception) {
            throw snapshotInvalid(exception.getMessage());
        }
    }

    private void transition(
            WritingruncommandRecord command,
            String target,
            Map<String, Object> result,
            Map<String, Object> callbackResult) {
        if (command == null) return;
        LocalDateTime now = DatabaseTimestamp.now(clock);
        if ("processing".equals(target)) {
            if ("processing".equals(command.getStatus())) return;
            command.setStatus("processing");
            if (command.getSubmittedat() == null) command.setSubmittedat(now);
            command.setLasterror(null);
            command.setUpdatedat(now);
            return;
        }
        command.setStatus(target);
        command.setCompletedat(now);
        command.setUpdatedat(now);
        if (callbackResult != null) {
            Map<String, Object> persisted = terminalResultPayload(command, result);
            persisted.put(TERMINAL_CALLBACK_RESULT, callbackResult);
            command.setResultjson(canonical(persisted));
        } else if (command.getResultjson() == null && result != null) {
            command.setResultjson(canonical(result));
        }
    }

    private void applyCompletionFields(
            WritingtaskRecord task, Map<String, Object> result, boolean setPhase) {
        Object finalValue = result.containsKey("finalContent")
                ? result.get("finalContent")
                : result.get("finalResponse");
        if (finalValue instanceof String text) task.setFinalcontent(text);
        if (result.get("agentOutputs") != null) {
            task.setAgentoutputs(json.writeValueAsString(result.get("agentOutputs")));
        }
        if (setPhase && !TERMINAL_TASKS.contains(task.getPhase())) {
            task.setPhase(Writingtaskphase.completed);
        }
        task.setUpdatedat(DatabaseTimestamp.now(clock));
    }

    private void persistMessage(
            DSLContext transaction,
            WritingtaskRecord task,
            String role,
            String content,
            String eventType,
            String agentId) {
        String visible = content.strip();
        if (visible.isEmpty() || task.getWritingsessionid() == null) return;
        String serialized = WritingMessageMetadata.serialize(
                task.getId(), eventType, visible, agentId, "workflow", json);
        String existing = transaction.select(WRITINGMESSAGE.ID)
                .from(WRITINGMESSAGE)
                .where(
                        WRITINGMESSAGE.SESSIONID.eq(task.getWritingsessionid()),
                        WRITINGMESSAGE.METADATA.eq(serialized))
                .fetchAny(WRITINGMESSAGE.ID);
        if (existing != null) return;
        LocalDateTime now = DatabaseTimestamp.now(clock);
        transaction.insertInto(WRITINGMESSAGE)
                .set(WRITINGMESSAGE.ID, ids.next())
                .set(WRITINGMESSAGE.SESSIONID, task.getWritingsessionid())
                .set(WRITINGMESSAGE.ROLE, role)
                .set(WRITINGMESSAGE.AGENTID, agentId)
                .set(WRITINGMESSAGE.CONTENT, visible)
                .set(WRITINGMESSAGE.METADATA, serialized)
                .set(WRITINGMESSAGE.CREATEDAT, now)
                .execute();
        transaction.update(WRITINGSESSION)
                .set(WRITINGSESSION.UPDATEDAT, now)
                .where(WRITINGSESSION.ID.eq(task.getWritingsessionid()))
                .execute();
    }

    private boolean completionCompatible(
            WritingtaskRecord task,
            WritingruncommandRecord command,
            Map<String, Object> incoming) {
        // 决定命令的 result 先保存受理回执，首次终态需与任务事实比较；后续才比较冻结 callback 原文。
        if (!"artifact_decision".equals(command.getKind())
                || hasTerminalCallback(command)) {
            return commandResultContains(command, incoming);
        }
        return taskCompletionCompatible(task, incoming);
    }

    private boolean failureCompatible(
            WritingtaskRecord task, WritingruncommandRecord command, String code) {
        if (!"artifact_decision".equals(command.getKind())
                || hasTerminalCallback(command)) {
            return commandResultContains(command, Map.of("code", code));
        }
        return taskFailureCompatible(task, code);
    }

    private boolean commandResultContains(
            WritingruncommandRecord command, Map<String, Object> incoming) {
        Map<String, Object> stored = objectOrNull(command.getResultjson());
        if (stored == null) return false;
        Object callback = stored.get(TERMINAL_CALLBACK_RESULT);
        if (callback instanceof Map<?, ?> map) {
            return Objects.equals(stringMap(map), incoming);
        }
        Map<String, Object> comparable = new LinkedHashMap<>(stored);
        if (isShort(command)) {
            comparable.remove("full_check".equals(commandJob(command).get("operation"))
                    ? "checkReport"
                    : "candidateVersionId");
        }
        return comparable.equals(incoming);
    }

    private boolean taskCompletionCompatible(
            WritingtaskRecord task, Map<String, Object> incoming) {
        if (!Set.of("finalContent", "finalResponse", "agentOutputs")
                .containsAll(incoming.keySet())) {
            return false;
        }
        Object explicit = incoming.get("finalContent");
        Object response = incoming.get("finalResponse");
        if (explicit instanceof String first
                && response instanceof String second
                && !first.equals(second)) {
            return false;
        }
        Object finalValue = incoming.containsKey("finalContent") ? explicit : response;
        if (task.getFinalcontent() != null) {
            if (!(finalValue instanceof String text)
                    || !task.getFinalcontent().equals(text)) return false;
        } else if (finalValue instanceof String) {
            return false;
        }
        Object outputs = incoming.get("agentOutputs");
        if (task.getAgentoutputs() == null) return outputs == null;
        if (outputs == null) return false;
        try {
            Object stored = json.readValue(
                    task.getAgentoutputs(), new TypeReference<Object>() {});
            return Objects.equals(stored, outputs);
        } catch (RuntimeException exception) {
            return false;
        }
    }

    private boolean taskFailureCompatible(WritingtaskRecord task, String code) {
        if (task.getGraphstatejson() == null) return true;
        Map<String, Object> snapshot = objectOrNull(task.getGraphstatejson());
        if (snapshot == null) return false;
        Object message = snapshot.get("errorMessage");
        if (!(message instanceof String text)
                || !text.startsWith("智能体运行失败：")) return true;
        return text.endsWith(code);
    }

    private boolean hasTerminalCallback(WritingruncommandRecord command) {
        Map<String, Object> result = objectOrNull(command.getResultjson());
        return result != null && result.get(TERMINAL_CALLBACK_RESULT) instanceof Map<?, ?>;
    }

    private Map<String, Object> terminalResultPayload(
            WritingruncommandRecord command, Map<String, Object> result) {
        if (!"artifact_decision".equals(command.getKind())) {
            return new LinkedHashMap<>(result == null ? Map.of() : result);
        }
        Map<String, Object> existing = objectOrNull(command.getResultjson());
        return new LinkedHashMap<>(existing == null
                ? result == null ? Map.of() : result
                : existing);
    }

    private boolean isShort(WritingruncommandRecord command) {
        return "short_medium".equals(commandJob(command).get("workflow"));
    }

    private boolean isShortSafely(WritingruncommandRecord command) {
        try {
            return isShort(command);
        } catch (RuntimeException exception) {
            return false;
        }
    }

    private Map<String, Object> commandJob(WritingruncommandRecord command) {
        return WritingCommandPayload.parse(
                        command.getKind(), command.getPayloadjson(), json)
                .job();
    }

    private String shortArtifactKey(
            WritingruncommandRecord command, WritingtaskRecord task) {
        Map<String, Object> job = commandJob(command);
        return switch (Objects.toString(job.get("documentType"), "")) {
            case "outline" -> "short-medium:outline:" + task.getNovelid();
            case "manuscript" -> "short-medium:manuscript:" + task.getChapterid();
            default -> null;
        };
    }

    private String legacyJobId(WritingtaskRecord task) {
        if (task.getGraphstatejson() != null) {
            Map<String, Object> snapshot = objectOrNull(task.getGraphstatejson());
            Object callback = snapshot == null ? null : snapshot.get("callbackJobId");
            if (callback instanceof String text && !text.isBlank()) return text;
        }
        // 该哈希精确复刻 Python 历史 jobId；只用于无持久命令任务，不能用于新命令。
        boolean resume = task.getGraphstatejson() != null;
        String fingerprint = resume ? task.getGraphstatejson() : "initial";
        String source = "writing:"
                + task.getId()
                + ":"
                + (resume ? "True" : "False")
                + ":"
                + fingerprint;
        return "writing-" + CommandIdempotency.sha256(
                        source.getBytes(StandardCharsets.UTF_8))
                .substring(0, 32);
    }

    private WritingCallbackAcceptance outboxConflict(Target target, int persisted) {
        return acceptance(
                target,
                false,
                persisted,
                false,
                "WRITING_OUTBOX_BOUNDARY_CONFLICT",
                null);
    }

    private static WritingCallbackAcceptance rejected(int persisted, String code) {
        return WritingCallbackAcceptance.rejected(persisted, code);
    }

    private static WritingCallbackAcceptance acceptance(
            Target target,
            boolean accepted,
            int persisted,
            boolean alreadyApplied,
            String rejection,
            String outboxId) {
        return new WritingCallbackAcceptance(
                accepted,
                persisted,
                alreadyApplied,
                rejection,
                target.task().getPhase().getLiteral(),
                target.command() == null ? null : target.command().getStatus(),
                outboxId);
    }

    private Map<String, Object> object(String serialized, String code) {
        Map<String, Object> result = objectOrNull(serialized);
        if (result == null) {
            throw new ApiException(409, code, "持久写作快照不是有效 JSON");
        }
        return result;
    }

    private Map<String, Object> objectOrNull(String serialized) {
        if (serialized == null) return null;
        try {
            Object parsed = json.readValue(serialized, new TypeReference<Object>() {});
            if (!(parsed instanceof Map<?, ?> map)) return null;
            return stringMap(map);
        } catch (RuntimeException exception) {
            return null;
        }
    }

    private static Map<String, Object> stringMap(Map<?, ?> value) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : value.entrySet()) {
            if (!(entry.getKey() instanceof String key)) return null;
            result.put(key, entry.getValue());
        }
        return result;
    }

    private String canonical(Map<String, Object> value) {
        return new String(
                CommandIdempotency.canonicalJsonBytes(value, json),
                StandardCharsets.UTF_8);
    }

    private static ApiException snapshotInvalid(String message) {
        return new ApiException(409, "WRITING_SNAPSHOT_INVALID", message);
    }

    private record Target(
            WritingtaskRecord task,
            WritingruncommandRecord command,
            boolean alreadyApplied,
            String userId) {}
}
