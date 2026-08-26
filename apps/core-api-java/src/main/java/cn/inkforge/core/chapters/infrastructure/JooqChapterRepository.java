package cn.inkforge.core.chapters.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.CHAPTERPROGRESS;
import static cn.inkforge.core.db.generated.Tables.CHAPTERQUALITYCHECK;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.WORKFLOWRUN;

import cn.inkforge.contracts.api.ChapterStatus;
import cn.inkforge.contracts.api.WorkspaceChapter;
import cn.inkforge.core.chapters.application.ChapterRecord;
import cn.inkforge.core.chapters.application.ChapterRepository;
import cn.inkforge.core.chapters.application.ChapterWorkspaceReadModel;
import cn.inkforge.core.db.generated.enums.Chapterstatus;
import cn.inkforge.core.db.generated.enums.Qualitycheckstatus;
import cn.inkforge.core.db.generated.enums.Qualitychecktype;
import cn.inkforge.core.db.generated.enums.Workflowrunkind;
import cn.inkforge.core.db.generated.enums.Workflowrunstatus;
import cn.inkforge.core.db.generated.tables.records.ChapterprogressRecord;
import cn.inkforge.core.db.generated.tables.records.ChapterqualitycheckRecord;
import cn.inkforge.core.db.generated.tables.records.NovelRecord;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import java.time.Clock;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.jooq.DSLContext;
import org.jooq.Record;
import org.jooq.impl.DSL;

/** PostgreSQL 章节仓储；写路径固定按“章节/小说 → 质量检查”顺序加锁。 */
public final class JooqChapterRepository implements ChapterRepository {

    static final String DEFAULT_QUALITY_TITLE = "一致性终检";
    static final String DEFAULT_QUALITY_SUMMARY =
            "最终检查正文与设定的一致性、角色 OOC、伏笔回收、逻辑矛盾";
    static final String QUALITY_SOURCE_CHANGED = "QUALITY_SOURCE_CHANGED";

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final ChapterWorkspaceReadModel mapper = new ChapterWorkspaceReadModel();

