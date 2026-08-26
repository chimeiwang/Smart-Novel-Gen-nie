package cn.inkforge.core.novels.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;

import cn.inkforge.contracts.api.ApprovedBeatPlanSummary;
import cn.inkforge.contracts.api.ChapterStatus;
import cn.inkforge.contracts.api.WorkspaceChapter;
import cn.inkforge.contracts.api.WorkspaceChapterSummary;
import cn.inkforge.core.chapters.application.ChapterWorkspaceReadModel;
import cn.inkforge.core.db.generated.enums.Chapterstatus;
import cn.inkforge.core.db.generated.tables.records.ChapterRecord;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import java.util.List;
import java.util.Map;
import org.jooq.DSLContext;
import org.jooq.Field;
import org.jooq.Record;
import org.jooq.impl.DSL;

/** 工作区章节读取器；启动页不预取非当前章节正文，完整工作区批量加载全部详情。 */
final class WorkspaceChapterReader {

    private static final String IGNORED_TEXT_CHARACTERS = new String(
            new int[] {
                0x0009, 0x000A, 0x000B, 0x000C, 0x000D, 0x0020, 0x0085, 0x00A0,
                0x1680, 0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006,
                0x2007, 0x2008, 0x2009, 0x200A, 0x2028, 0x2029, 0x202F, 0x205F,
                0x3000, 0xFEFF
            },
            0,
            26);

    private final ChapterWorkspaceReadModel details = new ChapterWorkspaceReadModel();

    FullChapters full(DSLContext context, String novelId, String requestedChapterId) {
        List<ChapterRecord> chapters = context.selectFrom(CHAPTER)
                .where(CHAPTER.NOVELID.eq(novelId))
                .orderBy(CHAPTER.ORDER.asc(), CHAPTER.ID.asc())
                .fetch();
        String currentId = selectCurrent(
                chapters.stream().map(ChapterMeta::from).toList(), requestedChapterId);
        return new FullChapters(details.load(context, chapters), currentId);
    }

    BootstrapChapters bootstrap(
            DSLContext context, String novelId, String requestedChapterId) {
        Field<Integer> wordCount = DSL.length(DSL.translate(
                        CHAPTER.CONTENT,
                        DSL.inline(IGNORED_TEXT_CHARACTERS),
                        DSL.inline("")))
                .as("wordCount");
        List<ChapterMeta> metadata = context.select(
                        CHAPTER.ID,
                        CHAPTER.TITLE,
                        CHAPTER.ORDER,
                        CHAPTER.STATUS,
                        CHAPTER.UPDATEDAT,
                        wordCount)
                .from(CHAPTER)
                .where(CHAPTER.NOVELID.eq(novelId))
                .orderBy(CHAPTER.ORDER.asc(), CHAPTER.ID.asc())
                .fetch(row -> ChapterMeta.from(row, wordCount));
        String currentId = selectCurrent(metadata, requestedChapterId);
        WorkspaceChapter current = null;
        if (currentId != null) {
            ChapterRecord currentRecord = context.selectFrom(CHAPTER)
                    .where(CHAPTER.ID.eq(currentId).and(CHAPTER.NOVELID.eq(novelId)))
                    .fetchOne();
            if (currentRecord != null) {
                current = details.load(context, List.of(currentRecord)).getFirst();
            }
        }
        Map<String, ApprovedBeatPlanSummary> plans = details.approvedPlanSummaries(
                context, metadata.stream().map(ChapterMeta::id).toList());
        List<WorkspaceChapterSummary> summaries = metadata.stream()
                .map(value -> value.summary(plans.get(value.id())))
                .toList();
        return new BootstrapChapters(summaries, current, currentId);
    }

    private static String selectCurrent(
            List<ChapterMeta> chapters, String requestedChapterId) {
        if (requestedChapterId != null
                && chapters.stream().anyMatch(value -> value.id().equals(requestedChapterId))) {
            return requestedChapterId;
        }
        for (int index = chapters.size() - 1; index >= 0; index--) {
            if (chapters.get(index).status() == Chapterstatus.drafting) {
                return chapters.get(index).id();
            }
        }
        return chapters.isEmpty() ? null : chapters.getLast().id();
    }

    record FullChapters(List<WorkspaceChapter> chapters, String currentChapterId) {}

    record BootstrapChapters(
            List<WorkspaceChapterSummary> chapters,
            WorkspaceChapter currentChapter,
            String currentChapterId) {}

    private record ChapterMeta(
            String id,
            String title,
            int order,
            Chapterstatus status,
            java.time.LocalDateTime updatedAt,
            int wordCount) {

        static ChapterMeta from(ChapterRecord record) {
            return new ChapterMeta(
                    record.getId(),
                    record.getTitle(),
                    record.getOrder(),
                    record.getStatus(),
                    record.getUpdatedat(),
                    0);
        }

        static ChapterMeta from(Record record, Field<Integer> wordCount) {
            Integer count = record.get(wordCount);
            return new ChapterMeta(
                    record.get(CHAPTER.ID),
                    record.get(CHAPTER.TITLE),
                    record.get(CHAPTER.ORDER),
                    record.get(CHAPTER.STATUS),
                    record.get(CHAPTER.UPDATEDAT),
                    count == null ? 0 : count);
        }

        WorkspaceChapterSummary summary(ApprovedBeatPlanSummary plan) {
            return new WorkspaceChapterSummary(
                    plan,
                    id,
                    order,
                    ChapterStatus.fromValue(status.getLiteral()),
                    title,
                    DatabaseTimestamp.api(updatedAt),
                    wordCount);
        }
    }
}
