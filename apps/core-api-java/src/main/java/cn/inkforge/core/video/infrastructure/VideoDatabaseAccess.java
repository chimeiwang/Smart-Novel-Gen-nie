package cn.inkforge.core.video.infrastructure;

import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.VIDEOASSET;
import static cn.inkforge.core.db.generated.Tables.VIDEOCHAPTERADAPTATION;
import static cn.inkforge.core.db.generated.Tables.VIDEOCHAPTERADAPTATIONHEAD;
import static cn.inkforge.core.db.generated.Tables.VIDEOPROJECT;
import static cn.inkforge.core.db.generated.Tables.WRITINGBIBLE;

import cn.inkforge.core.db.generated.enums.Storylengthprofile;
import cn.inkforge.core.db.generated.tables.records.VideoassetRecord;
import cn.inkforge.core.db.generated.tables.records.VideochapteradaptationRecord;
import cn.inkforge.core.db.generated.tables.records.VideochapteradaptationheadRecord;
import cn.inkforge.core.db.generated.tables.records.VideoprojectRecord;
import cn.inkforge.core.platform.http.ApiException;
import org.jooq.DSLContext;

/** 视频各仓储在同一外层事务中复用的锁定与归属规则。 */
final class VideoDatabaseAccess {

    private VideoDatabaseAccess() {}

    static VideoprojectRecord ownedProject(
            DSLContext context, String userId, String projectId, boolean lock) {
        var query = context.select(VIDEOPROJECT.fields())
                .from(VIDEOPROJECT)
                .join(NOVEL)
                .on(NOVEL.ID.eq(VIDEOPROJECT.NOVELID))
                .where(
                        VIDEOPROJECT.ID.eq(projectId),
                        VIDEOPROJECT.DELETEDAT.isNull(),
                        NOVEL.USERID.eq(userId));
        VideoprojectRecord record = lock
                ? query.forUpdate().fetchOneInto(VideoprojectRecord.class)
                : query.fetchOneInto(VideoprojectRecord.class);
        if (record == null) {
            throw new ApiException(
                    404, "VIDEO_PROJECT_NOT_FOUND", "视频项目不存在");
        }
        return record;
    }

    static VideoassetRecord ownedAsset(
            DSLContext context, String userId, String assetId, boolean lock) {
        var query = context.select(VIDEOASSET.fields())
                .from(VIDEOASSET)
                .join(VIDEOPROJECT)
                .on(VIDEOPROJECT.ID.eq(VIDEOASSET.PROJECTID))
                .join(NOVEL)
                .on(NOVEL.ID.eq(VIDEOPROJECT.NOVELID))
                .where(
                        VIDEOASSET.ID.eq(assetId),
                        VIDEOPROJECT.DELETEDAT.isNull(),
                        NOVEL.USERID.eq(userId));
        VideoassetRecord record = lock
                ? query.forUpdate().fetchOneInto(VideoassetRecord.class)
                : query.fetchOneInto(VideoassetRecord.class);
        if (record == null) {
            throw new ApiException(
                    404, "VIDEO_ASSET_NOT_FOUND", "视频素材不存在");
        }
        return record;
    }

    static VideoAdaptationDatabaseContext ownedAdaptation(
            DSLContext context, String userId, String adaptationId, boolean lock) {
        String projectId = context.select(VIDEOCHAPTERADAPTATION.PROJECTID)
                .from(VIDEOCHAPTERADAPTATION)
                .join(VIDEOPROJECT)
                .on(VIDEOPROJECT.ID.eq(VIDEOCHAPTERADAPTATION.PROJECTID))
                .join(NOVEL)
                .on(NOVEL.ID.eq(VIDEOPROJECT.NOVELID))
                .where(
                        VIDEOCHAPTERADAPTATION.ID.eq(adaptationId),
                        VIDEOCHAPTERADAPTATION.LIFECYCLESTATUS.eq("active"),
                        VIDEOPROJECT.DELETEDAT.isNull(),
                        NOVEL.USERID.eq(userId))
                .fetchOne(VIDEOCHAPTERADAPTATION.PROJECTID);
        if (projectId == null) throw adaptationNotFound();
        VideoprojectRecord project = ownedProject(context, userId, projectId, lock);
        var adaptationQuery = context.selectFrom(VIDEOCHAPTERADAPTATION)
                .where(
                        VIDEOCHAPTERADAPTATION.ID.eq(adaptationId),
                        VIDEOCHAPTERADAPTATION.PROJECTID.eq(projectId),
                        VIDEOCHAPTERADAPTATION.LIFECYCLESTATUS.eq("active"));
        VideochapteradaptationRecord adaptation = lock
                ? adaptationQuery.forUpdate().fetchOne()
                : adaptationQuery.fetchOne();
        if (adaptation == null) throw adaptationNotFound();
        var headQuery = context.selectFrom(VIDEOCHAPTERADAPTATIONHEAD)
                .where(VIDEOCHAPTERADAPTATIONHEAD.ADAPTATIONID.eq(adaptationId));
        VideochapteradaptationheadRecord head = lock
                ? headQuery.forUpdate().fetchOne()
                : headQuery.fetchOne();
        if (head == null) {
            throw new ApiException(
                    409,
                    "VIDEO_ADAPTATION_HEAD_MISSING",
                    "章节影视化改编缺少正式版本指针");
        }
        return new VideoAdaptationDatabaseContext(adaptation, project, head);
    }

    static VideoprojectRecord requireProject(DSLContext context, String projectId) {
        VideoprojectRecord record = context.selectFrom(VIDEOPROJECT)
                .where(
                        VIDEOPROJECT.ID.eq(projectId),
                        VIDEOPROJECT.DELETEDAT.isNull())
                .fetchOne();
        if (record == null) {
            throw new ApiException(
                    404, "VIDEO_PROJECT_NOT_FOUND", "视频项目不存在");
        }
        return record;
    }

    static void requireLongSerial(
            DSLContext context, String novelId, boolean lock) {
        var query = context.select(WRITINGBIBLE.STORYLENGTHPROFILE)
                .from(WRITINGBIBLE)
                .where(WRITINGBIBLE.NOVELID.eq(novelId));
        Storylengthprofile profile = lock
                ? query.forUpdate().fetchOne(WRITINGBIBLE.STORYLENGTHPROFILE)
                : query.fetchOne(WRITINGBIBLE.STORYLENGTHPROFILE);
        if (profile != Storylengthprofile.long_serial) {
            throw new ApiException(
                    409,
                    "VIDEO_LONG_SERIAL_REQUIRED",
                    "视频制作仅支持长篇连载小说",
                    java.util.Map.of("requiredProfile", "long_serial"));
        }
    }

    private static ApiException adaptationNotFound() {
        return new ApiException(
                404,
                "VIDEO_ADAPTATION_NOT_FOUND",
                "章节影视化改编不存在");
    }

    record VideoAdaptationDatabaseContext(
            VideochapteradaptationRecord adaptation,
            VideoprojectRecord project,
            VideochapteradaptationheadRecord head) {}
}
