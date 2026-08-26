package cn.inkforge.core.video.infrastructure;

import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.VIDEOASSET;
import static cn.inkforge.core.db.generated.Tables.VIDEOPROJECT;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOT;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTKEYFRAMEHEAD;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTKEYFRAMEVERSION;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTTAKE;
import static cn.inkforge.core.db.generated.Tables.VIDEOTAKEFRAMEEXTRACTION;

import cn.inkforge.contracts.api.PostProductionAssetResponse;
import cn.inkforge.contracts.api.ChapterPostProductionWorkspaceResponse;
import cn.inkforge.contracts.api.PostProductionReadinessResponse;
import cn.inkforge.contracts.api.EpisodeEditHeadResponse;
import cn.inkforge.contracts.api.EpisodeEditVersionResponse;
import cn.inkforge.contracts.api.EpisodeMixHeadResponse;
import cn.inkforge.contracts.api.EpisodeMixVersionResponse;
import cn.inkforge.contracts.api.EpisodeExportTaskResponse;
import cn.inkforge.contracts.api.RetryEpisodeExportRequest;
import cn.inkforge.contracts.api.StartEpisodeExportRequest;
import cn.inkforge.contracts.api.SaveEpisodeEditVersionRequest;
import cn.inkforge.contracts.api.SaveEpisodeMixVersionRequest;
import cn.inkforge.contracts.api.SaveShotKeyframeVersionRequest;
import cn.inkforge.contracts.api.ShotKeyframeHeadResponse;
import cn.inkforge.contracts.api.ShotKeyframeVersionResponse;
import cn.inkforge.core.db.generated.tables.records.VideoassetRecord;
import cn.inkforge.core.db.generated.tables.records.VideochapteradaptationRecord;
import cn.inkforge.core.db.generated.tables.records.VideochapteradaptationheadRecord;
import cn.inkforge.core.db.generated.tables.records.VideoepisodeplanversionRecord;
import cn.inkforge.core.db.generated.tables.records.VideoprojectRecord;
import cn.inkforge.core.db.generated.tables.records.VideoshotRecord;
import cn.inkforge.core.db.generated.tables.records.VideoshotkeyframeheadRecord;
import cn.inkforge.core.db.generated.tables.records.VideoshotkeyframeversionRecord;
import cn.inkforge.core.db.generated.tables.records.VideoshottakeRecord;
import cn.inkforge.core.db.generated.tables.records.VideotakeframeextractionRecord;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.video.application.CompletedTakeFrameExtraction;
import cn.inkforge.core.video.application.CompletedEpisodeExport;
import cn.inkforge.core.video.application.EpisodeExportClaim;
import cn.inkforge.core.video.application.TakeFrameSource;
import cn.inkforge.core.video.application.VideoPostProductionRepository;
import cn.inkforge.core.video.application.VideoAssetFile;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.jooq.DSLContext;
import org.jooq.Record;
import org.jooq.impl.DSL;
import org.openapitools.jackson.nullable.JsonNullable;
import tools.jackson.databind.ObjectMapper;

/**
 * P1–P3 后期制作的 jOOQ 门面；所有 Head 更新与版本创建位于同一事务。
 *
 * <p>关键帧、粗剪、声音字幕和导出分别拥有版本链，本类只协调公共端口，不把它们压成一个可覆盖 JSON。
 * 抽帧和 FFmpeg 是事务外文件副作用，数据库登记失败时由应用层按精确 storage key 补偿清理。
 */
