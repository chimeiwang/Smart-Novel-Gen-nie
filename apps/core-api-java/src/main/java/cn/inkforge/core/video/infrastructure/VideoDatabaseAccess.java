package cn.inkforge.core.video.infrastructure;

import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.VIDEOASSET;
import static cn.inkforge.core.db.generated.Tables.VIDEOPROJECT;
import static cn.inkforge.core.db.generated.Tables.WRITINGBIBLE;

import cn.inkforge.core.db.generated.enums.Storylengthprofile;
import cn.inkforge.core.db.generated.tables.records.VideoassetRecord;
import cn.inkforge.core.db.generated.tables.records.VideoprojectRecord;
import cn.inkforge.core.platform.http.ApiException;
import org.jooq.DSLContext;

/** 视频各仓储在同一外层事务中复用的锁定与归属规则。 */
final class VideoDatabaseAccess {

    private VideoDatabaseAccess() {}

    static VideoprojectRecord ownedProject(
            DSLContext context, String userId, String projectId, boolean lock) {
        if (lock) {
            // 与 V2 计费后的候选投影采用同一 Novel→Project 顺序；仍只锁原查询已有的行。
            context.select(NOVEL.ID).from(NOVEL)
                    .where(NOVEL.USERID.eq(userId), NOVEL.ID.in(context.select(VIDEOPROJECT.NOVELID)
                            .from(VIDEOPROJECT).where(VIDEOPROJECT.ID.eq(projectId))))
                    .forUpdate().fetch();
        }
        var query = context.select(VIDEOPROJECT.fields())
                .from(VIDEOPROJECT)
                .join(NOVEL)
                .on(NOVEL.ID.eq(VIDEOPROJECT.NOVELID))
                .where(
                        VIDEOPROJECT.ID.eq(projectId),
                        VIDEOPROJECT.DELETEDAT.isNull(),
                        NOVEL.USERID.eq(userId));
        VideoprojectRecord record = lock
                ? query.forUpdate().of(VIDEOPROJECT).fetchOneInto(VideoprojectRecord.class)
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

}
