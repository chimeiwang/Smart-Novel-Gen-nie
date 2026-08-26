package cn.inkforge.core.writing.infrastructure;

import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACT;
import static cn.inkforge.core.db.generated.Tables.WRITINGRUNCOMMAND;
import static cn.inkforge.core.db.generated.Tables.WRITINGTASK;

import cn.inkforge.contracts.api.WritingRunListItem;
import cn.inkforge.contracts.api.WritingRunListResponse;
import cn.inkforge.contracts.api.WritingRunStatusResponse;
import cn.inkforge.core.db.generated.tables.records.ReviewartifactRecord;
import cn.inkforge.core.db.generated.tables.records.WritingruncommandRecord;
import cn.inkforge.core.db.generated.tables.records.WritingtaskRecord;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.writing.application.WritingRunQueryRepository;
import cn.inkforge.core.writing.domain.WritingRunCursor;
import cn.inkforge.core.writing.domain.WritingRunStatusProjector;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.jooq.Condition;
import org.jooq.DSLContext;
import org.jooq.impl.DSL;

/** 使用批量关联读取避免 N+1，并在内存中应用依赖统一结果投影的过滤条件。 */
final class JooqWritingRunQueryRepository implements WritingRunQueryRepository {

    private static final int SCAN_BATCH_SIZE = 200;
    private static final Set<String> OPERATIONS = Set.of(
            "generate_outline",
            "generate_manuscript",
            "replace_selection",
            "full_check",
            "plan_chapter",
            "rewrite_scene",
            "rewrite_chapter_selection",
            "rewrite_outline_selection",
            "write_chapter",
            "review_chapter");
    private static final Set<String> OUTCOMES = Set.of(
            "queued", "running", "waiting_user", "succeeded", "failed", "cancelled", "inconsistent");

    private final CoreDatabase database;
    private final WritingRunStatusProjector projector;
    private final WritingRunCursor cursors;

    JooqWritingRunQueryRepository(
            CoreDatabase database,
            WritingRunStatusProjector projector,
            WritingRunCursor cursors) {
        this.database = Objects.requireNonNull(database);
        this.projector = Objects.requireNonNull(projector);
        this.cursors = Objects.requireNonNull(cursors);
    }

    @Override
    public WritingRunStatusResponse get(String userId, String taskId) {
        DSLContext context = database.dsl();
        WritingtaskRecord task = context.select(WRITINGTASK.fields())
                .from(WRITINGTASK)
                .join(NOVEL)
                .on(NOVEL.ID.eq(WRITINGTASK.NOVELID))
                .where(WRITINGTASK.ID.eq(taskId), NOVEL.USERID.eq(userId))
                .fetchOneInto(WritingtaskRecord.class);
        if (task == null) {
            throw new ApiException(403, "WRITING_TASK_FORBIDDEN", "无权访问该写作任务");
        }
        return projector.project(task, commands(context, List.of(taskId)), artifacts(context, List.of(taskId)));
    }

    @Override
    public WritingRunListResponse list(
            String userId,
            String novelId,
            String chapterId,
            String writingSessionId,
            String operation,
            String outcome,
            String cursor,
            int limit) {
        if (operation != null && !OPERATIONS.contains(operation)) {
            throw new ApiException(422, "VALIDATION_ERROR", "任务 operation 过滤值无效");
        }
        if (outcome != null && !OUTCOMES.contains(outcome)) {
            throw new ApiException(422, "VALIDATION_ERROR", "任务 outcome 过滤值无效");
        }
        WritingRunCursor.Position initial = decode(cursor);
        WritingRunCursor.Position scan = initial;
        List<WritingRunListItem> matched = new ArrayList<>();
        DSLContext context = database.dsl();
        while (matched.size() < limit + 1) {
            Condition condition = NOVEL.USERID.eq(userId).and(WRITINGTASK.NOVELID.eq(novelId));
            if (chapterId != null) condition = condition.and(WRITINGTASK.CHAPTERID.eq(chapterId));
            if (writingSessionId != null) {
                condition = condition.and(WRITINGTASK.WRITINGSESSIONID.eq(writingSessionId));
            }
            if (scan != null) {
                LocalDateTime createdAt = DatabaseTimestamp.database(scan.createdAt());
                condition = condition.and(WRITINGTASK.CREATEDAT.lt(createdAt)
                        .or(WRITINGTASK.CREATEDAT.eq(createdAt)
                                .and(WRITINGTASK.ID.lt(scan.taskId()))));
            }
            List<WritingtaskRecord> tasks = context.select(WRITINGTASK.fields())
                    .from(WRITINGTASK)
                    .join(NOVEL)
                    .on(NOVEL.ID.eq(WRITINGTASK.NOVELID))
                    .where(condition)
                    .orderBy(WRITINGTASK.CREATEDAT.desc(), WRITINGTASK.ID.desc())
                    .limit(SCAN_BATCH_SIZE)
                    .fetchInto(WritingtaskRecord.class);
            if (tasks.isEmpty()) break;
            List<String> taskIds = tasks.stream().map(WritingtaskRecord::getId).toList();
            Map<String, List<WritingruncommandRecord>> commands = groupCommands(
                    commands(context, taskIds));
            Map<String, List<ReviewartifactRecord>> artifacts = groupArtifacts(
                    artifacts(context, taskIds));
            for (WritingtaskRecord task : tasks) {
                WritingRunStatusResponse status = projector.project(
                        task,
                        commands.getOrDefault(task.getId(), List.of()),
                        artifacts.getOrDefault(task.getId(), List.of()));
                String statusOperation = status.getOperation() == null
                        ? null
                        : status.getOperation().getValue();
                if (operation != null && !operation.equals(statusOperation)) continue;
                if (outcome != null && !outcome.equals(status.getOutcome().getState().getValue())) {
                    continue;
                }
                matched.add(listItem(status));
                if (matched.size() == limit + 1) break;
            }
            WritingtaskRecord last = tasks.getLast();
            scan = new WritingRunCursor.Position(
                    DatabaseTimestamp.api(last.getCreatedat()), last.getId());
            if (tasks.size() < SCAN_BATCH_SIZE) break;
        }
        List<WritingRunListItem> page = matched.size() <= limit
                ? List.copyOf(matched)
                : List.copyOf(matched.subList(0, limit));
        String next = matched.size() > limit && !page.isEmpty()
                ? cursors.encode(page.getLast().getCreatedAt(), page.getLast().getTaskId())
                : null;
        return new WritingRunListResponse(page, next);
    }

