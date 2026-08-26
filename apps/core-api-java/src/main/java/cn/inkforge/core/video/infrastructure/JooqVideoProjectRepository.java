package cn.inkforge.core.video.infrastructure;

import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.VIDEOASSET;
import static cn.inkforge.core.db.generated.Tables.VIDEOPROJECT;
import cn.inkforge.core.db.generated.tables.records.VideoassetRecord;
import cn.inkforge.core.db.generated.tables.records.VideoprojectRecord;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.video.application.VideoAssetCreation;
import cn.inkforge.core.video.application.VideoAssetFile;
import cn.inkforge.core.video.application.VideoAssetSnapshot;
import cn.inkforge.core.video.application.VideoProjectAggregate;
import cn.inkforge.core.video.application.VideoProjectCreation;
import cn.inkforge.core.video.application.VideoProjectRepository;
import cn.inkforge.core.video.application.VideoProjectSnapshot;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Objects;
import org.jooq.DSLContext;

/** 视频项目与真实素材的 jOOQ 实现；不包含已退役的公共 VideoScene 语义。 */
public final class JooqVideoProjectRepository implements VideoProjectRepository {

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;

    public JooqVideoProjectRepository(
            CoreDatabase database, CuidV1Generator ids, Clock clock) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
    }

    @Override
    public VideoProjectSnapshot createProject(
            String userId, String novelId, VideoProjectCreation creation) {
        return database.transactionResult(transaction -> {
            String owned = transaction.select(NOVEL.ID)
                    .from(NOVEL)
                    .where(NOVEL.ID.eq(novelId), NOVEL.USERID.eq(userId))
                    .fetchOne(NOVEL.ID);
            if (owned == null) {
                throw new ApiException(404, "NOVEL_NOT_FOUND", "小说不存在");
            }
            VideoDatabaseAccess.requireLongSerial(transaction, novelId, true);
            LocalDateTime now = DatabaseTimestamp.now(clock);
            String projectId = ids.next();
            transaction.insertInto(VIDEOPROJECT)
                    .set(VIDEOPROJECT.ID, projectId)
                    .set(VIDEOPROJECT.NOVELID, novelId)
                    .set(VIDEOPROJECT.TITLE, creation.title())
                    .set(VIDEOPROJECT.MODE, creation.mode())
                    .set(VIDEOPROJECT.STATUS, "draft")
                    .set(VIDEOPROJECT.TARGETASPECTRATIO, creation.targetAspectRatio())
                    .set(VIDEOPROJECT.TARGETLANGUAGE, creation.targetLanguage())
                    .set(VIDEOPROJECT.PROVIDER, "seedance_2_5")
                    .set(VIDEOPROJECT.REVISION, 1)
                    .set(VIDEOPROJECT.CREATEDAT, now)
                    .set(VIDEOPROJECT.UPDATEDAT, now)
                    .execute();
            return project(requireProjectRecord(transaction, projectId));
        });
    }

    @Override
    public List<VideoProjectSnapshot> listProjects(String userId, String novelId) {
        return database.dsl()
                .select(VIDEOPROJECT.fields())
                .from(VIDEOPROJECT)
                .join(NOVEL)
                .on(NOVEL.ID.eq(VIDEOPROJECT.NOVELID))
                .where(
                        NOVEL.USERID.eq(userId),
                        VIDEOPROJECT.NOVELID.eq(novelId),
                        VIDEOPROJECT.DELETEDAT.isNull())
                .orderBy(VIDEOPROJECT.UPDATEDAT.desc(), VIDEOPROJECT.ID)
                .fetchInto(VideoprojectRecord.class)
                .stream()
                .map(JooqVideoProjectRepository::project)
                .toList();
    }

    @Override
    public VideoProjectAggregate getProject(String userId, String projectId) {
        return database.transactionResult(transaction -> {
            VideoprojectRecord project = VideoDatabaseAccess.ownedProject(
                    transaction, userId, projectId, false);
            List<VideoAssetSnapshot> assets = transaction.selectFrom(VIDEOASSET)
                    .where(VIDEOASSET.PROJECTID.eq(projectId))
                    .orderBy(VIDEOASSET.CREATEDAT, VIDEOASSET.ID)
                    .fetch()
                    .stream()
                    .map(JooqVideoProjectRepository::asset)
                    .toList();
            return new VideoProjectAggregate(project(project), assets);
        });
    }

    @Override
    public void requireWritableProject(String userId, String projectId) {
        database.transactionResult(transaction -> {
            VideoprojectRecord project = VideoDatabaseAccess.ownedProject(
                    transaction, userId, projectId, false);
            VideoDatabaseAccess.requireLongSerial(transaction, project.getNovelid(), false);
            // series 与试制模式共享素材库；旧 VideoScene 的预览模式限制不得泄漏到章节改编域。
            return null;
        });
    }

    @Override
    public VideoAssetSnapshot createAsset(
            String userId, String projectId, VideoAssetCreation creation) {
        return database.transactionResult(transaction -> {
            VideoprojectRecord project = VideoDatabaseAccess.ownedProject(
                    transaction, userId, projectId, true);
            VideoDatabaseAccess.requireLongSerial(transaction, project.getNovelid(), true);
            LocalDateTime now = DatabaseTimestamp.now(clock);
            transaction.insertInto(VIDEOASSET)
                    .set(VIDEOASSET.ID, creation.id())
                    .set(VIDEOASSET.PROJECTID, projectId)
                    .set(VIDEOASSET.NAME, creation.name())
                    .set(VIDEOASSET.MODALITY, creation.modality())
                    .set(VIDEOASSET.DUTY, creation.duty())
                    .set(VIDEOASSET.STORAGEKEY, creation.stored().storageKey())
                    .set(VIDEOASSET.MIMETYPE, creation.stored().mimeType())
                    .set(VIDEOASSET.BYTESIZE, creation.stored().byteSize())
                    .set(VIDEOASSET.DURATIONMS, creation.durationMs())
                    .set(VIDEOASSET.SHA256, creation.stored().sha256())
                    .set(VIDEOASSET.SOURCEKIND, creation.sourceKind())
                    .set(VIDEOASSET.RIGHTSSTATUS, "unconfirmed")
                    .set(VIDEOASSET.CREATEDAT, now)
                    .set(VIDEOASSET.UPDATEDAT, now)
                    .execute();
            VideoassetRecord record = transaction.selectFrom(VIDEOASSET)
                    .where(VIDEOASSET.ID.eq(creation.id()))
                    .fetchOne();
            if (record == null) throw new IllegalStateException("视频素材创建后无法读取");
            return asset(record);
        });
    }

    @Override
    public VideoAssetSnapshot confirmAsset(
            String userId, String assetId, String rightsStatus) {
        return database.transactionResult(transaction -> {
            VideoassetRecord record = VideoDatabaseAccess.ownedAsset(
                    transaction, userId, assetId, true);
            VideoprojectRecord project = VideoDatabaseAccess.requireProject(
                    transaction, record.getProjectid());
            VideoDatabaseAccess.requireLongSerial(transaction, project.getNovelid(), true);
            LocalDateTime now = DatabaseTimestamp.next(clock, record.getUpdatedat());
            transaction.update(VIDEOASSET)
                    .set(VIDEOASSET.RIGHTSSTATUS, rightsStatus)
                    .set(
                            VIDEOASSET.LOCKEDAT,
                            "confirmed".equals(rightsStatus) ? now : null)
                    .set(VIDEOASSET.UPDATEDAT, now)
                    .where(VIDEOASSET.ID.eq(assetId))
                    .execute();
            record.setRightsstatus(rightsStatus);
            record.setLockedat("confirmed".equals(rightsStatus) ? now : null);
            record.setUpdatedat(now);
            return asset(record);
        });
    }

    @Override
    public VideoAssetFile getAssetFile(String userId, String assetId) {
        VideoassetRecord record = VideoDatabaseAccess.ownedAsset(
                database.dsl(), userId, assetId, false);
        return new VideoAssetFile(
                record.getStoragekey(), record.getMimetype(), record.getName());
    }

    private static VideoprojectRecord requireProjectRecord(
            DSLContext context, String projectId) {
        return VideoDatabaseAccess.requireProject(context, projectId);
    }

    private static VideoProjectSnapshot project(VideoprojectRecord value) {
        return new VideoProjectSnapshot(
                value.getId(),
                value.getNovelid(),
                value.getTitle(),
                value.getMode(),
                value.getStatus(),
                value.getTargetaspectratio(),
                value.getTargetlanguage(),
                value.getProvider(),
                value.getRevision(),
                DatabaseTimestamp.api(value.getCreatedat()),
                DatabaseTimestamp.api(value.getUpdatedat()));
    }

    private static VideoAssetSnapshot asset(VideoassetRecord value) {
        return new VideoAssetSnapshot(
                value.getId(),
                value.getProjectid(),
                value.getName(),
                value.getModality(),
                value.getDuty(),
                value.getMimetype(),
                value.getBytesize(),
                value.getDurationms(),
                value.getSha256(),
                value.getSourcekind(),
                value.getRightsstatus(),
                DatabaseTimestamp.api(value.getLockedat()),
                DatabaseTimestamp.api(value.getCreatedat()),
                DatabaseTimestamp.api(value.getUpdatedat()));
    }
}