public final class JooqVideoPostProductionRepository
        implements VideoPostProductionRepository {

    private static final List<String> KEYFRAME_ROLES =
            List.of("initial_state", "transition_anchor", "end_state");

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final ObjectMapper json;
    private final JooqVideoTimelineRepository timelines;
    private final JooqVideoExportRepository exports;
    private final JooqVideoPostProductionReadModel reads;

    public JooqVideoPostProductionRepository(
            CoreDatabase database, CuidV1Generator ids, Clock clock, ObjectMapper json) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
        this.timelines = new JooqVideoTimelineRepository(database, ids, clock, json);
        this.exports = new JooqVideoExportRepository(database, ids, clock, json);
        this.reads = new JooqVideoPostProductionReadModel(
                database, timelines, exports);
    }

    @Override
    public ChapterPostProductionWorkspaceResponse getWorkspace(
            String userId,
            String adaptationId,
            PostProductionReadinessResponse readiness) {
        return reads.getWorkspace(userId, adaptationId, readiness);
    }

    @Override
    public ShotKeyframeHeadResponse saveKeyframe(
            String userId,
            String adaptationId,
            String shotId,
            SaveShotKeyframeVersionRequest request) {
        KeyframeInput input = keyframeInput(request);
        String requestHash = VideoPostProductionCommands.hash(
                keyframeRequestMap(adaptationId, shotId, input), json);
        return database.transactionResult(transaction -> {
            // 幂等命令锁必须覆盖版本号分配与 Head CAS，防止并发保存生成两个“当前版本”。
            VideoPostProductionCommands.lock(
                    transaction, "keyframe", userId, input.clientRequestId());
            VideoshotkeyframeversionRecord existing = transaction
                    .selectFrom(VIDEOSHOTKEYFRAMEVERSION)
                    .where(
                            VIDEOSHOTKEYFRAMEVERSION.CREATEDBYUSERID.eq(userId),
                            VIDEOSHOTKEYFRAMEVERSION.CLIENTREQUESTID.eq(
                                    input.clientRequestId()))
                    .fetchOne();
            if (existing != null) {
                if (!requestHash.equals(existing.getRequesthash())) {
                    throw error(
                            409,
                            "VIDEO_KEYFRAME_CLIENT_REQUEST_REUSED",
                            "clientRequestId 已用于不同的关键帧请求");
                }
                return keyframeHeadResponse(
                        transaction, existing.getShotid(), existing.getRole());
            }

            VideoPostProductionContext context =
                    VideoPostProductionDatabaseAccess.context(
                            transaction, userId, adaptationId, true);
            VideoshotRecord shot = context.shots().stream()
                    .filter(item -> item.getId().equals(shotId))
                    .findFirst()
                    .orElseThrow(() -> error(
                            404,
                            "VIDEO_KEYFRAME_SHOT_NOT_FOUND",
                            "当前正式方案中不存在该镜头"));
            VideoshotkeyframeheadRecord head = transaction
                    .selectFrom(VIDEOSHOTKEYFRAMEHEAD)
                    .where(
                            VIDEOSHOTKEYFRAMEHEAD.SHOTID.eq(shotId),
                            VIDEOSHOTKEYFRAMEHEAD.ROLE.eq(input.role()))
                    .forUpdate()
                    .fetchOne();
            LocalDateTime now = DatabaseTimestamp.now(clock);
            if (head == null) {
                transaction.insertInto(VIDEOSHOTKEYFRAMEHEAD)
                        .set(VIDEOSHOTKEYFRAMEHEAD.SHOTID, shotId)
                        .set(VIDEOSHOTKEYFRAMEHEAD.SHOTPLANVERSIONID, context.planId())
                        .set(VIDEOSHOTKEYFRAMEHEAD.ROLE, input.role())
                        .set(VIDEOSHOTKEYFRAMEHEAD.CURRENTVERSIONID, (String) null)
                        .set(VIDEOSHOTKEYFRAMEHEAD.REVISION, 1)
                        .set(VIDEOSHOTKEYFRAMEHEAD.UPDATEDAT, now)
                        .execute();
                head = transaction.selectFrom(VIDEOSHOTKEYFRAMEHEAD)
                        .where(
                                VIDEOSHOTKEYFRAMEHEAD.SHOTID.eq(shotId),
                                VIDEOSHOTKEYFRAMEHEAD.ROLE.eq(input.role()))
                        .forUpdate()
                        .fetchOne();
            }
            if (head == null || head.getRevision() != input.expectedRevision()) {
                throw error(
                        409,
                        "VIDEO_KEYFRAME_REVISION_CONFLICT",
                        "关键帧已经变化，请刷新后重新确认");
            }

            VideoassetRecord asset = null;
            String sourceKind = "cleared";
            if (input.assetId() != null) {
                asset = transaction.selectFrom(VIDEOASSET)
                        .where(
                                VIDEOASSET.ID.eq(input.assetId()),
                                VIDEOASSET.PROJECTID.eq(context.project().getId()))
                        .fetchOne();
                if (asset == null
                        || !"image".equals(asset.getModality())
                        || !Set.of("keyframe", "storyboard").contains(asset.getDuty())
                        || !"confirmed".equals(asset.getRightsstatus())
                        || asset.getLockedat() == null) {
                    throw error(
                            409,
                            "VIDEO_KEYFRAME_ASSET_NOT_READY",
                            "关键帧必须使用本项目已确认并锁定的 keyframe/storyboard 图片");
                }
                sourceKind = "asset";
            }
            if (input.sourceTakeId() != null) {
                VideoshottakeRecord take = transaction.selectFrom(VIDEOSHOTTAKE)
                        .where(
                                VIDEOSHOTTAKE.ID.eq(input.sourceTakeId()),
                                VIDEOSHOTTAKE.SHOTID.eq(shotId),
                                VIDEOSHOTTAKE.ADAPTATIONID.eq(adaptationId))
                        .fetchOne();
                if (take == null) {
                    throw error(
                            404,
                            "VIDEO_KEYFRAME_SOURCE_TAKE_NOT_FOUND",
                            "关键帧来源 Take 不存在");
                }
                VideoassetRecord takeAsset = transaction.selectFrom(VIDEOASSET)
                        .where(VIDEOASSET.ID.eq(take.getAssetid()))
                        .fetchOne();
                if (takeAsset == null
                        || takeAsset.getDurationms() == null
                        || input.sourceTimeMs() == null
                        || input.sourceTimeMs() >= takeAsset.getDurationms()) {
                    throw error(
                            422,
                            "VIDEO_KEYFRAME_SOURCE_TIME_INVALID",
                            "抽帧时间必须位于来源 Take 的已知时长内");
                }
                boolean proven = transaction.fetchExists(transaction
                        .selectOne()
                        .from(VIDEOTAKEFRAMEEXTRACTION)
                        .where(
                                VIDEOTAKEFRAMEEXTRACTION.ASSETID.eq(input.assetId()),
                                VIDEOTAKEFRAMEEXTRACTION.TAKEID.eq(input.sourceTakeId()),
                                VIDEOTAKEFRAMEEXTRACTION.TIMESTAMPMS.eq(
                                        input.sourceTimeMs())));
                // 仅凭一张图片和 sourceTakeId 不足以追溯；必须存在 Core 受控抽帧产生的三元来源事实。
                if (!proven) {
                    throw error(
                            422,
                            "VIDEO_KEYFRAME_EXTRACTION_NOT_PROVEN",
                            "该图片没有与 Take 和时间点匹配的受控抽帧记录");
                }
                sourceKind = "take_frame";
            }

            Integer maximum = transaction
                    .select(DSL.coalesce(DSL.max(VIDEOSHOTKEYFRAMEVERSION.VERSIONNO), 0))
                    .from(VIDEOSHOTKEYFRAMEVERSION)
                    .where(
                            VIDEOSHOTKEYFRAMEVERSION.SHOTID.eq(shotId),
                            VIDEOSHOTKEYFRAMEVERSION.ROLE.eq(input.role()))
                    .fetchOne(0, Integer.class);
            int versionNo = (maximum == null ? 0 : maximum) + 1;
            Map<String, Object> content = new LinkedHashMap<>();
            content.put("shotId", shotId);
            content.put("role", input.role());
            content.put("assetId", asset == null ? null : asset.getId());
            content.put("assetSha256", asset == null ? null : asset.getSha256());
            content.put("sourceKind", sourceKind);
            content.put("sourceTakeId", input.sourceTakeId());
            content.put("sourceTimeMs", input.sourceTimeMs());
            String versionId = ids.next();
            transaction.insertInto(VIDEOSHOTKEYFRAMEVERSION)
                    .set(VIDEOSHOTKEYFRAMEVERSION.ID, versionId)
                    .set(VIDEOSHOTKEYFRAMEVERSION.ADAPTATIONID, adaptationId)
                    .set(VIDEOSHOTKEYFRAMEVERSION.PROJECTID, context.project().getId())
                    .set(VIDEOSHOTKEYFRAMEVERSION.NOVELID, context.adaptation().getNovelid())
                    .set(VIDEOSHOTKEYFRAMEVERSION.SHOTID, shotId)
                    .set(VIDEOSHOTKEYFRAMEVERSION.SHOTPLANVERSIONID, context.planId())
                    .set(VIDEOSHOTKEYFRAMEVERSION.ROLE, input.role())
                    .set(VIDEOSHOTKEYFRAMEVERSION.VERSIONNO, versionNo)
                    .set(VIDEOSHOTKEYFRAMEVERSION.BASEDONVERSIONID, head.getCurrentversionid())
                    .set(VIDEOSHOTKEYFRAMEVERSION.ASSETID, asset == null ? null : asset.getId())
                    .set(VIDEOSHOTKEYFRAMEVERSION.SOURCEKIND, sourceKind)
                    .set(VIDEOSHOTKEYFRAMEVERSION.SOURCETAKEID, input.sourceTakeId())
                    .set(VIDEOSHOTKEYFRAMEVERSION.SOURCETIMEMS, input.sourceTimeMs())
                    .set(VIDEOSHOTKEYFRAMEVERSION.CLIENTREQUESTID, input.clientRequestId())
                    .set(VIDEOSHOTKEYFRAMEVERSION.REQUESTHASH, requestHash)
                    .set(
                            VIDEOSHOTKEYFRAMEVERSION.CONTENTHASH,
                            VideoPostProductionCommands.hash(content, json))
                    .set(VIDEOSHOTKEYFRAMEVERSION.CREATEDBYUSERID, userId)
                    .set(VIDEOSHOTKEYFRAMEVERSION.CREATEDAT, now)
                    .execute();
            transaction.update(VIDEOSHOTKEYFRAMEHEAD)
                    .set(VIDEOSHOTKEYFRAMEHEAD.CURRENTVERSIONID, versionId)
                    .set(VIDEOSHOTKEYFRAMEHEAD.REVISION, head.getRevision() + 1)
                    .set(VIDEOSHOTKEYFRAMEHEAD.UPDATEDAT, now)
                    .where(
                            VIDEOSHOTKEYFRAMEHEAD.SHOTID.eq(shotId),
                            VIDEOSHOTKEYFRAMEHEAD.ROLE.eq(input.role()))
                    .execute();
            return keyframeHeadResponse(transaction, shotId, input.role());
        });
    }

    @Override
    public TakeFrameSource getTakeFrameSource(
            String userId, String takeId, int timestampMs) {
        Record row = database.dsl().select(VIDEOSHOTTAKE.fields())
                .select(VIDEOASSET.fields())
                .from(VIDEOSHOTTAKE)
                .join(VIDEOASSET)
                .on(VIDEOASSET.ID.eq(VIDEOSHOTTAKE.ASSETID))
                .join(VIDEOPROJECT)
                .on(VIDEOPROJECT.ID.eq(VIDEOSHOTTAKE.PROJECTID))
                .join(NOVEL)
                .on(NOVEL.ID.eq(VIDEOPROJECT.NOVELID))
                .where(VIDEOSHOTTAKE.ID.eq(takeId), NOVEL.USERID.eq(userId))
                .fetchOne();
        if (row == null) {
            throw error(404, "VIDEO_TAKE_NOT_FOUND", "候选 Take 不存在");
        }
        VideoshottakeRecord take = row.into(VIDEOSHOTTAKE);
        VideoassetRecord asset = row.into(VIDEOASSET);
        if (!"video".equals(asset.getModality())
                || !"confirmed".equals(asset.getRightsstatus())
                || asset.getLockedat() == null) {
            throw error(
                    409,
                    "VIDEO_KEYFRAME_SOURCE_TAKE_NOT_READY",
                    "来源 Take 的视频素材未确认、未锁定或类型无效");
        }
        if (timestampMs < 0
                || asset.getDurationms() == null
                || timestampMs >= asset.getDurationms()) {
            throw error(
                    422,
                    "VIDEO_KEYFRAME_SOURCE_TIME_INVALID",
                    "抽帧时间必须位于 Take 的已知时长内");
        }
        return new TakeFrameSource(
                take.getId(),
                take.getShotid(),
                take.getAdaptationid(),
                take.getProjectid(),
                take.getNovelid(),
                asset.getStoragekey(),
                asset.getSha256(),
                asset.getDurationms());
    }

    @Override
    public PostProductionAssetResponse getExtractionReplay(
            String userId, String clientRequestId, String requestHash) {
        VideotakeframeextractionRecord extraction = database.dsl()
                .selectFrom(VIDEOTAKEFRAMEEXTRACTION)
                .where(
                        VIDEOTAKEFRAMEEXTRACTION.REQUESTEDBYUSERID.eq(userId),
                        VIDEOTAKEFRAMEEXTRACTION.CLIENTREQUESTID.eq(
                                VideoPostProductionCommands.requestId(clientRequestId)))
                .fetchOne();
        if (extraction == null) return null;
        if (!extraction.getRequesthash().equals(requestHash)) {
            throw error(
                    409,
                    "VIDEO_KEYFRAME_EXTRACTION_REQUEST_REUSED",
                    "clientRequestId 已用于不同的抽帧请求");
        }
        VideoassetRecord asset = database.dsl().selectFrom(VIDEOASSET)
                .where(VIDEOASSET.ID.eq(extraction.getAssetid()))
                .fetchOne();
        if (asset == null) {
            throw error(
                    409,
                    "VIDEO_KEYFRAME_EXTRACTION_ASSET_MISSING",
                    "既有抽帧记录缺少受控图片素材");
        }
        return assetResponse(asset);
    }

    @Override
    public PostProductionAssetResponse completeExtractedFrame(
            CompletedTakeFrameExtraction completed) {
        String requestId = VideoPostProductionCommands.requestId(completed.clientRequestId());
        return database.transactionResult(transaction -> {
            VideoPostProductionCommands.lock(
                    transaction, "frame-extraction", completed.userId(), requestId);
            VideotakeframeextractionRecord replay = transaction
                    .selectFrom(VIDEOTAKEFRAMEEXTRACTION)
                    .where(
                            VIDEOTAKEFRAMEEXTRACTION.REQUESTEDBYUSERID.eq(
                                    completed.userId()),
                            VIDEOTAKEFRAMEEXTRACTION.CLIENTREQUESTID.eq(requestId))
                    .fetchOne();
            if (replay != null) {
                if (!replay.getRequesthash().equals(completed.requestHash())
                        || !replay.getTakeid().equals(completed.source().takeId())
                        || replay.getTimestampms() != completed.timestampMs()) {
                    throw error(
                            409,
                            "VIDEO_KEYFRAME_EXTRACTION_REQUEST_REUSED",
                            "clientRequestId 已用于不同的抽帧请求");
                }
                VideoassetRecord asset = transaction.selectFrom(VIDEOASSET)
                        .where(VIDEOASSET.ID.eq(replay.getAssetid()))
                        .fetchOne();
                if (asset == null) {
                    throw error(
                            409,
                            "VIDEO_KEYFRAME_EXTRACTION_ASSET_MISSING",
                            "既有抽帧记录缺少受控图片素材");
                }
                return assetResponse(asset);
            }
            VideoDatabaseAccess.ownedProject(
                    transaction,
                    completed.userId(),
                    completed.source().projectId(),
                    false);
            VideoassetRecord existing = transaction.selectFrom(VIDEOASSET)
                    .where(VIDEOASSET.ID.eq(completed.assetId()))
                    .fetchOne();
            if (existing != null) {
                if (!existing.getProjectid().equals(completed.source().projectId())
                        || !existing.getSha256().equals(completed.stored().sha256())) {
                    throw error(
                            409,
                            "VIDEO_KEYFRAME_EXTRACTION_REUSED",
                            "抽帧请求标识已用于不同结果");
                }
                VideotakeframeextractionRecord fact = transaction
                        .selectFrom(VIDEOTAKEFRAMEEXTRACTION)
                        .where(VIDEOTAKEFRAMEEXTRACTION.ASSETID.eq(completed.assetId()))
                        .fetchOne();
                if (fact == null
                        || !fact.getTakeid().equals(completed.source().takeId())
                        || fact.getTimestampms() != completed.timestampMs()
                        || !fact.getRequesthash().equals(completed.requestHash())) {
                    throw error(
                            409,
                            "VIDEO_KEYFRAME_EXTRACTION_REUSED",
                            "抽帧素材缺少匹配的来源事实");
                }
                return assetResponse(existing);
            }
            LocalDateTime now = DatabaseTimestamp.now(clock);
            // 素材与 Take/时间点来源事实同事务写入，避免生成无法证明出处的孤立关键帧。
            transaction.insertInto(VIDEOASSET)
                    .set(VIDEOASSET.ID, completed.assetId())
                    .set(VIDEOASSET.PROJECTID, completed.source().projectId())
                    .set(VIDEOASSET.NAME, completed.name())
                    .set(VIDEOASSET.MODALITY, "image")
                    .set(VIDEOASSET.DUTY, "keyframe")
                    .set(VIDEOASSET.STORAGEKEY, completed.stored().storageKey())
                    .set(VIDEOASSET.MIMETYPE, completed.stored().mimeType())
                    .set(VIDEOASSET.BYTESIZE, completed.stored().byteSize())
                    .set(VIDEOASSET.DURATIONMS, (Integer) null)
                    .set(VIDEOASSET.SHA256, completed.stored().sha256())
                    .set(VIDEOASSET.SOURCEKIND, "model_generated")
                    .set(VIDEOASSET.RIGHTSSTATUS, "confirmed")
                    .set(VIDEOASSET.LOCKEDAT, now)
                    .set(VIDEOASSET.CREATEDAT, now)
                    .set(VIDEOASSET.UPDATEDAT, now)
                    .execute();
            transaction.insertInto(VIDEOTAKEFRAMEEXTRACTION)
                    .set(VIDEOTAKEFRAMEEXTRACTION.ASSETID, completed.assetId())
                    .set(VIDEOTAKEFRAMEEXTRACTION.TAKEID, completed.source().takeId())
                    .set(VIDEOTAKEFRAMEEXTRACTION.SHOTID, completed.source().shotId())
                    .set(VIDEOTAKEFRAMEEXTRACTION.ADAPTATIONID, completed.source().adaptationId())
                    .set(VIDEOTAKEFRAMEEXTRACTION.PROJECTID, completed.source().projectId())
                    .set(VIDEOTAKEFRAMEEXTRACTION.NOVELID, completed.source().novelId())
                    .set(VIDEOTAKEFRAMEEXTRACTION.TIMESTAMPMS, completed.timestampMs())
                    .set(VIDEOTAKEFRAMEEXTRACTION.CLIENTREQUESTID, requestId)
                    .set(VIDEOTAKEFRAMEEXTRACTION.REQUESTHASH, completed.requestHash())
                    .set(VIDEOTAKEFRAMEEXTRACTION.REQUESTEDBYUSERID, completed.userId())
                    .set(VIDEOTAKEFRAMEEXTRACTION.CREATEDAT, now)
                    .execute();
            return assetResponse(transaction.selectFrom(VIDEOASSET)
                    .where(VIDEOASSET.ID.eq(completed.assetId()))
                    .fetchOne());
        });
    }

    @Override
    public EpisodeEditHeadResponse saveEditVersion(
            String userId,
            String adaptationId,
            int episodeNo,
            SaveEpisodeEditVersionRequest request) {
        return timelines.saveEditVersion(userId, adaptationId, episodeNo, request);
    }

    @Override
    public EpisodeEditVersionResponse getEditVersion(String userId, String versionId) {
        return timelines.getEditVersion(userId, versionId);
    }

    @Override
    public EpisodeMixHeadResponse saveMixVersion(
            String userId,
            String adaptationId,
            int episodeNo,
            SaveEpisodeMixVersionRequest request) {
        return timelines.saveMixVersion(userId, adaptationId, episodeNo, request);
    }

    @Override
    public EpisodeMixVersionResponse getMixVersion(String userId, String versionId) {
        return timelines.getMixVersion(userId, versionId);
    }

    @Override
    public EpisodeExportTaskResponse createExportTask(
            String userId,
            String adaptationId,
            int episodeNo,
            StartEpisodeExportRequest request) {
        return exports.createExportTask(userId, adaptationId, episodeNo, request);
    }

    @Override
    public EpisodeExportTaskResponse retryExportTask(
            String userId, String taskId, RetryEpisodeExportRequest request) {
        return exports.retryExportTask(userId, taskId, request);
    }

    @Override
    public EpisodeExportTaskResponse getExportTask(String userId, String taskId) {
        return exports.getExportTask(userId, taskId);
    }

    @Override
    public VideoAssetFile getExportFile(String userId, String exportId) {
        return exports.getExportFile(userId, exportId);
    }

    @Override
    public List<EpisodeExportClaim> claimDueExportTasks(int limit) {
        return exports.claimDueExportTasks(limit);
    }

    @Override
    public EpisodeExportTaskResponse completeExport(CompletedEpisodeExport completed) {
        return exports.completeExport(completed);
    }

    @Override
    public boolean failExport(String taskId, String code, String message) {
        return exports.failExport(taskId, code, message);
    }

    private ShotKeyframeHeadResponse keyframeHeadResponse(
            DSLContext context, String shotId, String role) {
        VideoshotkeyframeheadRecord head = context.selectFrom(VIDEOSHOTKEYFRAMEHEAD)
                .where(
                        VIDEOSHOTKEYFRAMEHEAD.SHOTID.eq(shotId),
                        VIDEOSHOTKEYFRAMEHEAD.ROLE.eq(role))
                .fetchOne();
        List<VideoshotkeyframeversionRecord> versions = context
                .selectFrom(VIDEOSHOTKEYFRAMEVERSION)
                .where(
                        VIDEOSHOTKEYFRAMEVERSION.SHOTID.eq(shotId),
                        VIDEOSHOTKEYFRAMEVERSION.ROLE.eq(role))
                .orderBy(VIDEOSHOTKEYFRAMEVERSION.VERSIONNO.desc())
                .fetch();
        Map<String, VideoassetRecord> assets = new HashMap<>();
        List<String> assetIds = versions.stream()
                .map(VideoshotkeyframeversionRecord::getAssetid)
                .filter(Objects::nonNull)
                .distinct()
                .toList();
        if (!assetIds.isEmpty()) {
            context.selectFrom(VIDEOASSET)
                    .where(VIDEOASSET.ID.in(assetIds))
                    .fetch()
                    .forEach(asset -> assets.put(asset.getId(), asset));
        }
        List<ShotKeyframeVersionResponse> history = versions.stream()
                .map(version -> keyframeVersionResponse(
                        version,
                        version.getAssetid() == null
                                ? null
                                : assets.get(version.getAssetid())))
                .toList();
        ShotKeyframeVersionResponse current = null;
        if (head != null && head.getCurrentversionid() != null) {
            current = history.stream()
                    .filter(version -> version.getId().equals(head.getCurrentversionid()))
                    .findFirst()
                    .orElseThrow(() -> error(
                            409,
                            "VIDEO_KEYFRAME_HEAD_INVALID",
                            "当前关键帧版本指针无效"));
        }
        return new ShotKeyframeHeadResponse(
                        current,
                        head == null ? 1 : head.getRevision(),
                        ShotKeyframeHeadResponse.RoleEnum.fromValue(role),
                        shotId)
                .history(history);
    }

    private static ShotKeyframeVersionResponse keyframeVersionResponse(
            VideoshotkeyframeversionRecord version, VideoassetRecord asset) {
        return new ShotKeyframeVersionResponse(
                asset == null ? null : assetResponse(asset),
                version.getBasedonversionid(),
                version.getContenthash(),
                DatabaseTimestamp.api(version.getCreatedat()),
                version.getId(),
                ShotKeyframeVersionResponse.RoleEnum.fromValue(version.getRole()),
                version.getShotid(),
                version.getShotplanversionid(),
                ShotKeyframeVersionResponse.SourceKindEnum.fromValue(version.getSourcekind()),
                version.getSourcetakeid(),
                version.getSourcetimems(),
                version.getVersionno());
    }

    static PostProductionAssetResponse assetResponse(VideoassetRecord asset) {
        return new PostProductionAssetResponse(
                "/api/v1/video/assets/" + asset.getId() + "/content",
                asset.getDurationms(),
                asset.getDuty(),
                asset.getId(),
                asset.getMimetype(),
                PostProductionAssetResponse.ModalityEnum.fromValue(asset.getModality()),
                asset.getName(),
                asset.getSha256());
    }

    private KeyframeInput keyframeInput(SaveShotKeyframeVersionRequest request) {
        String requestId = VideoPostProductionCommands.requestId(request.getClientRequestId());
        String role = request.getRole() == null ? null : request.getRole().getValue();
        String assetId = nullable(request.getAssetId());
        String sourceTakeId = nullable(request.getSourceTakeId());
        Integer sourceTimeMs = nullable(request.getSourceTimeMs());
        if (request.getExpectedRevision() == null
                || request.getExpectedRevision() < 1
                || role == null
                || !KEYFRAME_ROLES.contains(role)
                || assetId == null && (sourceTakeId != null || sourceTimeMs != null)
                || (sourceTakeId == null) != (sourceTimeMs == null)) {
            throw error(422, "VALIDATION_ERROR", "关键帧请求无效");
        }
        return new KeyframeInput(
                requestId,
                request.getExpectedRevision(),
                role,
                assetId,
                sourceTakeId,
                sourceTimeMs);
    }

    private static Map<String, Object> keyframeRequestMap(
            String adaptationId, String shotId, KeyframeInput input) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("adaptationId", adaptationId);
        result.put("shotId", shotId);
        result.put("clientRequestId", input.clientRequestId());
        result.put("expectedRevision", input.expectedRevision());
        result.put("role", input.role());
        result.put("assetId", input.assetId());
        result.put("sourceTakeId", input.sourceTakeId());
        result.put("sourceTimeMs", input.sourceTimeMs());
        return result;
    }

    private static <T> T nullable(JsonNullable<T> value) {
        return value == null || value.isUndefined() ? null : value.orElse(null);
    }

    private static ApiException error(int status, String code, String message) {
        return new ApiException(status, code, message);
    }

    private record KeyframeInput(
            String clientRequestId,
            int expectedRevision,
            String role,
            String assetId,
            String sourceTakeId,
            Integer sourceTimeMs) {}

}
