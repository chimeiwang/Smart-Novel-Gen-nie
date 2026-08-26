package cn.inkforge.core.writing.infrastructure;

import static cn.inkforge.core.db.generated.Tables.WRITINGEVENTOUTBOX;
import static cn.inkforge.core.db.generated.Tables.WRITINGRUNCOMMAND;
import static cn.inkforge.core.db.generated.Tables.WRITINGTASK;
import static org.jooq.impl.DSL.count;
import static org.jooq.impl.DSL.exists;
import static org.jooq.impl.DSL.selectOne;

import cn.inkforge.core.db.generated.tables.Writingeventoutbox;
import cn.inkforge.core.db.generated.tables.records.WritingeventoutboxRecord;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.writing.application.WritingOutboxRepository;
import cn.inkforge.core.writing.domain.WritingEvent;
import cn.inkforge.core.writing.domain.WritingOutboxHealth;
import cn.inkforge.core.writing.domain.WritingOutboxRecord;
import java.time.Clock;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.jooq.Condition;
import org.jooq.DSLContext;
import org.jooq.Record;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/**
 * PostgreSQL Outbox 租约、退避、清理和 SSE 可见性实现。
 *
 * <p>同一任务必须按 {@code sourceSequence} 串行发布，后序边界不能越过未发布的前序边界。领取和发布都以
 * lease token 做 CAS，旧 worker 失去租约后不能确认结果。SSE 回放会查询 Outbox 当前状态，避免把已经被
 * 新命令取代的 waiting 事件重新暴露为可操作草案。
 */
final class JooqWritingOutboxRepository implements WritingOutboxRepository {

    private static final Set<String> BOUNDARY_TYPES = Set.of(
            "completed", "error", "artifact_awaiting_user_approval");

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final ObjectMapper json;

    JooqWritingOutboxRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock clock,
            ObjectMapper json) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
    }

    @Override
    public List<WritingOutboxRecord> claimDue(
            LocalDateTime now, int limit, int leaseSeconds) {
        if (now == null || limit < 1 || leaseSeconds < 1) {
            throw new IllegalArgumentException("Outbox 领取参数无效");
        }
        return database.transactionResult(transaction -> {
            // earlierUnpublished 把顺序约束下推到领取 SQL，多 worker 也不能越过同任务前序边界。
            Writingeventoutbox candidate = WRITINGEVENTOUTBOX.as("candidate");
            Writingeventoutbox earlier = WRITINGEVENTOUTBOX.as("earlier");
            Condition earlierUnpublished = exists(selectOne()
                    .from(earlier)
                    .where(
                            earlier.TASKID.eq(candidate.TASKID),
                            earlier.SOURCESEQUENCE.lt(candidate.SOURCESEQUENCE),
                            earlier.DELIVERYSTATE.in("pending", "delivering", "blocked")));
            Condition claimable = candidate.DELIVERYSTATE
                    .eq("pending")
                    .and(candidate.NEXTATTEMPTAT.le(now))
                    .or(candidate.DELIVERYSTATE
                            .eq("delivering")
                            .and(candidate.LEASEEXPIRESAT.isNotNull())
                            .and(candidate.LEASEEXPIRESAT.le(now)));
            List<Record> rows = transaction.select(candidate.fields())
                    .from(candidate)
                    .where(claimable, earlierUnpublished.not())
                    .orderBy(
                            candidate.NEXTATTEMPTAT.asc(),
                            candidate.CREATEDAT.asc(),
                            candidate.ID.asc())
                    .limit(limit)
                    .forUpdate()
                    .of(candidate)
                    .skipLocked()
                    .fetch();
            LocalDateTime expiresAt = now.plusSeconds(leaseSeconds);
            List<WritingOutboxRecord> result = new ArrayList<>(rows.size());
            for (Record row : rows) {
                WritingeventoutboxRecord record =
                        row.into(candidate).into(WritingeventoutboxRecord.class);
                String leaseToken = ids.next();
                int attempts = record.getAttemptcount() + 1;
                transaction.update(WRITINGEVENTOUTBOX)
                        .set(WRITINGEVENTOUTBOX.DELIVERYSTATE, "delivering")
                        .set(WRITINGEVENTOUTBOX.ATTEMPTCOUNT, attempts)
                        .set(WRITINGEVENTOUTBOX.LEASETOKEN, leaseToken)
                        .set(WRITINGEVENTOUTBOX.LEASEEXPIRESAT, expiresAt)
                        .set(WRITINGEVENTOUTBOX.UPDATEDAT, now)
                        .where(WRITINGEVENTOUTBOX.ID.eq(record.getId()))
                        .execute();
                record.setDeliverystate("delivering");
                record.setAttemptcount(attempts);
                record.setLeasetoken(leaseToken);
                record.setLeaseexpiresat(expiresAt);
                record.setUpdatedat(now);
                result.add(map(record));
            }
            return List.copyOf(result);
        });
    }

    @Override
    public boolean markPublished(
            String outboxId, String leaseToken, String redisEventId) {
        LocalDateTime now = DatabaseTimestamp.now(clock);
        // lease token 是 worker 所有权；返回 false 时调用方必须放弃，不能凭 Redis 成功自行认领发布。
        return database.dsl().update(WRITINGEVENTOUTBOX)
                        .set(WRITINGEVENTOUTBOX.DELIVERYSTATE, "published")
                        .set(WRITINGEVENTOUTBOX.REDISEVENTID, redisEventId)
                        .set(WRITINGEVENTOUTBOX.PUBLISHEDAT, now)
                        .setNull(WRITINGEVENTOUTBOX.LASTERRORCODE)
                        .setNull(WRITINGEVENTOUTBOX.LEASETOKEN)
                        .setNull(WRITINGEVENTOUTBOX.LEASEEXPIRESAT)
                        .set(WRITINGEVENTOUTBOX.UPDATEDAT, now)
                        .where(
                                WRITINGEVENTOUTBOX.ID.eq(outboxId),
                                WRITINGEVENTOUTBOX.DELIVERYSTATE.eq("delivering"),
                                WRITINGEVENTOUTBOX.LEASETOKEN.eq(leaseToken))
                        .execute()
                == 1;
    }

    @Override
    public boolean scheduleRetry(
            String outboxId,
            String leaseToken,
            LocalDateTime nextAttemptAt,
            String errorCode) {
        return database.dsl().update(WRITINGEVENTOUTBOX)
                        .set(WRITINGEVENTOUTBOX.DELIVERYSTATE, "pending")
                        .set(WRITINGEVENTOUTBOX.NEXTATTEMPTAT, nextAttemptAt)
                        .set(WRITINGEVENTOUTBOX.LASTERRORCODE, errorCode)
                        .setNull(WRITINGEVENTOUTBOX.LEASETOKEN)
                        .setNull(WRITINGEVENTOUTBOX.LEASEEXPIRESAT)
                        .set(WRITINGEVENTOUTBOX.UPDATEDAT, DatabaseTimestamp.now(clock))
                        .where(
                                WRITINGEVENTOUTBOX.ID.eq(outboxId),
                                WRITINGEVENTOUTBOX.DELIVERYSTATE.eq("delivering"),
                                WRITINGEVENTOUTBOX.LEASETOKEN.eq(leaseToken))
                        .execute()
                == 1;
    }

    @Override
    public boolean markBlocked(
            String outboxId, String leaseToken, String errorCode) {
        return database.dsl().update(WRITINGEVENTOUTBOX)
                        .set(WRITINGEVENTOUTBOX.DELIVERYSTATE, "blocked")
                        .set(WRITINGEVENTOUTBOX.LASTERRORCODE, errorCode)
                        .setNull(WRITINGEVENTOUTBOX.LEASETOKEN)
                        .setNull(WRITINGEVENTOUTBOX.LEASEEXPIRESAT)
                        .set(WRITINGEVENTOUTBOX.UPDATEDAT, DatabaseTimestamp.now(clock))
                        .where(
                                WRITINGEVENTOUTBOX.ID.eq(outboxId),
                                WRITINGEVENTOUTBOX.DELIVERYSTATE.eq("delivering"),
                                WRITINGEVENTOUTBOX.LEASETOKEN.eq(leaseToken))
                        .execute()
                == 1;
    }

    @Override
    public boolean supersedeWaitingIfStale(
            String outboxId, String leaseToken, LocalDateTime now) {
        return database.transactionResult(transaction -> {
            WritingeventoutboxRecord row = transaction.selectFrom(WRITINGEVENTOUTBOX)
                    .where(
                            WRITINGEVENTOUTBOX.ID.eq(outboxId),
                            WRITINGEVENTOUTBOX.DELIVERYSTATE.eq("delivering"),
                            WRITINGEVENTOUTBOX.LEASETOKEN.eq(leaseToken))
                    .forUpdate()
                    .fetchOne();
            if (row == null
                    || !"artifact_awaiting_user_approval".equals(row.getEventtype())) {
                return false;
            }
            String phase = transaction.select(WRITINGTASK.PHASE.cast(String.class))
                    .from(WRITINGTASK)
                    .where(WRITINGTASK.ID.eq(row.getTaskid()))
                    .fetchOne(0, String.class);
            Condition differentCommand = row.getCommandid() == null
                    ? WRITINGRUNCOMMAND.ID.isNotNull()
                    : WRITINGRUNCOMMAND.ID.ne(row.getCommandid());
            String laterCommand = transaction.select(WRITINGRUNCOMMAND.ID)
                    .from(WRITINGRUNCOMMAND)
                    .where(
                            WRITINGRUNCOMMAND.TASKID.eq(row.getTaskid()),
                            differentCommand,
                            WRITINGRUNCOMMAND.CREATEDAT.ge(row.getCreatedat()))
                    .orderBy(
                            WRITINGRUNCOMMAND.CREATEDAT.desc(),
                            WRITINGRUNCOMMAND.ID.desc())
                    .limit(1)
                    .fetchOne(WRITINGRUNCOMMAND.ID);
            // 只有任务已终态或存在更新命令时 waiting 才失效；普通发布延迟不能擅自吞掉审核入口。
            if (!Set.of("completed", "error").contains(phase) && laterCommand == null) {
                return false;
            }
            transaction.update(WRITINGEVENTOUTBOX)
                    .set(WRITINGEVENTOUTBOX.DELIVERYSTATE, "superseded")
                    .set(WRITINGEVENTOUTBOX.LASTERRORCODE, "OUTBOX_WAITING_SUPERSEDED")
                    .setNull(WRITINGEVENTOUTBOX.LEASETOKEN)
                    .setNull(WRITINGEVENTOUTBOX.LEASEEXPIRESAT)
                    .set(WRITINGEVENTOUTBOX.UPDATEDAT, now)
                    .where(WRITINGEVENTOUTBOX.ID.eq(outboxId))
                    .execute();
            return true;
        });
    }

    @Override
    public int cleanupTerminal(LocalDateTime olderThan) {
        return database.dsl().deleteFrom(WRITINGEVENTOUTBOX)
                .where(WRITINGEVENTOUTBOX.DELIVERYSTATE
                                .eq("published")
                                .and(WRITINGEVENTOUTBOX.PUBLISHEDAT.isNotNull())
                                .and(WRITINGEVENTOUTBOX.PUBLISHEDAT.lt(olderThan))
                        .or(WRITINGEVENTOUTBOX.DELIVERYSTATE
                                .eq("superseded")
                                .and(WRITINGEVENTOUTBOX.UPDATEDAT.lt(olderThan))))
                .execute();
    }

    @Override
    public WritingOutboxHealth health(
            LocalDateTime now, Duration staleAfter) {
        LocalDateTime staleBefore = now.minus(staleAfter);
        Long blocked = database.dsl().select(count())
                .from(WRITINGEVENTOUTBOX)
                .where(WRITINGEVENTOUTBOX.DELIVERYSTATE.eq("blocked"))
                .fetchOne(0, Long.class);
        Long stale = database.dsl().select(count())
                .from(WRITINGEVENTOUTBOX)
                .where(
                        WRITINGEVENTOUTBOX.DELIVERYSTATE.in("pending", "delivering"),
                        WRITINGEVENTOUTBOX.CREATEDAT.lt(staleBefore))
                .fetchOne(0, Long.class);
        return new WritingOutboxHealth(
                blocked == null ? 0 : blocked,
                stale == null ? 0 : stale);
    }

    @Override
    public Map<String, String> replayDispositions(List<WritingEvent> events) {
        // Redis 里可能仍有旧边界帧，回放前必须用 PostgreSQL 当前投递状态决定 emit/skip/wait。
        List<WritingEvent> boundary = events.stream()
                .filter(event -> BOUNDARY_TYPES.contains(event.event())
                        && event.sourceEventId() != null)
                .toList();
        if (boundary.isEmpty()) {
            Map<String, String> result = new LinkedHashMap<>();
            events.forEach(event -> result.put(event.id(), "emit"));
            return result;
        }
        List<String> sourceIds = boundary.stream()
                .map(WritingEvent::sourceEventId)
                .toList();
        Map<String, String> states = new HashMap<>();
        database.dsl().select(
                        WRITINGEVENTOUTBOX.SOURCEEVENTID,
                        WRITINGEVENTOUTBOX.DELIVERYSTATE)
                .from(WRITINGEVENTOUTBOX)
                .where(WRITINGEVENTOUTBOX.SOURCEEVENTID.in(sourceIds))
                .forEach(row -> states.put(row.value1(), row.value2()));
        Map<String, String> result = new LinkedHashMap<>();
        for (WritingEvent event : events) {
            if (!BOUNDARY_TYPES.contains(event.event()) || event.sourceEventId() == null) {
                result.put(event.id(), "emit");
                continue;
            }
            String state = states.get(event.sourceEventId());
            if (state == null || "published".equals(state)) {
                result.put(event.id(), "emit");
            } else if ("superseded".equals(state)) {
                result.put(event.id(), "skip");
            } else {
                result.put(event.id(), "wait");
            }
        }
        return result;
    }

    private WritingOutboxRecord map(WritingeventoutboxRecord row) {
        Object payload;
        try {
            Object parsed = json.readValue(row.getPayloadjson(), new TypeReference<Object>() {});
            if (parsed instanceof Map<?, ?> value) {
                Map<String, Object> normalized = new LinkedHashMap<>();
                boolean valid = true;
                for (Map.Entry<?, ?> entry : value.entrySet()) {
                    if (!(entry.getKey() instanceof String key)) {
                        valid = false;
                        break;
                    }
                    normalized.put(key, entry.getValue());
                }
                payload = valid
                        ? Collections.unmodifiableMap(normalized)
                        : new Object();
            } else {
                payload = new Object();
            }
        } catch (RuntimeException exception) {
            payload = new Object();
        }
        return new WritingOutboxRecord(
                row.getId(),
                row.getTaskid(),
                row.getCommandid(),
                row.getSourceeventid(),
                row.getSourcesequence(),
                row.getDurablebaseline(),
                row.getDedupekey(),
                row.getEventtype(),
                payload,
                row.getDeliverystate(),
                row.getAttemptcount(),
                row.getNextattemptat(),
                row.getLeasetoken(),
                row.getLeaseexpiresat());
    }
}
