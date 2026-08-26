package cn.inkforge.core.writing.infrastructure;

import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.WRITINGRUNCOMMAND;
import static cn.inkforge.core.db.generated.Tables.WRITINGTASK;

import cn.inkforge.core.db.generated.enums.Writingtaskphase;
import cn.inkforge.core.db.generated.tables.records.WritingruncommandRecord;
import cn.inkforge.core.db.generated.tables.records.WritingtaskRecord;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.writing.application.WritingCommandDispatchRepository;
import cn.inkforge.core.writing.application.WritingCommandPayload;
import cn.inkforge.core.writing.domain.WritingAgentJobStatus;
import cn.inkforge.core.writing.domain.WritingDispatchRecord;
import cn.inkforge.core.writing.domain.WritingTaskFailure;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.jooq.DSLContext;
import org.jooq.Record;
import tools.jackson.databind.ObjectMapper;

/** PostgreSQL 写作命令认领、状态转换和退避重试实现。 */
final class JooqWritingCommandDispatchRepository
        implements WritingCommandDispatchRepository {

    private static final Set<String> TERMINAL = Set.of("succeeded", "failed");

    private final CoreDatabase database;
    private final Clock clock;
    private final ObjectMapper json;

    JooqWritingCommandDispatchRepository(
            CoreDatabase database, Clock clock, ObjectMapper json) {
        this.database = Objects.requireNonNull(database);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
    }

    @Override
    public List<WritingDispatchRecord> claimDue(
            int limit, LocalDateTime activeStaleBefore) {
        if (limit < 1) throw new IllegalArgumentException("命令领取数量必须大于零");
        Objects.requireNonNull(activeStaleBefore);
        LocalDateTime now = DatabaseTimestamp.now(clock);
        return database.transactionResult(transaction -> {
            List<Record> rows = transaction.select(WRITINGRUNCOMMAND.fields())
                    .select(WRITINGTASK.fields())
                    .select(NOVEL.USERID)
                    .from(WRITINGRUNCOMMAND)
                    .join(WRITINGTASK)
                    .on(WRITINGTASK.ID.eq(WRITINGRUNCOMMAND.TASKID))
                    .join(NOVEL)
                    .on(NOVEL.ID.eq(WRITINGTASK.NOVELID))
                    .where(
                            WRITINGRUNCOMMAND.STATUS.eq("pending")
                                    .and(WRITINGRUNCOMMAND.NEXTATTEMPTAT.le(now))
                                    .or(WRITINGRUNCOMMAND.STATUS
                                            .in("submitted", "processing")
                                            .and(WRITINGRUNCOMMAND.UPDATEDAT.le(activeStaleBefore))),
                            NOVEL.USERID.isNotNull())
                    .orderBy(
                            WRITINGRUNCOMMAND.NEXTATTEMPTAT.asc(),
                            WRITINGRUNCOMMAND.CREATEDAT.asc(),
                            WRITINGRUNCOMMAND.ID.asc())
                    .limit(limit)
                    .forUpdate()
                    .of(WRITINGRUNCOMMAND)
                    .skipLocked()
                    .fetch();
            List<WritingDispatchRecord> result = new ArrayList<>(rows.size());
            for (Record row : rows) result.add(dispatchRecord(row));
            return List.copyOf(result);
        });
    }

    @Override
    public WritingDispatchRecord markAgentActive(String commandId) {
        return database.transactionResult(transaction -> {
            WritingruncommandRecord command = lockCommand(transaction, commandId);
            if (!TERMINAL.contains(command.getStatus())) {
                LocalDateTime now = DatabaseTimestamp.now(clock);
                if ("pending".equals(command.getStatus())) {
                    command.setStatus("submitted");
                    if (command.getSubmittedat() == null) command.setSubmittedat(now);
                }
                command.setLasterror(null);
                command.setUpdatedat(now);
                command.update();
            }
            return dispatchRecord(transaction, command);
        });
    }

    @Override
    public WritingDispatchRecord settleDispatchTerminal(
            String commandId, WritingAgentJobStatus agentStatus) {
        if (agentStatus == WritingAgentJobStatus.QUEUED
                || agentStatus == WritingAgentJobStatus.RUNNING) {
            throw new IllegalArgumentException("活动 Agent job 不能按终态收敛");
        }
        return database.transactionResult(transaction -> {
            Locked locked = lockTaskThenCommand(transaction, commandId);
            WritingruncommandRecord command = locked.command();
            WritingtaskRecord task = locked.task();
            if (TERMINAL.contains(command.getStatus())) {
                return dispatchRecord(command, task, locked.userId());
            }
            LocalDateTime now = DatabaseTimestamp.now(clock);
            String code = "AGENT_JOB_TERMINAL_"
                    + agentStatus.value().toUpperCase(Locale.ROOT);
            boolean completed = task.getPhase() == Writingtaskphase.completed;
            command.setStatus(completed ? "succeeded" : "failed");
            command.setCompletedat(now);
            command.setUpdatedat(now);
            command.setLasterror(completed ? null : code);
            if (command.getResultjson() == null) {
                command.setResultjson(json.writeValueAsString(
                        Map.of("code", code, "agentStatus", agentStatus.value())));
            }
            if (task.getPhase() != Writingtaskphase.completed
                    && task.getPhase() != Writingtaskphase.error) {
                WritingTaskFailure.apply(task, code, now, json);
                task.update();
            }
            command.update();
            return dispatchRecord(command, task, locked.userId());
        });
    }

    @Override
    public WritingDispatchRecord settleCancelDispatch(String commandId) {
        return database.transactionResult(transaction -> {
            Locked locked = lockTaskThenCommand(transaction, commandId);
            WritingruncommandRecord command = locked.command();
            WritingtaskRecord task = locked.task();
            WritingCommandPayload.Parsed payload = WritingCommandPayload.parse(
                    command.getKind(), command.getPayloadjson(), json);
            if (!"cancel".equals(payload.logicalKind())) {
                throw new ApiException(
                        409,
                        "WRITING_COMMAND_STATE_CONFLICT",
                        "只有取消命令可以按取消投递收敛");
            }
            if (TERMINAL.contains(command.getStatus())) {
                return dispatchRecord(command, task, locked.userId());
            }
            LocalDateTime now = DatabaseTimestamp.now(clock);
            command.setStatus("succeeded");
            command.setCompletedat(now);
            command.setUpdatedat(now);
            command.setLasterror(null);
            command.setResultjson(json.writeValueAsString(Map.of("effective", true)));
            if (task.getPhase() != Writingtaskphase.completed
                    && task.getPhase() != Writingtaskphase.error) {
                WritingTaskFailure.apply(
                        task, "WRITING_RUN_CANCELLED_BY_USER", now, json);
                task.update();
            }
            command.update();
            return dispatchRecord(command, task, locked.userId());
        });
    }

    @Override
    public WritingDispatchRecord recordDispatchFailure(
            String commandId, String errorCode) {
        return database.transactionResult(transaction -> {
            WritingruncommandRecord command = lockCommand(transaction, commandId);
            if (!TERMINAL.contains(command.getStatus())) {
                int attempts = command.getAttemptcount() + 1;
                long delaySeconds = attempts >= 6 ? 60 : 1L << attempts;
                LocalDateTime now = DatabaseTimestamp.now(clock);
                command.setAttemptcount(attempts);
                command.setNextattemptat(now.plusSeconds(delaySeconds));
                command.setLasterror(limitCode(errorCode));
                command.setUpdatedat(now);
                command.update();
            }
            return dispatchRecord(transaction, command);
        });
    }

    private Locked lockTaskThenCommand(DSLContext transaction, String commandId) {
        String taskId = transaction.select(WRITINGRUNCOMMAND.TASKID)
                .from(WRITINGRUNCOMMAND)
                .where(WRITINGRUNCOMMAND.ID.eq(commandId))
                .fetchOne(WRITINGRUNCOMMAND.TASKID);
        if (taskId == null) throw notFound();
        Record taskRow = transaction.select(WRITINGTASK.fields())
                .select(NOVEL.USERID)
                .from(WRITINGTASK)
                .join(NOVEL)
                .on(NOVEL.ID.eq(WRITINGTASK.NOVELID))
                .where(WRITINGTASK.ID.eq(taskId))
                .forUpdate()
                .of(WRITINGTASK)
                .fetchOne();
        if (taskRow == null) throw notFound();
        WritingruncommandRecord command = lockCommand(transaction, commandId);
        if (!taskId.equals(command.getTaskid())) throw notFound();
        return new Locked(
                taskRow.into(WRITINGTASK).into(WritingtaskRecord.class),
                command,
                taskRow.get(NOVEL.USERID));
    }

    private static WritingruncommandRecord lockCommand(
            DSLContext transaction, String commandId) {
        WritingruncommandRecord command = transaction.selectFrom(WRITINGRUNCOMMAND)
                .where(WRITINGRUNCOMMAND.ID.eq(commandId))
                .forUpdate()
                .fetchOne();
        if (command == null) throw notFound();
        return command;
    }

    private WritingDispatchRecord dispatchRecord(
            DSLContext transaction, WritingruncommandRecord command) {
        Record taskRow = transaction.select(WRITINGTASK.fields())
                .select(NOVEL.USERID)
                .from(WRITINGTASK)
                .join(NOVEL)
                .on(NOVEL.ID.eq(WRITINGTASK.NOVELID))
                .where(WRITINGTASK.ID.eq(command.getTaskid()))
                .fetchOne();
        if (taskRow == null) throw notFound();
        return dispatchRecord(
                command,
                taskRow.into(WRITINGTASK).into(WritingtaskRecord.class),
                taskRow.get(NOVEL.USERID));
    }

    private WritingDispatchRecord dispatchRecord(Record row) {
        return dispatchRecord(
                row.into(WRITINGRUNCOMMAND).into(WritingruncommandRecord.class),
                row.into(WRITINGTASK).into(WritingtaskRecord.class),
                row.get(NOVEL.USERID));
    }

    private WritingDispatchRecord dispatchRecord(
            WritingruncommandRecord command,
            WritingtaskRecord task,
            String userId) {
        WritingCommandPayload.Parsed payload = WritingCommandPayload.parse(
                command.getKind(), command.getPayloadjson(), json);
        return new WritingDispatchRecord(
                command.getId(),
                task.getId(),
                userId,
                task.getNovelid(),
                task.getChapterid(),
                task.getWritingsessionid(),
                task.getPhase().getLiteral(),
                task.getGraphstatejson(),
                payload.logicalKind(),
                payload.job(),
                command.getStatus(),
                command.getAttemptcount(),
                command.getArtifactid(),
                command.getDecision());
    }

    private static String limitCode(String value) {
        String code = value == null || value.isEmpty() ? "RuntimeException" : value;
        int points = code.codePointCount(0, code.length());
        if (points <= 128) return code;
        return code.substring(0, code.offsetByCodePoints(0, 128));
    }

    private static ApiException notFound() {
        return new ApiException(404, "WRITING_COMMAND_NOT_FOUND", "写作命令不存在");
    }

    private record Locked(
            WritingtaskRecord task,
            WritingruncommandRecord command,
            String userId) {}
}