    public JooqChapterRepository(
            CoreDatabase database, CuidV1Generator ids, Clock clock) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
    }

    @Override
    public WorkspaceChapter create(String novelId, String userId) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            NovelRecord novel = requireNovel(transaction, novelId, userId, true);
            Integer currentOrder = transaction.select(DSL.max(CHAPTER.ORDER))
                    .from(CHAPTER)
                    .where(CHAPTER.NOVELID.eq(novel.getId()))
                    .fetchOne(DSL.max(CHAPTER.ORDER));
            int nextOrder = (currentOrder == null ? 0 : currentOrder) + 1;
            LocalDateTime now = DatabaseTimestamp.now(clock);
            cn.inkforge.core.db.generated.tables.records.ChapterRecord chapter = transaction
                    .insertInto(CHAPTER)
                    .set(CHAPTER.ID, ids.next())
                    .set(CHAPTER.NOVELID, novelId)
                    .set(CHAPTER.TITLE, "第 " + nextOrder + " 章")
                    .set(CHAPTER.CONTENT, "")
                    .set(CHAPTER.ORDER, nextOrder)
                    .set(CHAPTER.STATUS, Chapterstatus.drafting)
                    .set(CHAPTER.CREATEDAT, now)
                    .set(CHAPTER.UPDATEDAT, now)
                    .returning()
                    .fetchSingle();
            return mapper.load(transaction, List.of(chapter)).getFirst();
        });
    }

    @Override
    public List<WorkspaceChapter> list(String novelId, String userId) {
        DSLContext context = database.dsl();
        requireNovel(context, novelId, userId, false);
        List<cn.inkforge.core.db.generated.tables.records.ChapterRecord> chapters = context
                .selectFrom(CHAPTER)
                .where(CHAPTER.NOVELID.eq(novelId))
                .orderBy(CHAPTER.ORDER.asc(), CHAPTER.ID.asc())
                .fetch();
        return mapper.load(context, chapters);
    }

    @Override
    public WorkspaceChapter get(String chapterId, String userId) {
        DSLContext context = database.dsl();
        cn.inkforge.core.db.generated.tables.records.ChapterRecord chapter =
                requireChapterOwner(context, chapterId, userId, false);
        return mapper.load(context, List.of(chapter)).getFirst();
    }

    @Override
    public OffsetDateTime updateDraft(
            String chapterId,
            String userId,
            String title,
            String content,
            OffsetDateTime expectedUpdatedAt) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            cn.inkforge.core.db.generated.tables.records.ChapterRecord chapter =
                    requireChapterOwner(transaction, chapterId, userId, true);
            LocalDateTime current = chapter.getUpdatedat();
            if (chapter.getTitle().equals(title) && chapter.getContent().equals(content)) {
                return DatabaseTimestamp.api(current);
            }
            if (chapter.getStatus() != Chapterstatus.drafting) {
                throw new ApiException(
                        409,
                        "CHAPTER_NOT_EDITABLE",
                        "章节退回草稿后才能编辑正文");
            }
            requireChapterVersion(current, expectedUpdatedAt);
            boolean contentChanged = !chapter.getContent().equals(content);
            ChapterqualitycheckRecord check = contentChanged
                    ? lockConsistencyCheck(transaction, chapterId)
                    : null;
            LocalDateTime updatedAt = DatabaseTimestamp.next(clock, current);
            var update = transaction.update(CHAPTER)
                    .set(CHAPTER.TITLE, title)
                    .set(CHAPTER.UPDATEDAT, updatedAt);
            if (contentChanged) {
                update.set(CHAPTER.CONTENT, content);
            }
            update.where(CHAPTER.ID.eq(chapterId)).execute();
            if (contentChanged && check != null) {
                invalidateQuality(transaction, check, DatabaseTimestamp.now(clock));
            }
            return DatabaseTimestamp.api(updatedAt);
        });
    }

    @Override
    public OffsetDateTime upsertProgress(
            String chapterId,
            String userId,
            String content,
            OffsetDateTime expectedUpdatedAt) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            requireChapterOwner(transaction, chapterId, userId, true);
            ChapterprogressRecord progress = transaction.selectFrom(CHAPTERPROGRESS)
                    .where(CHAPTERPROGRESS.CHAPTERID.eq(chapterId))
                    .forUpdate()
                    .fetchOne();
            if (progress == null) {
                requireProgressVersion(null, expectedUpdatedAt);
                LocalDateTime now = DatabaseTimestamp.now(clock);
                transaction.insertInto(CHAPTERPROGRESS)
                        .set(CHAPTERPROGRESS.ID, ids.next())
                        .set(CHAPTERPROGRESS.CHAPTERID, chapterId)
                        .set(CHAPTERPROGRESS.CONTENT, content)
                        .set(CHAPTERPROGRESS.CREATEDAT, now)
                        .set(CHAPTERPROGRESS.UPDATEDAT, now)
                        .execute();
                return DatabaseTimestamp.api(now);
            }
            LocalDateTime current = progress.getUpdatedat();
            if (progress.getContent().equals(content)) {
                return DatabaseTimestamp.api(current);
            }
            requireProgressVersion(current, expectedUpdatedAt);
            LocalDateTime updatedAt = DatabaseTimestamp.next(clock, current);
            transaction.update(CHAPTERPROGRESS)
                    .set(CHAPTERPROGRESS.CONTENT, content)
                    .set(CHAPTERPROGRESS.UPDATEDAT, updatedAt)
                    .where(CHAPTERPROGRESS.ID.eq(progress.getId()))
                    .execute();
            return DatabaseTimestamp.api(updatedAt);
        });
    }

    @Override
    public ChapterRecord transitionStatus(
            String chapterId,
            String userId,
            ChapterStatus target,
            OffsetDateTime expectedUpdatedAt) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            cn.inkforge.core.db.generated.tables.records.ChapterRecord chapter =
                    requireChapterOwner(transaction, chapterId, userId, true);
            LocalDateTime current = chapter.getUpdatedat();
            requireChapterVersion(current, expectedUpdatedAt);
            Chapterstatus targetStatus = Chapterstatus.lookupLiteral(target.getValue());
            if (chapter.getStatus() == Chapterstatus.drafting
                    && targetStatus == Chapterstatus.completed) {
                throw new ApiException(
                        409,
                        "INVALID_CHAPTER_STATUS_TRANSITION",
                        "章节状态不能这样切换");
            }

            ChapterqualitycheckRecord check = lockConsistencyCheck(transaction, chapterId);
            if (targetStatus == Chapterstatus.completed && !handled(check)) {
                throw new ApiException(
                        409,
                        "QUALITY_CHECK_REQUIRED",
                        "一致性终检完成或跳过后，才能标记章节完成");
            }
            LocalDateTime now = DatabaseTimestamp.now(clock);
            if (targetStatus == Chapterstatus.review) {
                repairReviewCheck(transaction, chapter, check, now);
            }

            LocalDateTime completedAt = targetStatus == Chapterstatus.completed
                    ? (chapter.getCompletedat() == null ? now : chapter.getCompletedat())
                    : null;
            boolean changed = chapter.getStatus() != targetStatus
                    || !Objects.equals(chapter.getCompletedat(), completedAt);
            LocalDateTime updatedAt = current;
            if (changed) {
                updatedAt = DatabaseTimestamp.next(clock, current);
                transaction.update(CHAPTER)
                        .set(CHAPTER.STATUS, targetStatus)
                        .set(CHAPTER.COMPLETEDAT, completedAt)
                        .set(CHAPTER.UPDATEDAT, updatedAt)
                        .where(CHAPTER.ID.eq(chapterId))
                        .execute();
            }
            return new ChapterRecord(
                    chapterId,
                    chapter.getNovelid(),
                    target,
                    DatabaseTimestamp.api(completedAt),
                    DatabaseTimestamp.api(updatedAt));
        });
    }

    private void repairReviewCheck(
            DSLContext transaction,
            cn.inkforge.core.db.generated.tables.records.ChapterRecord chapter,
            ChapterqualitycheckRecord check,
            LocalDateTime now) {
        if (check == null) {
            transaction.insertInto(CHAPTERQUALITYCHECK)
                    .set(CHAPTERQUALITYCHECK.ID, ids.next())
                    .set(CHAPTERQUALITYCHECK.CHAPTERID, chapter.getId())
                    .set(CHAPTERQUALITYCHECK.TYPE, Qualitychecktype.consistency)
                    .set(CHAPTERQUALITYCHECK.STATUS, Qualitycheckstatus.pending)
                    .set(CHAPTERQUALITYCHECK.TITLE, DEFAULT_QUALITY_TITLE)
                    .set(CHAPTERQUALITYCHECK.SUMMARY, DEFAULT_QUALITY_SUMMARY)
                    .set(CHAPTERQUALITYCHECK.CREATEDAT, now)
                    .set(CHAPTERQUALITYCHECK.UPDATEDAT, now)
                    .execute();
            return;
        }
        boolean sourceChanged = chapter.getStatus() != Chapterstatus.review;
        boolean metadataChanged = !DEFAULT_QUALITY_TITLE.equals(check.getTitle())
                || !DEFAULT_QUALITY_SUMMARY.equals(check.getSummary());
        if (sourceChanged) {
            invalidateQuality(transaction, check, now);
        }
        if (sourceChanged || metadataChanged) {
            transaction.update(CHAPTERQUALITYCHECK)
                    .set(CHAPTERQUALITYCHECK.TITLE, DEFAULT_QUALITY_TITLE)
                    .set(CHAPTERQUALITYCHECK.SUMMARY, DEFAULT_QUALITY_SUMMARY)
                    .set(CHAPTERQUALITYCHECK.UPDATEDAT, now)
                    .where(CHAPTERQUALITYCHECK.ID.eq(check.getId()))
                    .execute();
        }
    }

    private static void invalidateQuality(
            DSLContext transaction, ChapterqualitycheckRecord check, LocalDateTime now) {
        transaction.update(CHAPTERQUALITYCHECK)
                .set(CHAPTERQUALITYCHECK.STATUS, Qualitycheckstatus.pending)
                .setNull(CHAPTERQUALITYCHECK.RESULT)
                .setNull(CHAPTERQUALITYCHECK.SCOREHOOK)
                .setNull(CHAPTERQUALITYCHECK.SCORETENSION)
                .setNull(CHAPTERQUALITYCHECK.SCOREPAYOFF)
                .setNull(CHAPTERQUALITYCHECK.SCOREPACING)
                .setNull(CHAPTERQUALITYCHECK.SCOREENDINGHOOK)
                .setNull(CHAPTERQUALITYCHECK.SCOREREADERPROMISE)
                .setNull(CHAPTERQUALITYCHECK.SCOREOVERALL)
                .setNull(CHAPTERQUALITYCHECK.QUALITYGATE)
                .setNull(CHAPTERQUALITYCHECK.REWRITEBRIEF)
                .set(CHAPTERQUALITYCHECK.UPDATEDAT, now)
                .where(CHAPTERQUALITYCHECK.ID.eq(check.getId()))
                .execute();
        transaction.update(WORKFLOWRUN)
                .set(WORKFLOWRUN.STATUS, Workflowrunstatus.cancelled)
                .set(WORKFLOWRUN.ERRORMESSAGE, QUALITY_SOURCE_CHANGED)
                .set(WORKFLOWRUN.UPDATEDAT, now)
                .where(
                        WORKFLOWRUN.KIND.eq(Workflowrunkind.quality_check),
                        WORKFLOWRUN.SOURCEID.eq(check.getId()),
                        WORKFLOWRUN.STATUS.in(
                                Workflowrunstatus.pending, Workflowrunstatus.running))
                .execute();
    }

    private static boolean handled(ChapterqualitycheckRecord check) {
        if (check == null) {
            return false;
        }
        if (check.getStatus() == Qualitycheckstatus.skipped) {
            return true;
        }
        return check.getStatus() == Qualitycheckstatus.completed
                && check.getResult() != null
                && !check.getResult().strip().isEmpty()
                && check.getScoreoverall() != null
                && ("pass".equals(check.getQualitygate())
                        || "revise".equals(check.getQualitygate()));
    }

    private static ChapterqualitycheckRecord lockConsistencyCheck(
            DSLContext transaction, String chapterId) {
        return transaction.selectFrom(CHAPTERQUALITYCHECK)
                .where(
                        CHAPTERQUALITYCHECK.CHAPTERID.eq(chapterId),
                        CHAPTERQUALITYCHECK.TYPE.eq(Qualitychecktype.consistency))
                .forUpdate()
                .fetchOne();
    }

    private static NovelRecord requireNovel(
            DSLContext context, String novelId, String userId, boolean lock) {
        var query = context.selectFrom(NOVEL).where(NOVEL.ID.eq(novelId));
        NovelRecord novel = lock ? query.forUpdate().fetchOne() : query.fetchOne();
        if (novel == null) {
            throw new ApiException(404, "NOVEL_NOT_FOUND", "小说不存在");
        }
        if (novel.getUserid() == null || !novel.getUserid().equals(userId)) {
            throw new ApiException(403, "NOVEL_FORBIDDEN", "无权访问该小说");
        }
        return novel;
    }

    private static cn.inkforge.core.db.generated.tables.records.ChapterRecord
            requireChapterOwner(
                    DSLContext context, String chapterId, String userId, boolean lock) {
        var query = context.select(CHAPTER.fields())
                .select(NOVEL.USERID)
                .from(CHAPTER)
                .join(NOVEL)
                .on(NOVEL.ID.eq(CHAPTER.NOVELID))
                .where(CHAPTER.ID.eq(chapterId));
        Record row = lock
                ? query.forUpdate().of(CHAPTER).fetchOne()
                : query.fetchOne();
        if (row == null) {
            throw new ApiException(404, "CHAPTER_NOT_FOUND", "章节不存在");
        }
        String ownerId = row.get(NOVEL.USERID);
        if (ownerId == null || !ownerId.equals(userId)) {
            throw new ApiException(403, "CHAPTER_FORBIDDEN", "无权访问该章节");
        }
        return row.into(CHAPTER);
    }

    private static void requireChapterVersion(
            LocalDateTime current, OffsetDateTime expected) {
        if (!DatabaseTimestamp.sameInstant(current, expected)) {
            throw new ApiException(
                    409,
                    "CHAPTER_VERSION_CONFLICT",
                    "章节已在其他位置更新，请保留当前草稿并重新加载",
                    Map.of("currentUpdatedAt", DatabaseTimestamp.api(current)));
        }
    }

    private static void requireProgressVersion(
            LocalDateTime current, OffsetDateTime expected) {
        if (!DatabaseTimestamp.sameInstant(current, expected)) {
            throw new ApiException(
                    409,
                    "CHAPTER_PROGRESS_VERSION_CONFLICT",
                    "章节进展已在其他位置更新，请保留当前草稿并重新加载",
                    java.util.Collections.singletonMap(
                            "currentUpdatedAt", DatabaseTimestamp.api(current)));
        }
    }
}
