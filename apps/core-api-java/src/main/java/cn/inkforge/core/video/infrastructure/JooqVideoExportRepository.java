package cn.inkforge.core.video.infrastructure;

import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.VIDEOASSET;
import static cn.inkforge.core.db.generated.Tables.VIDEOEPISODEAUDIOCLIP;
import static cn.inkforge.core.db.generated.Tables.VIDEOEPISODEEDITCLIP;
import static cn.inkforge.core.db.generated.Tables.VIDEOEPISODEEDITVERSION;
import static cn.inkforge.core.db.generated.Tables.VIDEOEPISODEEXPORT;
import static cn.inkforge.core.db.generated.Tables.VIDEOEPISODEEXPORTTASK;
import static cn.inkforge.core.db.generated.Tables.VIDEOEPISODEMIXVERSION;
import static cn.inkforge.core.db.generated.Tables.VIDEOEPISODESUBTITLECUE;
import static cn.inkforge.core.db.generated.Tables.VIDEOPROJECT;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTTAKE;

import cn.inkforge.contracts.api.EpisodeExportResponse;
import cn.inkforge.contracts.api.EpisodeExportTaskResponse;
import cn.inkforge.contracts.api.PostProductionAssetResponse;
import cn.inkforge.contracts.api.RetryEpisodeExportRequest;
import cn.inkforge.contracts.api.StartEpisodeExportRequest;
import cn.inkforge.core.db.generated.tables.records.VideoassetRecord;
import cn.inkforge.core.db.generated.tables.records.VideoepisodeaudioclipRecord;
import cn.inkforge.core.db.generated.tables.records.VideoepisodeeditclipRecord;
import cn.inkforge.core.db.generated.tables.records.VideoepisodeeditversionRecord;
import cn.inkforge.core.db.generated.tables.records.VideoepisodeexportRecord;
import cn.inkforge.core.db.generated.tables.records.VideoepisodeexporttaskRecord;
import cn.inkforge.core.db.generated.tables.records.VideoepisodemixversionRecord;
import cn.inkforge.core.db.generated.tables.records.VideoepisodesubtitlecueRecord;
import cn.inkforge.core.db.generated.tables.records.VideoshottakeRecord;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.video.application.CompletedEpisodeExport;
import cn.inkforge.core.video.application.EpisodeExportClaim;
import cn.inkforge.core.video.application.VideoAssetFile;
import cn.inkforge.core.video.application.VideoEpisodeExportManifest;
import cn.inkforge.core.video.application.VideoEpisodeExportManifest.FrozenAsset;
import cn.inkforge.core.video.application.VideoEpisodeExportManifest.FrozenAudioClip;
import cn.inkforge.core.video.application.VideoEpisodeExportManifest.FrozenSubtitleCue;
import cn.inkforge.core.video.application.VideoEpisodeExportManifest.FrozenVideoClip;
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
import tools.jackson.databind.ObjectMapper;

/**
 * 整集冻结清单、耐久 FFmpeg 任务和不可变成片的仓储。
 *
 * <p>创建时把镜头素材哈希、粗剪、声音字幕和输出参数冻结为 manifest；worker 只消费该清单，不回读当前
 * Head。失败重试复制原清单并创建新任务，成功成片也以新 VideoAsset 保存，绝不覆盖历史导出。
 */
final class JooqVideoExportRepository {

    private static final Set<String> ACTIVE = Set.of("pending", "rendering");

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final VideoEpisodeExportManifestCodec manifests;

