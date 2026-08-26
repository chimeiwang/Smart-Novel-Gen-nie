package cn.inkforge.core.writing.infrastructure;

import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.WRITINGRUNCOMMAND;
import static cn.inkforge.core.db.generated.Tables.WRITINGTASK;

import cn.inkforge.core.db.generated.enums.Writingtaskphase;
import cn.inkforge.core.db.generated.tables.records.WritingtaskRecord;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.writing.application.WritingReconciliationRepository;
import cn.inkforge.core.writing.domain.WritingReconciliationTask;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.jooq.DSLContext;
import tools.jackson.databind.ObjectMapper;

/** 使用行锁把旧任务快照原子转换为唯一耐久对账命令。 */
final class JooqWritingReconciliationRepository implements WritingReconciliationRepository {

    private static final Set<Writingtaskphase> RECONCILABLE =
            Set.of(Writingtaskphase.active, Writingtaskphase.waiting_call);
    private static final Set<String> ACTIVE_COMMANDS = Set.of("pending", "submitted", "processing");

    private final CoreDatabase database;
    private final Clock clock;
    private final ObjectMapper json;

    JooqWritingReconciliationRepository(
            CoreDatabase database, Clock clock, ObjectMapper json) {
        this.database = Objects.requireNonNull(database);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
    }

    @Override
    public List<WritingReconciliationTask> listReconcilable(int limit) {
        if (limit < 1) throw new IllegalArgumentException("对账领取数量必须大于零");
        return database.dsl()
                .select(WRITINGTASK.fields())
                .select(NOVEL.USERID)
                .from(WRITINGTASK)
                .join(NOVEL)
                .on(NOVEL.ID.eq(WRITINGTASK.NOVELID))
                .where(
                        WRITINGTASK.PHASE.in(RECONCILABLE),
                        NOVEL.USERID.isNotNull(),
                        org.jooq.impl.DSL.notExists(database.dsl()
                                .select(WRITINGRUNCOMMAND.ID)
                                .from(WRITINGRUNCOMMAND)
                                .where(
                                        WRITINGRUNCOMMAND.TASKID.eq(WRITINGTASK.ID),
                                        WRITINGRUNCOMMAND.STATUS.in(ACTIVE_COMMANDS))))
                .orderBy(WRITINGTASK.UPDATEDAT.asc(), WRITINGTASK.ID.asc())
                .limit(limit)
                .fetch()
                .map(row -> {
                    WritingtaskRecord task = row.into(WRITINGTASK);
                    return new WritingReconciliationTask(
                            task.getId(),
                            row.get(NOVEL.USERID),
                            task.getNovelid(),
                            task.getChapterid(),
                            task.getWritingsessionid(),
                            task.getPhase().getLiteral(),
                            task.getGraphstatejson());
                });
    }

    @Override
    public boolean createCommand(WritingReconciliationTask expected) {
        Objects.requireNonNull(expected);
        return database.transactionResult(transaction -> createCommand(transaction, expected));
    }

    private boolean createCommand(
            DSLContext transaction, WritingReconciliationTask expected) {
        WritingtaskRecord task = transaction.selectFrom(WRITINGTASK)
                .where(WRITINGTASK.ID.eq(expected.id()))
                .forUpdate()
                .fetchOne();
        if (task == null
                || !Objects.equals(task.getPhase().getLiteral(), expected.phase())
                || !Objects.equals(task.getGraphstatejson(), expected.graphStateJson())
                || !RECONCILABLE.contains(task.getPhase())) {
            return false;
        }
        String active = transaction.select(WRITINGRUNCOMMAND.ID)
                .from(WRITINGRUNCOMMAND)
                .where(
                        WRITINGRUNCOMMAND.TASKID.eq(task.getId()),
                        WRITINGRUNCOMMAND.STATUS.in(ACTIVE_COMMANDS))
                .fetchOne(WRITINGRUNCOMMAND.ID);
        if (active != null) return false;
        boolean resume = task.getGraphstatejson() != null;
        String commandId = commandId(task.getId(), resume, task.getGraphstatejson());
        String existing = transaction.select(WRITINGRUNCOMMAND.ID)
                .from(WRITINGRUNCOMMAND)
                .where(WRITINGRUNCOMMAND.ID.eq(commandId))
                .forUpdate()
                .fetchOne(WRITINGRUNCOMMAND.ID);
        if (existing != null) return false;

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("version", 1);
        payload.put("resume", resume);
        payload.put("chapterId", task.getChapterid());
        payload.put("writingSessionId", task.getWritingsessionid());
        payload.put("resumeInput", null);
        payload.put("force", true);
        String payloadJson = new String(
                CommandIdempotency.canonicalJsonBytes(payload, json), StandardCharsets.UTF_8);
        LocalDateTime now = DatabaseTimestamp.now(clock);
        transaction.insertInto(WRITINGRUNCOMMAND)
                .set(WRITINGRUNCOMMAND.ID, commandId)
                .set(WRITINGRUNCOMMAND.TASKID, task.getId())
                .set(WRITINGRUNCOMMAND.KIND, resume ? "resume" : "start")
                .set(WRITINGRUNCOMMAND.PAYLOADJSON, payloadJson)
                .set(WRITINGRUNCOMMAND.IDEMPOTENCYKEY, "reconcile:" + commandId)
                .set(WRITINGRUNCOMMAND.STATUS, "pending")
                .set(WRITINGRUNCOMMAND.ATTEMPTCOUNT, 0)
                .set(WRITINGRUNCOMMAND.NEXTATTEMPTAT, now)
                .set(WRITINGRUNCOMMAND.CREATEDAT, now)
                .set(WRITINGRUNCOMMAND.UPDATEDAT, now)
                .execute();
        return true;
    }

    static String commandId(String taskId, boolean resume, String graphStateJson) {
        String fingerprint = graphStateJson == null ? "initial" : graphStateJson;
        String source = "writing:"
                + taskId
                + ":"
                + (resume ? "True" : "False")
                + ":"
                + fingerprint;
        return "writing-" + CommandIdempotency.sha256(
                        source.getBytes(StandardCharsets.UTF_8))
                .substring(0, 32);
    }
}
