package cn.inkforge.core.writing.infrastructure;

import static cn.inkforge.core.db.generated.Tables.WRITINGEVENTOUTBOX;

import cn.inkforge.core.db.generated.tables.records.WritingeventoutboxRecord;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.writing.domain.WritingBoundaryEvent;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.Objects;
import org.jooq.DSLContext;
import tools.jackson.databind.ObjectMapper;

/** 在调用方既有事务内幂等登记边界事件。 */
final class WritingBoundaryOutboxRegistrar {

    private final CuidV1Generator ids;
    private final Clock clock;
    private final ObjectMapper json;

    WritingBoundaryOutboxRegistrar(
            CuidV1Generator ids, Clock clock, ObjectMapper json) {
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
    }

    Registration register(
            DSLContext transaction,
            String taskId,
            String commandId,
            WritingBoundaryEvent boundary,
            Integer durableBaseline) {
        if (boundary == null) return new Registration(null, false);
        String payloadJson = new String(
                CommandIdempotency.canonicalJsonBytes(boundary.payload(), json),
                StandardCharsets.UTF_8);
        WritingeventoutboxRecord existing = transaction.selectFrom(WRITINGEVENTOUTBOX)
                .where(
                        WRITINGEVENTOUTBOX.SOURCEEVENTID.eq(boundary.sourceEventId())
                                .or(WRITINGEVENTOUTBOX.DEDUPEKEY.eq(boundary.dedupeKey()))
                                .or(WRITINGEVENTOUTBOX.TASKID
                                        .eq(taskId)
                                        .and(WRITINGEVENTOUTBOX.SOURCESEQUENCE
                                                .eq(boundary.sourceSequence()))))
                .forUpdate()
                .fetchOne();
        if (existing != null) {
            boolean same = Objects.equals(existing.getTaskid(), taskId)
                    && Objects.equals(existing.getCommandid(), commandId)
                    && Objects.equals(existing.getSourceeventid(), boundary.sourceEventId())
                    && existing.getSourcesequence() == boundary.sourceSequence()
                    && (durableBaseline == null
                            || Objects.equals(existing.getDurablebaseline(), durableBaseline))
                    && Objects.equals(existing.getDedupekey(), boundary.dedupeKey())
                    && Objects.equals(existing.getEventtype(), boundary.eventType())
                    && Objects.equals(existing.getPayloadjson(), payloadJson);
            return new Registration(same ? existing.getId() : null, !same);
        }
        if (durableBaseline == null
                || durableBaseline < 0
                || durableBaseline >= boundary.sourceSequence()) {
            return new Registration(null, true);
        }
        LocalDateTime now = DatabaseTimestamp.now(clock);
        String id = ids.next();
        transaction.insertInto(WRITINGEVENTOUTBOX)
                .set(WRITINGEVENTOUTBOX.ID, id)
                .set(WRITINGEVENTOUTBOX.TASKID, taskId)
                .set(WRITINGEVENTOUTBOX.COMMANDID, commandId)
                .set(WRITINGEVENTOUTBOX.SOURCEEVENTID, boundary.sourceEventId())
                .set(WRITINGEVENTOUTBOX.SOURCESEQUENCE, boundary.sourceSequence())
                .set(WRITINGEVENTOUTBOX.DURABLEBASELINE, durableBaseline)
                .set(WRITINGEVENTOUTBOX.DEDUPEKEY, boundary.dedupeKey())
                .set(WRITINGEVENTOUTBOX.EVENTTYPE, boundary.eventType())
                .set(WRITINGEVENTOUTBOX.PAYLOADJSON, payloadJson)
                .set(WRITINGEVENTOUTBOX.DELIVERYSTATE, "pending")
                .set(WRITINGEVENTOUTBOX.ATTEMPTCOUNT, 0)
                .set(WRITINGEVENTOUTBOX.NEXTATTEMPTAT, now)
                .set(WRITINGEVENTOUTBOX.CREATEDAT, now)
                .set(WRITINGEVENTOUTBOX.UPDATEDAT, now)
                .execute();
        return new Registration(id, false);
    }

    record Registration(String outboxId, boolean conflict) {}
}