    JooqVideoExportRepository(
            CoreDatabase database, CuidV1Generator ids, Clock clock, ObjectMapper json) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.manifests = new VideoEpisodeExportManifestCodec(json);
    }

    EpisodeExportTaskResponse createExportTask(
            String userId,
            String adaptationId,
            int episodeNo,
            StartEpisodeExportRequest request) {
        ExportStart input = exportStart(request);
        return database.transactionResult(transaction -> {
            // 导出命令先串行化再查重，确保一次用户动作只冻结一份渲染清单。
            VideoPostProductionCommands.lock(
                    transaction, "export", userId, input.clientRequestId());
            VideoepisodeexporttaskRecord existing = taskByRequest(
                    transaction, userId, input.clientRequestId());
            if (existing != null) {
                validateStartReplay(existing, adaptationId, episodeNo, input);
                return response(transaction, existing);
            }
            VideoPostProductionContext context =
                    VideoPostProductionDatabaseAccess.context(
                            transaction, userId, adaptationId, true);
            context.requireEpisode(episodeNo);
            String active = transaction.select(VIDEOEPISODEEXPORTTASK.ID)
                    .from(VIDEOEPISODEEXPORTTASK)
                    .where(
                            VIDEOEPISODEEXPORTTASK.EPISODEPLANVERSIONID.eq(
                                    context.episodePlan().getId()),
                            VIDEOEPISODEEXPORTTASK.EPISODENO.eq(episodeNo),
                            VIDEOEPISODEEXPORTTASK.STATUS.in(ACTIVE))
                    .fetchOne(VIDEOEPISODEEXPORTTASK.ID);
            if (active != null) {
                throw error(
                        409,
                        "VIDEO_EXPORT_TASK_ACTIVE",
                        "本集已有导出任务正在执行");
            }
            VideoEpisodeExportManifest manifest = buildManifest(
                    transaction, context, episodeNo, input);
            // worker 此后只能读取该 manifest；Take/Edit/Mix Head 的后续变化不影响本次导出。
            LocalDateTime now = DatabaseTimestamp.now(clock);
            String taskId = ids.next();
            transaction.insertInto(VIDEOEPISODEEXPORTTASK)
                    .set(VIDEOEPISODEEXPORTTASK.ID, taskId)
                    .set(VIDEOEPISODEEXPORTTASK.REQUESTEDBYUSERID, userId)
                    .set(VIDEOEPISODEEXPORTTASK.ADAPTATIONID, adaptationId)
                    .set(VIDEOEPISODEEXPORTTASK.PROJECTID, context.project().getId())
                    .set(VIDEOEPISODEEXPORTTASK.NOVELID, context.adaptation().getNovelid())
                    .set(VIDEOEPISODEEXPORTTASK.EPISODEPLANVERSIONID, context.episodePlan().getId())
                    .set(VIDEOEPISODEEXPORTTASK.SHOTPLANVERSIONID, context.planId())
                    .set(VIDEOEPISODEEXPORTTASK.EPISODENO, episodeNo)
                    .set(VIDEOEPISODEEXPORTTASK.EDITVERSIONID, manifest.editVersionId())
                    .set(VIDEOEPISODEEXPORTTASK.MIXVERSIONID, manifest.mixVersionId())
                    .set(VIDEOEPISODEEXPORTTASK.RETRYOFTASKID, (String) null)
                    .set(VIDEOEPISODEEXPORTTASK.CLIENTREQUESTID, input.clientRequestId())
                    .set(VIDEOEPISODEEXPORTTASK.STATUS, "pending")
                    .set(VIDEOEPISODEEXPORTTASK.INPUTHASH, manifests.hash(manifest))
                    .set(VIDEOEPISODEEXPORTTASK.REQUESTMANIFESTJSON, manifests.serialize(manifest))
                    .set(VIDEOEPISODEEXPORTTASK.RESOLUTION, input.resolution())
                    .set(VIDEOEPISODEEXPORTTASK.FRAMESPERSECOND, input.framesPerSecond())
                    .set(VIDEOEPISODEEXPORTTASK.BURNSUBTITLES, input.burnSubtitles())
                    .set(VIDEOEPISODEEXPORTTASK.ATTEMPTCOUNT, 0)
                    .set(VIDEOEPISODEEXPORTTASK.NEXTATTEMPTAT, now)
                    .set(VIDEOEPISODEEXPORTTASK.LASTERRORCODE, (String) null)
                    .set(VIDEOEPISODEEXPORTTASK.LASTERRORMESSAGE, (String) null)
                    .set(VIDEOEPISODEEXPORTTASK.CREATEDAT, now)
                    .set(VIDEOEPISODEEXPORTTASK.UPDATEDAT, now)
                    .set(VIDEOEPISODEEXPORTTASK.STARTEDAT, (LocalDateTime) null)
                    .set(VIDEOEPISODEEXPORTTASK.COMPLETEDAT, (LocalDateTime) null)
                    .execute();
            return response(transaction, requireTask(transaction, taskId));
        });
    }

    EpisodeExportTaskResponse retryExportTask(
            String userId, String taskId, RetryEpisodeExportRequest request) {
        String clientRequestId =
                VideoPostProductionCommands.requestId(request.getClientRequestId());
        return database.transactionResult(transaction -> {
            VideoPostProductionCommands.lock(
                    transaction, "export", userId, clientRequestId);
            VideoepisodeexporttaskRecord source =
                    ownedTask(transaction, userId, taskId, true);
            VideoepisodeexporttaskRecord existing =
                    taskByRequest(transaction, userId, clientRequestId);
            if (existing != null) {
                if (!source.getId().equals(existing.getRetryoftaskid())) {
                    throw error(
                            409,
                            "VIDEO_EXPORT_CLIENT_REQUEST_REUSED",
                            "clientRequestId 已用于另一条导出任务");
                }
                return response(transaction, existing);
            }
            if (!"failed".equals(source.getStatus())) {
                throw error(
                        409,
                        "VIDEO_EXPORT_TASK_NOT_RETRYABLE",
                        "只有失败的整集导出任务可以按原清单重试");
            }
            VideoPostProductionContext context =
                    VideoPostProductionDatabaseAccess.context(
                            transaction, userId, source.getAdaptationid(), true);
            if (!context.episodePlan().getId().equals(source.getEpisodeplanversionid())) {
                throw error(
                        409,
                        "VIDEO_EXPORT_RETRY_STALE_PLAN",
                        "原导出不属于当前正式分集方案，不能直接重试");
            }
            boolean active = transaction.fetchExists(transaction.selectOne()
                    .from(VIDEOEPISODEEXPORTTASK)
                    .where(
                            VIDEOEPISODEEXPORTTASK.EPISODEPLANVERSIONID.eq(
                                    source.getEpisodeplanversionid()),
                            VIDEOEPISODEEXPORTTASK.EPISODENO.eq(source.getEpisodeno()),
                            VIDEOEPISODEEXPORTTASK.STATUS.in(ACTIVE)));
            if (active) {
                throw error(
                        409,
                        "VIDEO_EXPORT_TASK_ACTIVE",
                        "本集已有导出任务正在执行");
            }
            // 显式重试复制原始 manifest，避免一次“重试”悄悄导出成另一版作品。
            VideoEpisodeExportManifest manifest = parse(source);
            LocalDateTime now = DatabaseTimestamp.now(clock);
            String retryId = ids.next();
            transaction.insertInto(VIDEOEPISODEEXPORTTASK)
                    .set(VIDEOEPISODEEXPORTTASK.ID, retryId)
                    .set(VIDEOEPISODEEXPORTTASK.REQUESTEDBYUSERID, userId)
                    .set(VIDEOEPISODEEXPORTTASK.ADAPTATIONID, source.getAdaptationid())
                    .set(VIDEOEPISODEEXPORTTASK.PROJECTID, source.getProjectid())
                    .set(VIDEOEPISODEEXPORTTASK.NOVELID, source.getNovelid())
                    .set(VIDEOEPISODEEXPORTTASK.EPISODEPLANVERSIONID, source.getEpisodeplanversionid())
                    .set(VIDEOEPISODEEXPORTTASK.SHOTPLANVERSIONID, source.getShotplanversionid())
                    .set(VIDEOEPISODEEXPORTTASK.EPISODENO, source.getEpisodeno())
                    .set(VIDEOEPISODEEXPORTTASK.EDITVERSIONID, source.getEditversionid())
                    .set(VIDEOEPISODEEXPORTTASK.MIXVERSIONID, source.getMixversionid())
                    .set(VIDEOEPISODEEXPORTTASK.RETRYOFTASKID, source.getId())
                    .set(VIDEOEPISODEEXPORTTASK.CLIENTREQUESTID, clientRequestId)
                    .set(VIDEOEPISODEEXPORTTASK.STATUS, "pending")
                    .set(VIDEOEPISODEEXPORTTASK.INPUTHASH, manifests.hash(manifest))
                    .set(VIDEOEPISODEEXPORTTASK.REQUESTMANIFESTJSON, source.getRequestmanifestjson())
                    .set(VIDEOEPISODEEXPORTTASK.RESOLUTION, source.getResolution())
                    .set(VIDEOEPISODEEXPORTTASK.FRAMESPERSECOND, source.getFramespersecond())
                    .set(VIDEOEPISODEEXPORTTASK.BURNSUBTITLES, source.getBurnsubtitles())
                    .set(VIDEOEPISODEEXPORTTASK.ATTEMPTCOUNT, 0)
                    .set(VIDEOEPISODEEXPORTTASK.NEXTATTEMPTAT, now)
                    .set(VIDEOEPISODEEXPORTTASK.CREATEDAT, now)
                    .set(VIDEOEPISODEEXPORTTASK.UPDATEDAT, now)
                    .execute();
            return response(transaction, requireTask(transaction, retryId));
        });
    }

    EpisodeExportTaskResponse getExportTask(String userId, String taskId) {
        return response(database.dsl(), ownedTask(database.dsl(), userId, taskId, false));
    }

    VideoAssetFile getExportFile(String userId, String exportId) {
        VideoassetRecord asset = database.dsl().select(VIDEOASSET.fields())
                .from(VIDEOASSET)
                .join(VIDEOEPISODEEXPORT)
                .on(VIDEOEPISODEEXPORT.ASSETID.eq(VIDEOASSET.ID))
                .join(VIDEOPROJECT)
                .on(VIDEOPROJECT.ID.eq(VIDEOEPISODEEXPORT.PROJECTID))
                .join(NOVEL)
                .on(NOVEL.ID.eq(VIDEOPROJECT.NOVELID))
                .where(VIDEOEPISODEEXPORT.ID.eq(exportId), NOVEL.USERID.eq(userId))
                .fetchOneInto(VideoassetRecord.class);
        if (asset == null) {
            throw error(
                    404,
                    "VIDEO_EPISODE_EXPORT_NOT_FOUND",
                    "整集导出不存在");
        }
        return new VideoAssetFile(asset.getStoragekey(), asset.getMimetype(), asset.getName());
    }

    List<EpisodeExportClaim> claimDueExportTasks(int limit) {
        if (limit < 1) throw new IllegalArgumentException("整集导出任务领取数量必须为正整数");
        LocalDateTime now = DatabaseTimestamp.now(clock);
        LocalDateTime lease = now.plusMinutes(30);
        return database.transactionResult(transaction -> {
            // 数据库行锁和租约共同保证同一耐久任务同一时刻只由一个 FFmpeg worker 执行。
            List<VideoepisodeexporttaskRecord> tasks = transaction
                    .selectFrom(VIDEOEPISODEEXPORTTASK)
                    .where(
                            VIDEOEPISODEEXPORTTASK.STATUS.in(ACTIVE),
                            VIDEOEPISODEEXPORTTASK.NEXTATTEMPTAT.le(now))
                    .orderBy(
                            VIDEOEPISODEEXPORTTASK.NEXTATTEMPTAT,
                            VIDEOEPISODEEXPORTTASK.CREATEDAT)
                    .limit(limit)
                    .forUpdate()
                    .skipLocked()
                    .fetch();
            List<EpisodeExportClaim> claims = new ArrayList<>();
            for (VideoepisodeexporttaskRecord task : tasks) {
                VideoEpisodeExportManifest manifest = parse(task);
                transaction.update(VIDEOEPISODEEXPORTTASK)
                        .set(VIDEOEPISODEEXPORTTASK.STATUS, "rendering")
                        .set(VIDEOEPISODEEXPORTTASK.ATTEMPTCOUNT, task.getAttemptcount() + 1)
                        .set(VIDEOEPISODEEXPORTTASK.NEXTATTEMPTAT, lease)
                        .set(VIDEOEPISODEEXPORTTASK.STARTEDAT,
                                task.getStartedat() == null ? now : task.getStartedat())
                        .set(VIDEOEPISODEEXPORTTASK.UPDATEDAT, now)
                        .where(VIDEOEPISODEEXPORTTASK.ID.eq(task.getId()))
                        .execute();
                claims.add(new EpisodeExportClaim(
                        task.getId(), task.getProjectid(), manifest));
            }
            return List.copyOf(claims);
        });
    }

    EpisodeExportTaskResponse completeExport(CompletedEpisodeExport completed) {
        return database.transactionResult(transaction -> {
            VideoepisodeexporttaskRecord task = transaction
                    .selectFrom(VIDEOEPISODEEXPORTTASK)
                    .where(VIDEOEPISODEEXPORTTASK.ID.eq(completed.taskId()))
                    .forUpdate()
                    .fetchOne();
            if (task == null) throw new IllegalStateException("整集导出任务不存在");
            VideoepisodeexportRecord existing = transaction.selectFrom(VIDEOEPISODEEXPORT)
                    .where(VIDEOEPISODEEXPORT.TASKID.eq(task.getId()))
                    .fetchOne();
            if (existing != null) return response(transaction, task);
            if (!"rendering".equals(task.getStatus())) {
                throw new IllegalStateException("整集导出任务不在渲染阶段");
            }
            if (!completed.assetId().equals("export_" + task.getId())) {
                throw new IllegalArgumentException("整集导出必须使用任务确定性素材标识");
            }
            Integer maximum = transaction
                    .select(DSL.coalesce(DSL.max(VIDEOEPISODEEXPORT.VERSIONNO), 0))
                    .from(VIDEOEPISODEEXPORT)
                    .where(
                            VIDEOEPISODEEXPORT.EPISODEPLANVERSIONID.eq(
                                    task.getEpisodeplanversionid()),
                            VIDEOEPISODEEXPORT.EPISODENO.eq(task.getEpisodeno()))
                    .fetchOne(0, Integer.class);
            int versionNo = (maximum == null ? 0 : maximum) + 1;
            LocalDateTime now = DatabaseTimestamp.now(clock);
            // 成片 Asset、不可变导出记录和任务终态必须原子落库，避免“文件存在但业务仍失败”的半完成状态。
            transaction.insertInto(VIDEOASSET)
                    .set(VIDEOASSET.ID, completed.assetId())
                    .set(VIDEOASSET.PROJECTID, task.getProjectid())
                    .set(VIDEOASSET.NAME, "第 " + task.getEpisodeno() + " 集 · 成片 v" + versionNo)
                    .set(VIDEOASSET.MODALITY, "video")
                    .set(VIDEOASSET.DUTY, "episode_export")
                    .set(VIDEOASSET.STORAGEKEY, completed.stored().storageKey())
                    .set(VIDEOASSET.MIMETYPE, completed.stored().mimeType())
                    .set(VIDEOASSET.BYTESIZE, completed.stored().byteSize())
                    .set(VIDEOASSET.DURATIONMS, completed.durationMs())
                    .set(VIDEOASSET.SHA256, completed.stored().sha256())
                    .set(VIDEOASSET.SOURCEKIND, "model_generated")
                    .set(VIDEOASSET.RIGHTSSTATUS, "confirmed")
                    .set(VIDEOASSET.LOCKEDAT, now)
                    .set(VIDEOASSET.CREATEDAT, now)
                    .set(VIDEOASSET.UPDATEDAT, now)
                    .execute();
            transaction.insertInto(VIDEOEPISODEEXPORT)
                    .set(VIDEOEPISODEEXPORT.ID, ids.next())
                    .set(VIDEOEPISODEEXPORT.TASKID, task.getId())
                    .set(VIDEOEPISODEEXPORT.ADAPTATIONID, task.getAdaptationid())
                    .set(VIDEOEPISODEEXPORT.PROJECTID, task.getProjectid())
                    .set(VIDEOEPISODEEXPORT.EPISODEPLANVERSIONID, task.getEpisodeplanversionid())
                    .set(VIDEOEPISODEEXPORT.EPISODENO, task.getEpisodeno())
                    .set(VIDEOEPISODEEXPORT.EDITVERSIONID, task.getEditversionid())
                    .set(VIDEOEPISODEEXPORT.MIXVERSIONID, task.getMixversionid())
                    .set(VIDEOEPISODEEXPORT.ASSETID, completed.assetId())
                    .set(VIDEOEPISODEEXPORT.VERSIONNO, versionNo)
                    .set(VIDEOEPISODEEXPORT.INPUTHASH, task.getInputhash())
                    .set(VIDEOEPISODEEXPORT.CREATEDAT, now)
                    .execute();
            transaction.update(VIDEOEPISODEEXPORTTASK)
                    .set(VIDEOEPISODEEXPORTTASK.STATUS, "succeeded")
                    .set(VIDEOEPISODEEXPORTTASK.LASTERRORCODE, (String) null)
                    .set(VIDEOEPISODEEXPORTTASK.LASTERRORMESSAGE, (String) null)
                    .set(VIDEOEPISODEEXPORTTASK.NEXTATTEMPTAT, now)
                    .set(VIDEOEPISODEEXPORTTASK.UPDATEDAT, now)
                    .set(VIDEOEPISODEEXPORTTASK.COMPLETEDAT, now)
                    .where(VIDEOEPISODEEXPORTTASK.ID.eq(task.getId()))
                    .execute();
            return response(transaction, requireTask(transaction, task.getId()));
        });
    }

    boolean failExport(String taskId, String code, String message) {
        return database.transactionResult(transaction -> {
            VideoepisodeexporttaskRecord task = transaction
                    .selectFrom(VIDEOEPISODEEXPORTTASK)
                    .where(VIDEOEPISODEEXPORTTASK.ID.eq(taskId))
                    .forUpdate()
                    .fetchOne();
            if (task == null || !"rendering".equals(task.getStatus())) return false;
            LocalDateTime now = DatabaseTimestamp.now(clock);
            transaction.update(VIDEOEPISODEEXPORTTASK)
                    .set(VIDEOEPISODEEXPORTTASK.STATUS, "failed")
                    .set(VIDEOEPISODEEXPORTTASK.LASTERRORCODE, code)
                    .set(VIDEOEPISODEEXPORTTASK.LASTERRORMESSAGE, message)
                    .set(VIDEOEPISODEEXPORTTASK.NEXTATTEMPTAT, now)
                    .set(VIDEOEPISODEEXPORTTASK.UPDATEDAT, now)
                    .set(VIDEOEPISODEEXPORTTASK.COMPLETEDAT, now)
                    .where(VIDEOEPISODEEXPORTTASK.ID.eq(taskId))
                    .execute();
            return true;
        });
    }

    private VideoEpisodeExportManifest buildManifest(
            DSLContext transaction,
            VideoPostProductionContext context,
            int episodeNo,
            ExportStart input) {
        VideoepisodeeditversionRecord edit = transaction
                .selectFrom(VIDEOEPISODEEDITVERSION)
                .where(
                        VIDEOEPISODEEDITVERSION.ID.eq(input.editVersionId()),
                        VIDEOEPISODEEDITVERSION.EPISODEPLANVERSIONID.eq(
                                context.episodePlan().getId()),
                        VIDEOEPISODEEDITVERSION.EPISODENO.eq(episodeNo))
                .fetchOne();
        VideoepisodemixversionRecord mix = transaction
                .selectFrom(VIDEOEPISODEMIXVERSION)
                .where(
                        VIDEOEPISODEMIXVERSION.ID.eq(input.mixVersionId()),
                        VIDEOEPISODEMIXVERSION.EPISODEPLANVERSIONID.eq(
                                context.episodePlan().getId()),
                        VIDEOEPISODEMIXVERSION.EPISODENO.eq(episodeNo))
                .fetchOne();
        if (edit == null || mix == null) {
            throw error(
                    404,
                    "VIDEO_EXPORT_VERSION_NOT_FOUND",
                    "导出引用的粗剪或声音字幕版本不存在");
        }
        if (!mix.getEditversionid().equals(edit.getId())) {
            throw error(
                    409,
                    "VIDEO_EXPORT_MIX_STALE",
                    "声音字幕版本不是基于所选粗剪，请先重新保存声音版本");
        }
        String ratio = context.project().getTargetaspectratio();
        if ("adaptive".equals(ratio)) {
            throw error(
                    409,
                    "VIDEO_EXPORT_FIXED_RATIO_REQUIRED",
                    "整集导出需要项目使用固定画幅，不能使用 adaptive");
        }
        if (!Set.of("16:9", "4:3", "1:1", "3:4", "9:16", "21:9").contains(ratio)) {
            throw error(
                    409,
                    "VIDEO_EXPORT_RATIO_INVALID",
                    "项目画幅无法用于整集导出");
        }
        List<VideoepisodeeditclipRecord> editClips = transaction
                .selectFrom(VIDEOEPISODEEDITCLIP)
                .where(VIDEOEPISODEEDITCLIP.EDITVERSIONID.eq(edit.getId()))
                .orderBy(VIDEOEPISODEEDITCLIP.ORDINAL)
                .fetch();
        if (editClips.isEmpty()
                || editClips.stream().anyMatch(clip -> clip.getTakeid() == null)) {
            throw error(
                    409,
                    "VIDEO_EXPORT_PLACEHOLDER_REMAINING",
                    "粗剪仍有未确认 Take 的占位镜头，不能导出正式成片");
        }
        List<String> takeIds = editClips.stream()
                .map(VideoepisodeeditclipRecord::getTakeid)
                .toList();
        Map<String, TakeAsset> takes = new HashMap<>();
        transaction.select(VIDEOSHOTTAKE.fields())
                .select(VIDEOASSET.fields())
                .from(VIDEOSHOTTAKE)
                .join(VIDEOASSET)
                .on(VIDEOASSET.ID.eq(VIDEOSHOTTAKE.ASSETID))
                .where(VIDEOSHOTTAKE.ID.in(takeIds))
                .fetch()
                .forEach(row -> {
                    VideoshottakeRecord take = row.into(VIDEOSHOTTAKE);
                    takes.put(take.getId(), new TakeAsset(take, row.into(VIDEOASSET)));
                });
        List<FrozenVideoClip> video = new ArrayList<>();
        for (VideoepisodeeditclipRecord clip : editClips) {
            TakeAsset pair = takes.get(clip.getTakeid());
            if (pair == null) {
                throw error(
                        409,
                        "VIDEO_EXPORT_TAKE_MISSING",
                        "粗剪引用的 Take 或受控视频素材已丢失");
            }
            requireLocked(pair.asset(), "video");
            video.add(new FrozenVideoClip(
                    clip.getOrdinal(),
                    clip.getShotid(),
                    pair.take().getId(),
                    frozen(pair.asset()),
                    clip.getSourceinms(),
                    clip.getSourceoutms(),
                    clip.getOutputdurationms(),
                    clip.getTransitionafter(),
                    clip.getTransitiondurationms()));
        }
        List<Record> audioRows = transaction.select(VIDEOEPISODEAUDIOCLIP.fields())
                .select(VIDEOASSET.fields())
                .from(VIDEOEPISODEAUDIOCLIP)
                .join(VIDEOASSET)
                .on(VIDEOASSET.ID.eq(VIDEOEPISODEAUDIOCLIP.ASSETID))
                .where(VIDEOEPISODEAUDIOCLIP.MIXVERSIONID.eq(mix.getId()))
                .orderBy(VIDEOEPISODEAUDIOCLIP.ORDINAL)
                .fetch();
        List<FrozenAudioClip> audio = new ArrayList<>();
        for (Record row : audioRows) {
            VideoepisodeaudioclipRecord clip = row.into(VIDEOEPISODEAUDIOCLIP);
            VideoassetRecord asset = row.into(VIDEOASSET);
            requireLocked(asset, "audio");
            audio.add(new FrozenAudioClip(
                    clip.getOrdinal(),
                    clip.getTrackkind(),
                    clip.getShotid(),
                    frozen(asset),
                    clip.getTimelinestartms(),
                    clip.getSourceinms(),
                    clip.getSourceoutms(),
                    clip.getGainmillibels(),
                    clip.getFadeinms(),
                    clip.getFadeoutms()));
        }
        List<FrozenSubtitleCue> subtitles = transaction
                .selectFrom(VIDEOEPISODESUBTITLECUE)
                .where(VIDEOEPISODESUBTITLECUE.MIXVERSIONID.eq(mix.getId()))
                .orderBy(VIDEOEPISODESUBTITLECUE.ORDINAL)
                .fetch()
                .stream()
                .map(cue -> new FrozenSubtitleCue(
                        cue.getOrdinal(),
                        cue.getShotid(),
                        cue.getStartms(),
                        cue.getEndms(),
                        cue.getSpeaker(),
                        cue.getText()))
                .toList();
        return new VideoEpisodeExportManifest(
                VideoEpisodeExportManifest.SCHEMA_VERSION,
                context.adaptation().getId(),
                context.project().getId(),
                context.adaptation().getNovelid(),
                context.episodePlan().getId(),
                context.planId(),
                episodeNo,
                edit.getId(),
                edit.getContenthash(),
                mix.getId(),
                mix.getContenthash(),
                ratio,
                input.resolution(),
                input.framesPerSecond(),
                input.burnSubtitles(),
                edit.getTotaldurationms(),
                video,
                audio,
                subtitles);
    }

    EpisodeExportTaskResponse response(
            DSLContext context, VideoepisodeexporttaskRecord task) {
        VideoepisodeexportRecord exported = context.selectFrom(VIDEOEPISODEEXPORT)
                .where(VIDEOEPISODEEXPORT.TASKID.eq(task.getId()))
                .fetchOne();
        EpisodeExportResponse exportResponse = null;
        if (exported != null) {
            VideoassetRecord asset = context.selectFrom(VIDEOASSET)
                    .where(VIDEOASSET.ID.eq(exported.getAssetid()))
                    .fetchOne();
            if (asset == null) {
                throw error(
                        409,
                        "VIDEO_EPISODE_EXPORT_ASSET_MISSING",
                        "整集导出的受控素材已丢失");
            }
            PostProductionAssetResponse assetResponse =
                    JooqVideoPostProductionRepository.assetResponse(asset)
                            .contentUrl("/api/v1/video/exports/" + exported.getId() + "/content");
            exportResponse = new EpisodeExportResponse(
                    assetResponse,
                    DatabaseTimestamp.api(exported.getCreatedat()),
                    exported.getEditversionid(),
                    exported.getEpisodeno(),
                    exported.getId(),
                    exported.getInputhash(),
                    exported.getMixversionid(),
                    exported.getVersionno());
        }
        return new EpisodeExportTaskResponse(
                task.getAdaptationid(),
                task.getAttemptcount(),
                task.getBurnsubtitles(),
                task.getClientrequestid(),
                DatabaseTimestamp.api(task.getCompletedat()),
                DatabaseTimestamp.api(task.getCreatedat()),
                task.getEditversionid(),
                task.getEpisodeno(),
                exportResponse,
                EpisodeExportTaskResponse.FramesPerSecondEnum.fromValue(
                        task.getFramespersecond()),
                task.getId(),
                task.getInputhash(),
                task.getLasterrorcode(),
                task.getLasterrormessage(),
                task.getMixversionid(),
                EpisodeExportTaskResponse.ResolutionEnum.fromValue(task.getResolution()),
                task.getRetryoftaskid(),
                DatabaseTimestamp.api(task.getStartedat()),
                EpisodeExportTaskResponse.StatusEnum.fromValue(task.getStatus()),
                DatabaseTimestamp.api(task.getUpdatedat()));
    }

    private VideoepisodeexporttaskRecord ownedTask(
            DSLContext context, String userId, String taskId, boolean lock) {
        String ownedId = context.select(VIDEOEPISODEEXPORTTASK.ID)
                .from(VIDEOEPISODEEXPORTTASK)
                .join(VIDEOPROJECT)
                .on(VIDEOPROJECT.ID.eq(VIDEOEPISODEEXPORTTASK.PROJECTID))
                .join(NOVEL)
                .on(NOVEL.ID.eq(VIDEOPROJECT.NOVELID))
                .where(VIDEOEPISODEEXPORTTASK.ID.eq(taskId), NOVEL.USERID.eq(userId))
                .fetchOne(VIDEOEPISODEEXPORTTASK.ID);
        if (ownedId == null) {
            throw error(404, "VIDEO_EXPORT_TASK_NOT_FOUND", "整集导出任务不存在");
        }
        var query = context.selectFrom(VIDEOEPISODEEXPORTTASK)
                .where(VIDEOEPISODEEXPORTTASK.ID.eq(ownedId));
        return lock ? query.forUpdate().fetchOne() : query.fetchOne();
    }

    private static VideoepisodeexporttaskRecord requireTask(
            DSLContext context, String taskId) {
        VideoepisodeexporttaskRecord task = context.selectFrom(VIDEOEPISODEEXPORTTASK)
                .where(VIDEOEPISODEEXPORTTASK.ID.eq(taskId))
                .fetchOne();
        if (task == null) throw new IllegalStateException("整集导出任务不存在");
        return task;
    }

    private static VideoepisodeexporttaskRecord taskByRequest(
            DSLContext context, String userId, String requestId) {
        return context.selectFrom(VIDEOEPISODEEXPORTTASK)
                .where(
                        VIDEOEPISODEEXPORTTASK.REQUESTEDBYUSERID.eq(userId),
                        VIDEOEPISODEEXPORTTASK.CLIENTREQUESTID.eq(requestId))
                .fetchOne();
    }

    private VideoEpisodeExportManifest parse(VideoepisodeexporttaskRecord task) {
        return manifests.parse(task.getRequestmanifestjson(), task.getInputhash());
    }

    private static void validateStartReplay(
            VideoepisodeexporttaskRecord task,
            String adaptationId,
            int episodeNo,
            ExportStart input) {
        if (!task.getAdaptationid().equals(adaptationId)
                || task.getEpisodeno() != episodeNo
                || !task.getEditversionid().equals(input.editVersionId())
                || !task.getMixversionid().equals(input.mixVersionId())
                || !task.getResolution().equals(input.resolution())
                || task.getFramespersecond() != input.framesPerSecond()
                || task.getBurnsubtitles() != input.burnSubtitles()) {
            throw error(
                    409,
                    "VIDEO_EXPORT_CLIENT_REQUEST_REUSED",
                    "clientRequestId 已用于不同的导出请求");
        }
    }

    private static ExportStart exportStart(StartEpisodeExportRequest request) {
        String clientRequestId =
                VideoPostProductionCommands.requestId(request.getClientRequestId());
        String editVersionId = text(request.getEditVersionId());
        String mixVersionId = text(request.getMixVersionId());
        String resolution = request.getResolution() == null
                ? null
                : request.getResolution().getValue();
        Integer fps = request.getFramesPerSecond() == null
                ? null
                : request.getFramesPerSecond().getValue();
        if (resolution == null
                || !Set.of("720p", "1080p").contains(resolution)
                || fps == null
                || !Set.of(24, 25, 30).contains(fps)
                || request.getBurnSubtitles() == null) {
            throw error(422, "VALIDATION_ERROR", "整集导出请求无效");
        }
        return new ExportStart(
                clientRequestId,
                editVersionId,
                mixVersionId,
                resolution,
                fps,
                request.getBurnSubtitles());
    }

    private static void requireLocked(VideoassetRecord asset, String modality) {
        if (!modality.equals(asset.getModality())
                || !"confirmed".equals(asset.getRightsstatus())
                || asset.getLockedat() == null) {
            throw error(
                    409,
                    "VIDEO_EXPORT_ASSET_NOT_READY",
                    "导出引用的素材不再处于已确认锁定状态");
        }
    }

    private static FrozenAsset frozen(VideoassetRecord asset) {
        return new FrozenAsset(
                asset.getId(),
                asset.getStoragekey(),
                asset.getSha256(),
                asset.getMimetype(),
                asset.getDurationms());
    }

    private static String text(String value) {
        if (value == null || value.isEmpty()) {
            throw error(422, "VALIDATION_ERROR", "文本字段不能为空");
        }
        return value;
    }

    private static ApiException error(int status, String code, String message) {
        return VideoPostProductionCommands.error(status, code, message);
    }

    private record ExportStart(
            String clientRequestId,
            String editVersionId,
            String mixVersionId,
            String resolution,
            int framesPerSecond,
            boolean burnSubtitles) {}

    private record TakeAsset(VideoshottakeRecord take, VideoassetRecord asset) {}
}
