package cn.inkforge.core.novels.infrastructure;

import static cn.inkforge.core.db.generated.Tables.OUTLINE;
import static cn.inkforge.core.db.generated.Tables.OUTLINENODE;
import static cn.inkforge.core.db.generated.Tables.PLOTPROGRESS;
import static cn.inkforge.core.db.generated.Tables.STORYBACKGROUND;
import static cn.inkforge.core.db.generated.Tables.WORLDSETTING;
import static cn.inkforge.core.db.generated.Tables.WRITINGBIBLE;

import cn.inkforge.contracts.api.ContentDto;
import cn.inkforge.contracts.api.OutlineNodeDto;
import cn.inkforge.contracts.api.OutlineNodeKind;
import cn.inkforge.contracts.api.OutlineNodeStatus;
import cn.inkforge.contracts.api.PlotProgressDto;
import cn.inkforge.contracts.api.StoryLengthProfile;
import cn.inkforge.contracts.api.WorkspacePlanningResponse;
import cn.inkforge.contracts.api.WritingBibleDto;
import cn.inkforge.core.db.generated.tables.records.NovelRecord;
import cn.inkforge.core.db.generated.tables.records.OutlineRecord;
import cn.inkforge.core.db.generated.tables.records.OutlinenodeRecord;
import cn.inkforge.core.db.generated.tables.records.PlotprogressRecord;
import cn.inkforge.core.db.generated.tables.records.StorybackgroundRecord;
import cn.inkforge.core.db.generated.tables.records.WorldsettingRecord;
import cn.inkforge.core.db.generated.tables.records.WritingbibleRecord;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import java.time.LocalDateTime;
import java.util.List;
import org.jooq.DSLContext;

/** 规划分组读取器；正文故事进展与结构化规划保持各自数据层。 */
final class WorkspacePlanningReader {

    WorkspacePlanningResponse read(DSLContext context, NovelRecord novel) {
        String novelId = novel.getId();
        StorybackgroundRecord background = context.selectFrom(STORYBACKGROUND)
                .where(STORYBACKGROUND.NOVELID.eq(novelId))
                .fetchOne();
        WorldsettingRecord world = context.selectFrom(WORLDSETTING)
                .where(WORLDSETTING.NOVELID.eq(novelId))
                .fetchOne();
        WritingbibleRecord bible = context.selectFrom(WRITINGBIBLE)
                .where(WRITINGBIBLE.NOVELID.eq(novelId))
                .fetchOne();
        OutlineRecord outline = context.selectFrom(OUTLINE)
                .where(OUTLINE.NOVELID.eq(novelId))
                .fetchOne();
        List<OutlinenodeRecord> nodes = context.selectFrom(OUTLINENODE)
                .where(OUTLINENODE.NOVELID.eq(novelId))
                .orderBy(OUTLINENODE.ORDER.asc(), OUTLINENODE.TITLE.asc(), OUTLINENODE.ID.asc())
                .fetch();
        PlotprogressRecord plot = context.selectFrom(PLOTPROGRESS)
                .where(PLOTPROGRESS.NOVELID.eq(novelId))
                .fetchOne();

        WorkspacePlanningResponse result = new WorkspacePlanningResponse();
        result.setStoryProgress(novel.getStoryprogress());
        result.setStoryProgressUpdatedAt(DatabaseTimestamp.api(novel.getUpdatedat()));
        result.setStoryBackground(background == null
                ? null
                : content(
                        background.getId(),
                        background.getContent(),
                        background.getCreatedat(),
                        background.getUpdatedat()));
        result.setWorldSetting(world == null
                ? null
                : content(
                        world.getId(),
                        world.getContent(),
                        world.getCreatedat(),
                        world.getUpdatedat()));
        result.setWritingBible(bible == null ? null : bible(bible));
        result.setOutline(outline == null
                ? null
                : content(
                        outline.getId(),
                        outline.getContent(),
                        outline.getCreatedat(),
                        outline.getUpdatedat()));
        result.setOutlineNodes(nodes.stream()
                .map(WorkspacePlanningReader::node)
                .toList());
        result.setPlotProgress(plot == null ? null : plot(plot));
        return result;
    }

    private static ContentDto content(
            String id, String content, LocalDateTime createdAt, LocalDateTime updatedAt) {
        return new ContentDto(
                content,
                DatabaseTimestamp.api(createdAt),
                id,
                DatabaseTimestamp.api(updatedAt));
    }

    private static WritingBibleDto bible(WritingbibleRecord value) {
        return new WritingBibleDto(
                value.getAppealmodel(),
                value.getComparabletitles(),
                value.getCoresellingpoint(),
                DatabaseTimestamp.api(value.getCreatedat()),
                value.getGenre(),
                value.getId(),
                value.getNotes(),
                value.getReaderpromise(),
                StoryLengthProfile.fromValue(value.getStorylengthprofile().getLiteral()),
                value.getTaboo(),
                value.getTargetreaders(),
                value.getTargettotalwordcount(),
                DatabaseTimestamp.api(value.getUpdatedat()));
    }

    private static OutlineNodeDto node(OutlinenodeRecord value) {
        return new OutlineNodeDto(
                value.getActualwordcount(),
                value.getChapterendorder(),
                value.getChapterstartorder(),
                value.getContent(),
                DatabaseTimestamp.api(value.getCreatedat()),
                value.getEstimatedwordcount(),
                value.getId(),
                OutlineNodeKind.fromValue(value.getKind().getLiteral()),
                value.getLinkedchapterid(),
                value.getOrder(),
                value.getParentid(),
                OutlineNodeStatus.fromValue(value.getStatus().getLiteral()),
                value.getTitle(),
                DatabaseTimestamp.api(value.getUpdatedat()));
    }

    private static PlotProgressDto plot(PlotprogressRecord value) {
        return new PlotProgressDto(
                value.getCurrentconflict(),
                value.getCurrentgoal(),
                value.getCurrentstage(),
                value.getId(),
                value.getNextmilestone(),
                DatabaseTimestamp.api(value.getUpdatedat()));
    }
}