    private WritingRunCursor.Position decode(String cursor) {
        if (cursor == null) return null;
        try {
            return cursors.decode(cursor);
        } catch (IllegalArgumentException exception) {
            throw new ApiException(422, "WRITING_RUN_CURSOR_INVALID", "任务游标无效");
        }
    }

    private static List<WritingruncommandRecord> commands(
            DSLContext context, List<String> taskIds) {
        if (taskIds.isEmpty()) return List.of();
        return context.selectFrom(WRITINGRUNCOMMAND)
                .where(WRITINGRUNCOMMAND.TASKID.in(taskIds))
                .orderBy(
                        WRITINGRUNCOMMAND.TASKID.asc(),
                        WRITINGRUNCOMMAND.CREATEDAT.desc(),
                        WRITINGRUNCOMMAND.ID.desc())
                .fetch();
    }

    private static List<ReviewartifactRecord> artifacts(
            DSLContext context, List<String> taskIds) {
        if (taskIds.isEmpty()) return List.of();
        return context.selectFrom(REVIEWARTIFACT)
                .where(REVIEWARTIFACT.TASKID.in(taskIds))
                .orderBy(
                        REVIEWARTIFACT.TASKID.asc(),
                        REVIEWARTIFACT.CREATEDAT.desc(),
                        REVIEWARTIFACT.ID.desc())
                .fetch();
    }

    private static Map<String, List<WritingruncommandRecord>> groupCommands(
            List<WritingruncommandRecord> values) {
        Map<String, List<WritingruncommandRecord>> result = new LinkedHashMap<>();
        for (WritingruncommandRecord value : values) {
            result.computeIfAbsent(value.getTaskid(), ignored -> new ArrayList<>()).add(value);
        }
        return result;
    }

    private static Map<String, List<ReviewartifactRecord>> groupArtifacts(
            List<ReviewartifactRecord> values) {
        Map<String, List<ReviewartifactRecord>> result = new LinkedHashMap<>();
        for (ReviewartifactRecord value : values) {
            if (value.getTaskid() != null) {
                result.computeIfAbsent(value.getTaskid(), ignored -> new ArrayList<>()).add(value);
            }
        }
        return result;
    }

    private static WritingRunListItem listItem(WritingRunStatusResponse status) {
        if (status.getCreatedAt() == null || status.getTarget() == null || status.getScope() == null) {
            throw new IllegalStateException("统一任务投影缺少列表必需字段");
        }
        return new WritingRunListItem(
                status.getActiveArtifactId(),
                status.getChapterId(),
                status.getCreatedAt(),
                status.getNovelId(),
                status.getOperation() == null ? null : status.getOperation().getValue(),
                status.getOutcome(),
                status.getPhase(),
                status.getRecoverable(),
                status.getScope(),
                status.getTarget(),
                status.getTaskId(),
                status.getUpdatedAt(),
                WritingRunListItem.WorkflowEnum.fromValue(status.getWorkflow().getValue()),
                status.getWritingSessionId());
    }
}
