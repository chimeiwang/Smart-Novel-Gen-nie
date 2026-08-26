package cn.inkforge.core.quality.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.CHAPTERQUALITYCHECK;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.WORKFLOWRUN;
import static cn.inkforge.core.db.generated.Tables.WRITINGTASK;

import cn.inkforge.contracts.api.ConsistencyIssue;
import cn.inkforge.contracts.api.ConsistencyScores;
import cn.inkforge.contracts.api.QualityCheckDto;
import cn.inkforge.contracts.api.QualityCheckStatus;
import cn.inkforge.contracts.api.QualityCheckType;
import cn.inkforge.contracts.api.QualityGate;
import cn.inkforge.contracts.api.QualityRunContextResponse;
import cn.inkforge.contracts.api.QualityRunSuccessRequest;
import cn.inkforge.contracts.api.RunQualityCheckRequest;
import cn.inkforge.contracts.api.UpdateQualityCheckRequest;
import cn.inkforge.core.db.generated.enums.Chapterstatus;
import cn.inkforge.core.db.generated.enums.Qualitycheckstatus;
import cn.inkforge.core.db.generated.enums.Qualitychecktype;
import cn.inkforge.core.db.generated.enums.Workflowrunkind;
import cn.inkforge.core.db.generated.enums.Workflowrunstatus;
import cn.inkforge.core.db.generated.tables.records.ChapterRecord;
import cn.inkforge.core.db.generated.tables.records.ChapterqualitycheckRecord;
import cn.inkforge.core.db.generated.tables.records.WorkflowrunRecord;
import cn.inkforge.core.db.generated.tables.records.WritingtaskRecord;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.platform.idempotency.CommandIdempotencyStore;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.quality.application.QualityRepository;
import cn.inkforge.core.quality.domain.QualityDispatchRecord;
import cn.inkforge.core.quality.domain.QualityRunCreation;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Clock;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.jooq.DSLContext;
import org.jooq.Record;
import org.openapitools.jackson.nullable.JsonNullable;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/**
 * 质量检查的 PostgreSQL 权威实现：冻结输入、运行状态和公开检查项在同一事务边界内收敛。
 *
 * <p>{@code WorkflowRun} 保存本次正文快照，{@code ChapterQualityCheck} 只接受最新运行且正文哈希仍匹配的
 * 结果。旧运行仍需形成自己的终态，但绝不能覆盖新运行或使新正文通过质量门禁。
 */
final class JooqQualityRepository implements QualityRepository {

    private static final String SOURCE_CHANGED = "QUALITY_SOURCE_CHANGED";
    private static final List<Workflowrunstatus> ACTIVE_RUN_STATUSES =
            List.of(Workflowrunstatus.pending, Workflowrunstatus.running);
    private static final List<Workflowrunstatus> TERMINAL_RUN_STATUSES = List.of(
            Workflowrunstatus.completed,
            Workflowrunstatus.failed,
            Workflowrunstatus.cancelled);
    private static final DateTimeFormatter SOURCE_TIME =
            DateTimeFormatter.ofPattern("uuuu-MM-dd'T'HH:mm:ss");

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final ObjectMapper json;
    private final CommandIdempotencyStore idempotency;

    JooqQualityRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock clock,
            ObjectMapper json) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
        this.idempotency = new CommandIdempotencyStore(json);
    }

    @Override
    public QualityCheckDto get(String userId, String checkId) {
        Record row = database.dsl().select(CHAPTERQUALITYCHECK.fields())
                .select(NOVEL.USERID)
                .from(CHAPTERQUALITYCHECK)
                .join(CHAPTER)
                .on(CHAPTER.ID.eq(CHAPTERQUALITYCHECK.CHAPTERID))
                .join(NOVEL)
                .on(NOVEL.ID.eq(CHAPTER.NOVELID))
                .where(CHAPTERQUALITYCHECK.ID.eq(checkId))
                .fetchOne();
        if (row == null) throw notFound();
        if (!userId.equals(row.get(NOVEL.USERID))) throw forbidden();
        return dto(row.into(CHAPTERQUALITYCHECK));
    }

    @Override
    public QualityCheckDto updateStatus(
            String userId, String checkId, UpdateQualityCheckRequest request) {
        return database.transactionResult(transaction -> {
            LockedScope scope = lockScope(transaction, userId, checkId);
            ChapterqualitycheckRecord check = scope.check();
            Qualitycheckstatus requested = Qualitycheckstatus.lookupLiteral(
                    request.getStatus().getValue());
            boolean reset = Boolean.TRUE.equals(request.getResetResult());
            if (publicUpdateIsIdempotent(check, requested, reset)) return dto(check);
            if (!DatabaseTimestamp.sameInstant(
                    check.getUpdatedat(), request.getExpectedUpdatedAt())) {
                throw new ApiException(
                        409,
                        "QUALITY_CHECK_VERSION_CONFLICT",
                        "质量检查已在其他位置更新，请重新加载后再操作",
                        Map.of("currentUpdatedAt", DatabaseTimestamp.api(check.getUpdatedat())));
            }
            if (scope.chapter().getStatus() == Chapterstatus.completed) {
                throw new ApiException(
                        409,
                        "QUALITY_CHECK_CHAPTER_COMPLETED",
                        "已完成章节不能重置或跳过一致性终检");
            }
            if (activeRun(transaction, checkId) != null) {
                throw new ApiException(
                        409,
                        "QUALITY_RUN_ACTIVE",
                        "质量检查运行期间不能修改检查状态");
            }
            check.setStatus(requested);
            if (reset) clearResult(check);
            check.setUpdatedat(DatabaseTimestamp.next(clock, check.getUpdatedat()));
            check.update();
            return dto(check);
        });
    }

    @Override
    public QualityRunCreation createRun(
            String userId, String checkId, RunQualityCheckRequest request) {
        String sourceTaskId = nullable(request.getTaskId());
        String message = nullable(request.getMessage());
        Map<String, Object> normalizedBody = new LinkedHashMap<>();
        normalizedBody.put("taskId", sourceTaskId);
        normalizedBody.put("message", message);
        return database.transactionResult(transaction -> {
            // 质量运行与写作命令共享用户级幂等命名空间，必须先串行化再锁小说和章节。
            transaction.fetchValue(
                    "SELECT pg_advisory_xact_lock(?)",
                    CommandIdempotency.advisoryLockKey(
                            userId, request.getClientRequestId()));
            // 第一次只验证已有记录的可见元数据；资源锁定后用完整 fingerprint 再确认归属。
            validatePreliminaryReplay(
                    idempotency.resolve(
                            transaction, userId, request.getClientRequestId(), null),
                    checkId,
                    normalizedBody,
                    request.getClientRequestId());

            LockedScope scope = lockScope(transaction, userId, checkId);
            Map<String, Object> resourceIdentity = new LinkedHashMap<>();
            resourceIdentity.put("novelId", scope.novelId());
            resourceIdentity.put("chapterId", scope.chapter().getId());
            resourceIdentity.put("checkItemId", checkId);
            String fingerprint = CommandIdempotency.requestFingerprint(
                    "quality_run", resourceIdentity, normalizedBody, json);
            CommandIdempotencyStore.Resolution replay = idempotency.resolve(
                    transaction,
                    userId,
                    request.getClientRequestId(),
                    fingerprint);
            validatePreliminaryReplay(
                    replay,
                    checkId,
                    normalizedBody,
                    request.getClientRequestId());
            if (replay != null) {
                WorkflowrunRecord persisted = lockRun(transaction, replay.recordId());
                if (persisted.getKind() != Workflowrunkind.quality_check
                        || !"quality_check".equals(persisted.getSourcetype())
                        || !userId.equals(persisted.getUserid())
                        || !checkId.equals(persisted.getSourceid())) {
                    throw CommandIdempotencyStore.reused(request.getClientRequestId());
                }
                return new QualityRunCreation(dispatchRecord(persisted), false);
            }

            if (scope.chapter().getStatus() != Chapterstatus.review) {
                throw new ApiException(
                        409,
                        "QUALITY_CHECK_CHAPTER_NOT_IN_REVIEW",
                        "只有待审章节可以运行一致性终检");
            }
            if (scope.check().getType() != Qualitychecktype.consistency) {
                throw new ApiException(
                        400,
                        "UNSUPPORTED_QUALITY_CHECK",
                        "当前只支持一致性终检");
            }
            validateTaskBinding(
                    transaction,
                    sourceTaskId,
                    userId,
                    scope.novelId(),
                    scope.chapter().getId());
            if (activeRun(transaction, checkId) != null) {
                throw new ApiException(
                        409,
                        "QUALITY_RUN_ACTIVE",
                        "质量检查已有运行中的任务");
            }

            LocalDateTime now = DatabaseTimestamp.now(clock);
            scope.check().setStatus(Qualitycheckstatus.running);
            scope.check().setUpdatedat(DatabaseTimestamp.next(clock, scope.check().getUpdatedat()));
            scope.check().update();
            // 正文、哈希、来源时间和可选 taskId 固定写入 WorkflowRun；dispatcher 不再读取当前章节。
            String runId = ids.next();
            WorkflowrunRecord run = transaction.newRecord(WORKFLOWRUN);
            run.setId(runId);
            run.setChapterid(scope.chapter().getId());
            run.setNovelid(scope.novelId());
            run.setUserid(userId);
            run.setKind(Workflowrunkind.quality_check);
            run.setStatus(Workflowrunstatus.pending);
            run.setSourcetype("quality_check");
            run.setSourceid(checkId);
            run.setInput(runInput(
                    request.getClientRequestId(),
                    resourceIdentity,
                    normalizedBody,
                    fingerprint,
                    checkId,
                    sourceTaskId,
                    message,
                    scope.chapter()));
            run.setCreatedat(now);
            run.setUpdatedat(now);
            run.insert();
            return new QualityRunCreation(dispatchRecord(run), true);
        });
    }

    @Override
    public List<QualityDispatchRecord> listDispatchable(int limit) {
        if (limit < 1) throw new IllegalArgumentException("质量检查领取数量无效");
        return database.transactionResult(transaction -> {
            // skip locked 允许多个后台领取者分工；损坏单条只收敛自身，不阻断同批其他运行。
            List<WorkflowrunRecord> runs = transaction.selectFrom(WORKFLOWRUN)
                    .where(
                            WORKFLOWRUN.KIND.eq(Workflowrunkind.quality_check),
                            WORKFLOWRUN.STATUS.in(ACTIVE_RUN_STATUSES))
                    .orderBy(WORKFLOWRUN.UPDATEDAT.asc(), WORKFLOWRUN.ID.asc())
                    .limit(limit)
                    .forUpdate()
                    .skipLocked()
                    .fetch();
            List<QualityDispatchRecord> records = new ArrayList<>();
            LocalDateTime now = DatabaseTimestamp.now(clock);
            for (WorkflowrunRecord run : runs) {
                try {
                    records.add(dispatchRecord(run));
                } catch (IllegalArgumentException exception) {
                    run.setStatus(Workflowrunstatus.failed);
                    run.setErrormessage("QUALITY_RUN_INPUT_INVALID");
                    run.setUpdatedat(DatabaseTimestamp.next(clock, run.getUpdatedat()));
                    run.update();
                }
            }
            return List.copyOf(records);
        });
    }

    @Override
    public void markRunning(String runId) {
        database.transactionResult(transaction -> {
            WorkflowrunRecord run = lockRun(transaction, runId);
            if (ACTIVE_RUN_STATUSES.contains(run.getStatus())) {
                if (run.getStatus() == Workflowrunstatus.running
                        && run.getErrormessage() == null) {
                    return null;
                }
                run.setStatus(Workflowrunstatus.running);
                run.setErrormessage(null);
                run.setUpdatedat(DatabaseTimestamp.next(clock, run.getUpdatedat()));
                run.update();
            }
            return null;
        });
    }

    @Override
    public void recordDispatchFailure(String runId, String errorCode) {
        database.transactionResult(transaction -> {
            WorkflowrunRecord run = lockRun(transaction, runId);
            if (ACTIVE_RUN_STATUSES.contains(run.getStatus())) {
                if (Objects.equals(run.getErrormessage(), errorCode)) return null;
                run.setErrormessage(errorCode);
                run.setUpdatedat(DatabaseTimestamp.next(clock, run.getUpdatedat()));
                run.update();
            }
            return null;
        });
    }

    @Override
    public QualityRunContextResponse context(
            String userId,
            String checkId,
            String runId,
            String sourceTaskId,
            String message) {
        return database.transactionResult(transaction -> {
            LockedChapter locked = lockChapterOwner(transaction, userId, checkId, false);
            WorkflowrunRecord run = requireBoundRun(
                    transaction, runId, checkId, userId, null);
            RunInput input = runInput(run);
            if (!Objects.equals(input.sourceTaskId(), sourceTaskId)
                    || !Objects.equals(input.message(), message)) {
                throw new ApiException(
                        409,
                        "QUALITY_RUN_INPUT_MISMATCH",
                        "质量检查运行输入与持久记录不匹配");
            }
            if (!ACTIVE_RUN_STATUSES.contains(run.getStatus())
                    || !isLatest(transaction, run)) {
                throw new ApiException(
                        409,
                        "QUALITY_RUN_NOT_ACTIVE",
                        "质量检查运行已不是当前活动任务");
            }
            ChapterqualitycheckRecord check = lockCheck(
                    transaction, checkId, locked.chapter().getId());
            validateTaskBinding(
                    transaction,
                    input.sourceTaskId(),
                    userId,
                    locked.novelId(),
                    locked.chapter().getId());
            if (check.getStatus() != Qualitycheckstatus.running) {
                check.setStatus(Qualitycheckstatus.running);
                check.setUpdatedat(DatabaseTimestamp.next(clock, check.getUpdatedat()));
                check.update();
            }
            // Agent 始终读取 WorkflowRun 的冻结正文，而不是上面仅用于归属与失效判断的当前章节。
            return new QualityRunContextResponse(
                    input.chapterContent(),
                    locked.chapter().getId(),
                    checkId,
                    input.message() == null ? "检查本章一致性" : input.message(),
                    locked.novelId());
        });
    }

    @Override
    public void completeRun(
            String userId,
            String checkId,
            String runId,
            String novelId,
            QualityRunSuccessRequest result) {
        validateReport(result);
        Map<String, Object> report = report(result);
        database.transactionResult(transaction -> {
            LockedChapter locked = lockChapterOwner(transaction, userId, checkId, false);
            WorkflowrunRecord run = requireBoundRun(
                    transaction, runId, checkId, userId, novelId);
            ChapterqualitycheckRecord check = lockCheck(
                    transaction, checkId, locked.chapter().getId());
            if (TERMINAL_RUN_STATUSES.contains(run.getStatus())) return null;
            RunInput input = runInput(run);
            boolean latest = isLatest(transaction, run);
            String output = json.writeValueAsString(report);
            // 过期回调仍保存自己的报告用于审计，但只能 cancelled，不能把旧报告写进公开检查项。
            if (!sha256(locked.chapter().getContent()).equals(input.chapterContentSha256())) {
                run.setStatus(Workflowrunstatus.cancelled);
                run.setOutput(output);
                run.setErrormessage(SOURCE_CHANGED);
                run.setUpdatedat(DatabaseTimestamp.next(clock, run.getUpdatedat()));
                run.update();
                if (latest) resetCheck(check);
                return null;
            }
            run.setStatus(Workflowrunstatus.completed);
            run.setOutput(output);
            run.setErrormessage(null);
            run.setUpdatedat(DatabaseTimestamp.next(clock, run.getUpdatedat()));
            run.update();
            // 同一检查项可能已有更新运行；只有最新运行可以推进用户看到的质量门禁。
            if (!latest) return null;
            applyReport(check, result);
            return null;
        });
    }

    @Override
    public void failRun(String userId, String checkId, String runId, String novelId) {
        database.transactionResult(transaction -> {
            LockedChapter locked = lockChapterOwner(transaction, userId, checkId, false);
            WorkflowrunRecord run = requireBoundRun(
                    transaction, runId, checkId, userId, novelId);
            ChapterqualitycheckRecord check = lockCheck(
                    transaction, checkId, locked.chapter().getId());
            if (TERMINAL_RUN_STATUSES.contains(run.getStatus())) return null;
            RunInput input = runInput(run);
            boolean latest = isLatest(transaction, run);
            if (!sha256(locked.chapter().getContent()).equals(input.chapterContentSha256())) {
                run.setStatus(Workflowrunstatus.cancelled);
                run.setErrormessage(SOURCE_CHANGED);
                run.setUpdatedat(DatabaseTimestamp.next(clock, run.getUpdatedat()));
                run.update();
                if (latest) resetCheck(check);
                return null;
            }
            run.setStatus(Workflowrunstatus.failed);
            run.setErrormessage("QUALITY_RUN_FAILED");
            run.setUpdatedat(DatabaseTimestamp.next(clock, run.getUpdatedat()));
            run.update();
            if (latest) {
                check.setStatus(Qualitycheckstatus.failed);
                check.setUpdatedat(DatabaseTimestamp.next(clock, check.getUpdatedat()));
                check.update();
            }
            return null;
        });
    }

    private LockedScope lockScope(
            DSLContext transaction, String userId, String checkId) {
        LockedChapter locked = lockChapterOwner(transaction, userId, checkId, true);
        ChapterqualitycheckRecord check = lockCheck(
                transaction, checkId, locked.chapter().getId());
        return new LockedScope(locked.novelId(), locked.chapter(), check);
    }

    private LockedChapter lockChapterOwner(
            DSLContext transaction,
            String userId,
            String checkId,
            boolean lockNovel) {
        Record identity = transaction.select(
                        CHAPTERQUALITYCHECK.CHAPTERID,
                        CHAPTER.NOVELID,
                        NOVEL.USERID)
                .from(CHAPTERQUALITYCHECK)
                .join(CHAPTER)
                .on(CHAPTER.ID.eq(CHAPTERQUALITYCHECK.CHAPTERID))
                .join(NOVEL)
                .on(NOVEL.ID.eq(CHAPTER.NOVELID))
                .where(CHAPTERQUALITYCHECK.ID.eq(checkId))
                .fetchOne();
        if (identity == null) throw notFound();
        if (!userId.equals(identity.get(NOVEL.USERID))) throw forbidden();
        String novelId = identity.get(CHAPTER.NOVELID);
        String chapterId = identity.get(CHAPTERQUALITYCHECK.CHAPTERID);
        if (lockNovel) {
            String lockedOwner = transaction.select(NOVEL.USERID)
                    .from(NOVEL)
                    .where(NOVEL.ID.eq(novelId))
                    .forUpdate()
                    .fetchOne(NOVEL.USERID);
            if (!userId.equals(lockedOwner)) throw forbidden();
        }
        ChapterRecord chapter = transaction.selectFrom(CHAPTER)
                .where(CHAPTER.ID.eq(chapterId), CHAPTER.NOVELID.eq(novelId))
                .forUpdate()
                .fetchOne();
        if (chapter == null) throw notFound();
        return new LockedChapter(novelId, chapter);
    }

    private ChapterqualitycheckRecord lockCheck(
            DSLContext transaction, String checkId, String chapterId) {
        ChapterqualitycheckRecord check = transaction.selectFrom(CHAPTERQUALITYCHECK)
                .where(
                        CHAPTERQUALITYCHECK.ID.eq(checkId),
                        CHAPTERQUALITYCHECK.CHAPTERID.eq(chapterId))
                .forUpdate()
                .fetchOne();
        if (check == null) throw notFound();
        return check;
    }

    private void validateTaskBinding(
            DSLContext transaction,
            String taskId,
            String userId,
            String novelId,
            String chapterId) {
        if (taskId == null) return;
        Record row = transaction.select(WRITINGTASK.fields())
                .select(NOVEL.USERID)
                .from(WRITINGTASK)
                .join(NOVEL)
                .on(NOVEL.ID.eq(WRITINGTASK.NOVELID))
                .where(WRITINGTASK.ID.eq(taskId))
                .fetchOne();
        if (row == null) throw taskMismatch();
        WritingtaskRecord task = row.into(WRITINGTASK);
        if (!userId.equals(row.get(NOVEL.USERID))
                || !novelId.equals(task.getNovelid())
                || !chapterId.equals(task.getChapterid())) {
            throw taskMismatch();
        }
    }

    private WorkflowrunRecord activeRun(DSLContext transaction, String checkId) {
        return transaction.selectFrom(WORKFLOWRUN)
                .where(
                        WORKFLOWRUN.KIND.eq(Workflowrunkind.quality_check),
                        WORKFLOWRUN.SOURCEID.eq(checkId),
                        WORKFLOWRUN.STATUS.in(ACTIVE_RUN_STATUSES))
                .orderBy(WORKFLOWRUN.CREATEDAT.asc(), WORKFLOWRUN.ID.asc())
                .limit(1)
                .fetchOne();
    }

    private WorkflowrunRecord lockRun(DSLContext transaction, String runId) {
        WorkflowrunRecord run = transaction.selectFrom(WORKFLOWRUN)
                .where(
                        WORKFLOWRUN.ID.eq(runId),
                        WORKFLOWRUN.KIND.eq(Workflowrunkind.quality_check))
                .forUpdate()
                .fetchOne();
        if (run == null) {
            throw new ApiException(
                    404,
                    "QUALITY_RUN_NOT_FOUND",
                    "质量检查运行不存在");
        }
        return run;
    }

    private WorkflowrunRecord requireBoundRun(
            DSLContext transaction,
            String runId,
            String checkId,
            String userId,
            String expectedNovelId) {
        WorkflowrunRecord run = lockRun(transaction, runId);
        if (!userId.equals(run.getUserid())
                || !checkId.equals(run.getSourceid())
                || (expectedNovelId != null && !expectedNovelId.equals(run.getNovelid()))) {
            throw new ApiException(
                    403,
                    "QUALITY_RUN_MISMATCH",
                    "质量检查运行资源绑定不匹配");
        }
        dispatchRecord(run);
        return run;
    }

    private boolean isLatest(DSLContext transaction, WorkflowrunRecord run) {
        String latest = transaction.select(WORKFLOWRUN.ID)
                .from(WORKFLOWRUN)
                .where(
                        WORKFLOWRUN.KIND.eq(Workflowrunkind.quality_check),
                        WORKFLOWRUN.SOURCEID.eq(run.getSourceid()))
                .orderBy(WORKFLOWRUN.CREATEDAT.desc(), WORKFLOWRUN.ID.desc())
                .limit(1)
                .fetchOne(WORKFLOWRUN.ID);
        return run.getId().equals(latest);
    }

    private void validatePreliminaryReplay(
            CommandIdempotencyStore.Resolution replay,
            String checkId,
            Map<String, Object> normalizedBody,
            String clientRequestId) {
        if (replay == null) return;
        CommandIdempotencyStore.Metadata metadata = replay.metadata();
        if (replay.recordKind() != CommandIdempotencyStore.RecordKind.WORKFLOW_RUN
                || !"quality_run".equals(metadata.commandKind())
                || !checkId.equals(metadata.resourceIdentity().get("checkItemId"))
                || !normalizedBody.equals(metadata.normalizedBody())) {
            throw CommandIdempotencyStore.reused(clientRequestId);
        }
    }

    private String runInput(
            String clientRequestId,
            Map<String, Object> resourceIdentity,
            Map<String, Object> normalizedBody,
            String fingerprint,
            String checkId,
            String sourceTaskId,
            String message,
            ChapterRecord chapter) {
        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("schemaVersion", 1);
        metadata.put("clientRequestId", clientRequestId);
        metadata.put("commandKind", "quality_run");
        metadata.put("resourceIdentity", resourceIdentity);
        metadata.put("normalizedBody", normalizedBody);
        metadata.put("requestFingerprint", fingerprint);
        Map<String, Object> job = new LinkedHashMap<>();
        job.put("checkId", checkId);
        job.put("sourceTaskId", sourceTaskId);
        job.put("message", message);
        job.put("chapterContent", chapter.getContent());
        job.put("chapterContentSha256", sha256(chapter.getContent()));
        job.put("sourceUpdatedAt", sourceUpdatedAt(chapter.getUpdatedat()));
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("_inkforgeCommand", metadata);
        payload.put("job", job);
        return json.writeValueAsString(payload);
    }

    private QualityDispatchRecord dispatchRecord(WorkflowrunRecord run) {
        RunInput input = runInput(run);
        if (run.getUserid() == null || run.getSourceid() == null) {
            throw new IllegalArgumentException("质量检查运行归属无效");
        }
        return new QualityDispatchRecord(
                run.getId(),
                run.getSourceid(),
                run.getUserid(),
                run.getNovelid(),
                run.getChapterid(),
                input.sourceTaskId(),
                input.message());
    }

    private RunInput runInput(WorkflowrunRecord run) {
        Map<String, Object> payload = object(run.getInput());
        if (payload == null) throw new IllegalArgumentException("质量检查运行输入无效");
        if (payload.containsKey("_inkforgeCommand")) {
            payload = payload.get("job") instanceof Map<?, ?> job ? stringMap(job) : null;
        }
        if (payload == null
                || run.getSourceid() == null
                || !run.getSourceid().equals(payload.get("checkId"))) {
            throw new IllegalArgumentException("质量检查运行输入无效");
        }
        Object task = payload.get("sourceTaskId");
        Object message = payload.get("message");
        Object content = payload.get("chapterContent");
        Object contentHash = payload.get("chapterContentSha256");
        Object sourceUpdatedAt = payload.get("sourceUpdatedAt");
        if (task != null && !(task instanceof String)) {
            throw new IllegalArgumentException("质量检查源任务无效");
        }
        if (message != null && !(message instanceof String)) {
            throw new IllegalArgumentException("质量检查消息无效");
        }
        if (!(content instanceof String text)) {
            throw new IllegalArgumentException("质量检查正文快照无效");
        }
        if (!(contentHash instanceof String hash) || !hash.equals(sha256(text))) {
            throw new IllegalArgumentException("质量检查正文哈希无效");
        }
        if (!(sourceUpdatedAt instanceof String version) || version.isEmpty()) {
            throw new IllegalArgumentException("质量检查正文版本无效");
        }
        return new RunInput(
                (String) task, (String) message, text, hash, version);
    }

    private Map<String, Object> object(String value) {
        if (value == null) return null;
        try {
            Object parsed = json.readValue(value, new TypeReference<Object>() {});
            return parsed instanceof Map<?, ?> map ? stringMap(map) : null;
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

    private Map<String, Object> report(QualityRunSuccessRequest value) {
        ConsistencyScores scores = value.getScores();
        Map<String, Object> scoreMap = new LinkedHashMap<>();
        scoreMap.put("characterConsistency", scores.getCharacterConsistency().doubleValue());
        scoreMap.put("worldRuleConsistency", scores.getWorldRuleConsistency().doubleValue());
        scoreMap.put("timelineConsistency", scores.getTimelineConsistency().doubleValue());
        scoreMap.put("causalityConsistency", scores.getCausalityConsistency().doubleValue());
        scoreMap.put("foreshadowingConsistency", scores.getForeshadowingConsistency().doubleValue());
        List<Map<String, Object>> issues = value.getIssues().stream()
                .map(this::issue)
                .toList();
        Map<String, Object> report = new LinkedHashMap<>();
        report.put("scores", scoreMap);
        report.put("qualityGate", value.getQualityGate().getValue());
        report.put("issues", issues);
        report.put("report", value.getReport());
        report.put("rewriteBrief", nullable(value.getRewriteBrief()));
        return report;
    }

    private Map<String, Object> issue(ConsistencyIssue value) {
        Map<String, Object> issue = new LinkedHashMap<>();
        issue.put("dimension", value.getDimension().getValue());
        issue.put("severity", value.getSeverity().getValue());
        issue.put("message", value.getMessage());
        issue.put("evidence", value.getEvidence());
        issue.put("location", nullable(value.getLocation()));
        issue.put("suggestion", value.getSuggestion());
        return issue;
    }

    private void applyReport(
            ChapterqualitycheckRecord check, QualityRunSuccessRequest report) {
        check.setStatus(Qualitycheckstatus.completed);
        check.setResult(report.getReport());
        check.setScorehook(null);
        check.setScoretension(null);
        check.setScorepayoff(null);
        check.setScorepacing(null);
        check.setScoreendinghook(null);
        check.setScorereaderpromise(null);
        ConsistencyScores scores = report.getScores();
        BigDecimal average = scores.getCharacterConsistency()
                .add(scores.getWorldRuleConsistency())
                .add(scores.getTimelineConsistency())
                .add(scores.getCausalityConsistency())
                .add(scores.getForeshadowingConsistency())
                .divide(BigDecimal.valueOf(5));
        // HALF_EVEN 精确兼容 Python round()，不能换成 Java 常见的 HALF_UP。
        check.setScoreoverall(average.setScale(0, RoundingMode.HALF_EVEN).intValueExact());
        check.setQualitygate(report.getQualityGate().getValue());
        check.setRewritebrief(nullable(report.getRewriteBrief()));
        check.setUpdatedat(DatabaseTimestamp.next(clock, check.getUpdatedat()));
        check.update();
    }

    private void resetCheck(ChapterqualitycheckRecord check) {
        check.setStatus(Qualitycheckstatus.pending);
        clearResult(check);
        check.setUpdatedat(DatabaseTimestamp.next(clock, check.getUpdatedat()));
        check.update();
    }

    private static void clearResult(ChapterqualitycheckRecord check) {
        check.setResult(null);
        check.setScorehook(null);
        check.setScoretension(null);
        check.setScorepayoff(null);
        check.setScorepacing(null);
        check.setScoreendinghook(null);
        check.setScorereaderpromise(null);
        check.setScoreoverall(null);
        check.setQualitygate(null);
        check.setRewritebrief(null);
    }

    private static boolean publicUpdateIsIdempotent(
            ChapterqualitycheckRecord check,
            Qualitycheckstatus status,
            boolean reset) {
        if (check.getStatus() != status) return false;
        if (!reset) return true;
        return check.getResult() == null
                && check.getScorehook() == null
                && check.getScoretension() == null
                && check.getScorepayoff() == null
                && check.getScorepacing() == null
                && check.getScoreendinghook() == null
                && check.getScorereaderpromise() == null
                && check.getScoreoverall() == null
                && check.getQualitygate() == null
                && check.getRewritebrief() == null;
    }

    private static void validateReport(QualityRunSuccessRequest report) {
        if (report.getReport() == null || report.getReport().trim().isEmpty()) {
            throw new ApiException(422, "VALIDATION_ERROR", "请求参数校验失败");
        }
    }

    private static QualityCheckDto dto(ChapterqualitycheckRecord value) {
        QualityCheckDto result = new QualityCheckDto();
        result.setId(value.getId());
        result.setChapterId(value.getChapterid());
        result.setType(QualityCheckType.fromValue(value.getType().getLiteral()));
        result.setStatus(QualityCheckStatus.fromValue(value.getStatus().getLiteral()));
        result.setTitle(value.getTitle());
        result.setSummary(value.getSummary());
        result.setResult(value.getResult());
        result.setScoreHook(value.getScorehook());
        result.setScoreTension(value.getScoretension());
        result.setScorePayoff(value.getScorepayoff());
        result.setScorePacing(value.getScorepacing());
        result.setScoreEndingHook(value.getScoreendinghook());
        result.setScoreReaderPromise(value.getScorereaderpromise());
        result.setScoreOverall(value.getScoreoverall());
        result.setQualityGate(value.getQualitygate() == null
                ? null
                : QualityGate.fromValue(value.getQualitygate()));
        result.setRewriteBrief(value.getRewritebrief());
        result.setCreatedAt(DatabaseTimestamp.api(value.getCreatedat()));
        result.setUpdatedAt(DatabaseTimestamp.api(value.getUpdatedat()));
        return result;
    }

    private static String sourceUpdatedAt(LocalDateTime value) {
        if (value == null) throw new IllegalStateException("章节更新时间缺失");
        StringBuilder result = new StringBuilder(SOURCE_TIME.format(value));
        if (value.getNano() != 0) {
            result.append('.').append(String.format("%06d", value.getNano() / 1_000));
        }
        return result.append("+00:00").toString();
    }

    private static String sha256(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("运行环境缺少 SHA-256", exception);
        }
    }

    private static <T> T nullable(JsonNullable<T> value) {
        return value == null || value.isUndefined() ? null : value.orElse(null);
    }

    private static ApiException notFound() {
        return new ApiException(404, "QUALITY_CHECK_NOT_FOUND", "检查项不存在");
    }

    private static ApiException forbidden() {
        return new ApiException(403, "QUALITY_CHECK_FORBIDDEN", "无权访问该检查项");
    }

    private static ApiException taskMismatch() {
        return new ApiException(403, "QUALITY_TASK_MISMATCH", "任务与检查项不匹配");
    }

    private record LockedScope(
            String novelId,
            ChapterRecord chapter,
            ChapterqualitycheckRecord check) {}

    private record LockedChapter(String novelId, ChapterRecord chapter) {}

    private record RunInput(
            String sourceTaskId,
            String message,
            String chapterContent,
            String chapterContentSha256,
            String sourceUpdatedAt) {}
}
