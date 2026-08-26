package cn.inkforge.core.video.infrastructure;

import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.VIDEOASSET;
import static cn.inkforge.core.db.generated.Tables.VIDEOEPISODEAUDIOCLIP;
import static cn.inkforge.core.db.generated.Tables.VIDEOEPISODEEDITCLIP;
import static cn.inkforge.core.db.generated.Tables.VIDEOEPISODEEDITHEAD;
import static cn.inkforge.core.db.generated.Tables.VIDEOEPISODEEDITVERSION;
import static cn.inkforge.core.db.generated.Tables.VIDEOEPISODEMIXHEAD;
import static cn.inkforge.core.db.generated.Tables.VIDEOEPISODEMIXVERSION;
import static cn.inkforge.core.db.generated.Tables.VIDEOEPISODESUBTITLECUE;
import static cn.inkforge.core.db.generated.Tables.VIDEOPROJECT;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTTAKE;

import cn.inkforge.contracts.api.EpisodeAudioClipInput;
import cn.inkforge.contracts.api.EpisodeAudioClipResponse;
import cn.inkforge.contracts.api.EpisodeEditClipInput;
import cn.inkforge.contracts.api.EpisodeEditClipResponse;
import cn.inkforge.contracts.api.EpisodeEditHeadResponse;
import cn.inkforge.contracts.api.EpisodeEditVersionResponse;
import cn.inkforge.contracts.api.EpisodeMixHeadResponse;
import cn.inkforge.contracts.api.EpisodeMixVersionResponse;
import cn.inkforge.contracts.api.EpisodeSubtitleCueInput;
import cn.inkforge.contracts.api.EpisodeSubtitleCueResponse;
import cn.inkforge.contracts.api.SaveEpisodeEditVersionRequest;
import cn.inkforge.contracts.api.SaveEpisodeMixVersionRequest;
import cn.inkforge.core.db.generated.tables.records.VideoassetRecord;
import cn.inkforge.core.db.generated.tables.records.VideoepisodeaudioclipRecord;
import cn.inkforge.core.db.generated.tables.records.VideoepisodeeditclipRecord;
import cn.inkforge.core.db.generated.tables.records.VideoepisodeeditheadRecord;
import cn.inkforge.core.db.generated.tables.records.VideoepisodeeditversionRecord;
import cn.inkforge.core.db.generated.tables.records.VideoepisodemixheadRecord;
import cn.inkforge.core.db.generated.tables.records.VideoepisodemixversionRecord;
import cn.inkforge.core.db.generated.tables.records.VideoepisodesubtitlecueRecord;
import cn.inkforge.core.db.generated.tables.records.VideoshottakeRecord;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
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
 * 非破坏性粗剪及声音字幕不可变版本仓储。
 *
 * <p>每次保存都创建完整不可变版本并以 revision CAS 切换 Head。粗剪必须恰好覆盖本集正式镜头集合；声音
 * 版本固定引用一个粗剪版本，因此后续 Head 变化只能使旧版本过期，不能静默重新绑定素材或时间线。
 */
final class JooqVideoTimelineRepository {

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final ObjectMapper json;

    JooqVideoTimelineRepository(
            CoreDatabase database, CuidV1Generator ids, Clock clock, ObjectMapper json) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
    }

    EpisodeEditHeadResponse saveEditVersion(
            String userId,
            String adaptationId,
            int episodeNo,
            SaveEpisodeEditVersionRequest request) {
        EditInput input = editInput(request);
        Map<String, Object> requestPayload = new LinkedHashMap<>();
        requestPayload.put("adaptationId", adaptationId);
        requestPayload.put("episodeNo", episodeNo);
        requestPayload.put("clientRequestId", input.clientRequestId());
        requestPayload.put("expectedRevision", input.expectedRevision());
        requestPayload.put("basedOnVersionId", input.basedOnVersionId());
        requestPayload.put("clips", input.clips().stream().map(EditClip::map).toList());
        String requestHash = hash(requestPayload);
        return database.transactionResult(transaction -> {
            // 命令锁覆盖查重、校验、建版本和切 Head；同一 clientRequestId 只能产生一个不可变版本。
            VideoPostProductionCommands.lock(
                    transaction, "edit", userId, input.clientRequestId());
            VideoepisodeeditversionRecord existing = transaction
                    .selectFrom(VIDEOEPISODEEDITVERSION)
                    .where(
                            VIDEOEPISODEEDITVERSION.CREATEDBYUSERID.eq(userId),
                            VIDEOEPISODEEDITVERSION.CLIENTREQUESTID.eq(
                                    input.clientRequestId()))
                    .fetchOne();
            if (existing != null) {
                if (!existing.getRequesthash().equals(requestHash)) {
                    throw error(
                            409,
                            "VIDEO_EDIT_CLIENT_REQUEST_REUSED",
                            "clientRequestId 已用于不同的粗剪请求");
                }
                return editHeadResponse(
                        transaction,
                        existing.getEpisodeplanversionid(),
                        existing.getEpisodeno());
            }
            VideoPostProductionContext context =
                    VideoPostProductionDatabaseAccess.context(
                            transaction, userId, adaptationId, true);
            List<cn.inkforge.core.db.generated.tables.records.VideoshotRecord> episodeShots =
                    context.requireEpisode(episodeNo);
            Set<String> expectedShots = episodeShots.stream()
                    .map(cn.inkforge.core.db.generated.tables.records.VideoshotRecord::getId)
                    .collect(java.util.stream.Collectors.toSet());
            Set<String> suppliedShots = input.clips().stream()
                    .map(EditClip::shotId)
                    .collect(java.util.stream.Collectors.toSet());
            if (!suppliedShots.equals(expectedShots)
                    || input.clips().size() != episodeShots.size()) {
                throw error(
                        422,
                        "VIDEO_EDIT_SHOT_SET_MISMATCH",
                        "粗剪必须让本集每个正式镜头恰好出现一次");
            }
            // “恰好一次”是重建时间线的前提：不能漏镜头，也不能用重复镜头伪装完整集合。
            VideoepisodeeditheadRecord head = editHead(
                    transaction, context, episodeNo, true);
            if (head.getRevision() != input.expectedRevision()) {
                throw error(
                        409,
                        "VIDEO_EDIT_REVISION_CONFLICT",
                        "粗剪版本已经变化，请刷新后重新保存");
            }
            String basedOn = head.getCurrentversionid();
            if (input.basedOnVersionId() != null) {
                VideoepisodeeditversionRecord base = transaction
                        .selectFrom(VIDEOEPISODEEDITVERSION)
                        .where(
                                VIDEOEPISODEEDITVERSION.ID.eq(input.basedOnVersionId()),
                                VIDEOEPISODEEDITVERSION.EPISODEPLANVERSIONID.eq(
                                        context.episodePlan().getId()),
                                VIDEOEPISODEEDITVERSION.EPISODENO.eq(episodeNo))
                        .fetchOne();
                if (base == null) {
                    throw error(
                            404,
                            "VIDEO_EDIT_BASE_VERSION_NOT_FOUND",
                            "粗剪基线版本不存在或不属于当前分集");
                }
                basedOn = base.getId();
            }
            List<String> takeIds = input.clips().stream()
                    .map(EditClip::takeId)
                    .filter(Objects::nonNull)
                    .distinct()
                    .toList();
            Map<String, TakeAsset> takes = new HashMap<>();
            if (!takeIds.isEmpty()) {
                transaction.select(VIDEOSHOTTAKE.fields())
                        .select(VIDEOASSET.fields())
                        .from(VIDEOSHOTTAKE)
                        .join(VIDEOASSET)
                        .on(VIDEOASSET.ID.eq(VIDEOSHOTTAKE.ASSETID))
                        .where(VIDEOSHOTTAKE.ID.in(takeIds))
                        .fetch()
                        .forEach(row -> {
                            VideoshottakeRecord take = row.into(VIDEOSHOTTAKE);
                            takes.put(
                                    take.getId(),
                                    new TakeAsset(take, row.into(VIDEOASSET)));
                        });
            }
            int timelineStart = 0;
            List<NormalizedEditClip> normalized = new ArrayList<>();
            for (EditClip clip : input.clips()) {
                if (clip.takeId() != null) {
                    TakeAsset pair = takes.get(clip.takeId());
                    if (pair == null) {
                        throw error(
                                404,
                                "VIDEO_EDIT_TAKE_NOT_FOUND",
                                "粗剪引用的 Take 不存在");
                    }
                    if (!pair.take().getShotid().equals(clip.shotId())
                            || !pair.take()
                                    .getShotplanversionid()
                                    .equals(context.episodePlan().getShotplanversionid())) {
                        throw error(
                                422,
                                "VIDEO_EDIT_TAKE_SCOPE_INVALID",
                                "Take 必须属于同一正式镜头和镜头方案");
                    }
                    if (pair.asset().getDurationms() == null) {
                        throw error(
                                409,
                                "VIDEO_EDIT_TAKE_DURATION_REQUIRED",
                                "该 Take 缺少已知时长，暂不能进入非破坏性裁切");
                    }
                    if (clip.sourceInMs() == null || clip.sourceOutMs() == null) {
                        throw error(
                                422,
                                "VIDEO_EDIT_TRIM_REQUIRED",
                                "选择 Take 后必须设置源入点和出点");
                    }
                    if (clip.sourceOutMs() > pair.asset().getDurationms()) {
                        throw error(
                                422,
                                "VIDEO_EDIT_TRIM_OUT_OF_RANGE",
                                "粗剪出点超过 Take 实际时长");
                    }
                    if (clip.outputDurationMs()
                            != clip.sourceOutMs() - clip.sourceInMs()) {
                        throw error(
                                422,
                                "VIDEO_EDIT_DURATION_MISMATCH",
                                "真实 Take 的输出时长必须等于源出点减入点");
                    }
                }
                normalized.add(new NormalizedEditClip(clip, timelineStart));
                timelineStart = Math.addExact(timelineStart, clip.outputDurationMs());
            }
            Integer maximum = transaction
                    .select(DSL.coalesce(DSL.max(VIDEOEPISODEEDITVERSION.VERSIONNO), 0))
                    .from(VIDEOEPISODEEDITVERSION)
                    .where(
                            VIDEOEPISODEEDITVERSION.EPISODEPLANVERSIONID.eq(
                                    context.episodePlan().getId()),
                            VIDEOEPISODEEDITVERSION.EPISODENO.eq(episodeNo))
                    .fetchOne(0, Integer.class);
            int versionNo = (maximum == null ? 0 : maximum) + 1;
            Map<String, Object> content = new LinkedHashMap<>();
            content.put("episodePlanVersionId", context.episodePlan().getId());
            content.put("episodeNo", episodeNo);
            content.put(
                    "clips",
                    normalized.stream().map(NormalizedEditClip::map).toList());
            LocalDateTime now = DatabaseTimestamp.now(clock);
            String versionId = ids.next();
            // 先保存完整版本及 clip 明细，最后才推进 Head；事务失败时不会暴露半条时间线。
            transaction.insertInto(VIDEOEPISODEEDITVERSION)
                    .set(VIDEOEPISODEEDITVERSION.ID, versionId)
                    .set(VIDEOEPISODEEDITVERSION.ADAPTATIONID, adaptationId)
                    .set(VIDEOEPISODEEDITVERSION.PROJECTID, context.project().getId())
                    .set(VIDEOEPISODEEDITVERSION.NOVELID, context.adaptation().getNovelid())
                    .set(VIDEOEPISODEEDITVERSION.EPISODEPLANVERSIONID, context.episodePlan().getId())
                    .set(VIDEOEPISODEEDITVERSION.SHOTPLANVERSIONID, context.planId())
                    .set(VIDEOEPISODEEDITVERSION.EPISODENO, episodeNo)
                    .set(VIDEOEPISODEEDITVERSION.VERSIONNO, versionNo)
                    .set(VIDEOEPISODEEDITVERSION.BASEDONVERSIONID, basedOn)
                    .set(VIDEOEPISODEEDITVERSION.TOTALDURATIONMS, timelineStart)
                    .set(VIDEOEPISODEEDITVERSION.CLIENTREQUESTID, input.clientRequestId())
                    .set(VIDEOEPISODEEDITVERSION.REQUESTHASH, requestHash)
                    .set(VIDEOEPISODEEDITVERSION.CONTENTHASH, hash(content))
                    .set(VIDEOEPISODEEDITVERSION.CREATEDBYUSERID, userId)
                    .set(VIDEOEPISODEEDITVERSION.CREATEDAT, now)
                    .execute();
            int ordinal = 1;
            for (NormalizedEditClip item : normalized) {
                EditClip clip = item.clip();
                transaction.insertInto(VIDEOEPISODEEDITCLIP)
                        .set(VIDEOEPISODEEDITCLIP.EDITVERSIONID, versionId)
                        .set(VIDEOEPISODEEDITCLIP.SHOTPLANVERSIONID, context.planId())
                        .set(VIDEOEPISODEEDITCLIP.SHOTID, clip.shotId())
                        .set(VIDEOEPISODEEDITCLIP.TAKEID, clip.takeId())
                        .set(VIDEOEPISODEEDITCLIP.ORDINAL, ordinal++)
                        .set(VIDEOEPISODEEDITCLIP.SOURCEINMS, clip.sourceInMs())
                        .set(VIDEOEPISODEEDITCLIP.SOURCEOUTMS, clip.sourceOutMs())
                        .set(VIDEOEPISODEEDITCLIP.TIMELINESTARTMS, item.timelineStartMs())
                        .set(VIDEOEPISODEEDITCLIP.OUTPUTDURATIONMS, clip.outputDurationMs())
                        .set(VIDEOEPISODEEDITCLIP.TRANSITIONAFTER, clip.transitionAfter())
                        .set(VIDEOEPISODEEDITCLIP.TRANSITIONDURATIONMS, clip.transitionDurationMs())
                        .execute();
            }
            transaction.update(VIDEOEPISODEEDITHEAD)
                    .set(VIDEOEPISODEEDITHEAD.CURRENTVERSIONID, versionId)
                    .set(VIDEOEPISODEEDITHEAD.REVISION, head.getRevision() + 1)
                    .set(VIDEOEPISODEEDITHEAD.UPDATEDAT, now)
                    .where(
                            VIDEOEPISODEEDITHEAD.EPISODEPLANVERSIONID.eq(
                                    context.episodePlan().getId()),
                            VIDEOEPISODEEDITHEAD.EPISODENO.eq(episodeNo))
                    .execute();
            return editHeadResponse(
                    transaction, context.episodePlan().getId(), episodeNo);
        });
    }

    EpisodeEditVersionResponse getEditVersion(String userId, String versionId) {
        VideoepisodeeditversionRecord version = database.dsl()
                .select(VIDEOEPISODEEDITVERSION.fields())
                .from(VIDEOEPISODEEDITVERSION)
                .join(VIDEOPROJECT)
                .on(VIDEOPROJECT.ID.eq(VIDEOEPISODEEDITVERSION.PROJECTID))
                .join(NOVEL)
                .on(NOVEL.ID.eq(VIDEOPROJECT.NOVELID))
                .where(
                        VIDEOEPISODEEDITVERSION.ID.eq(versionId),
                        NOVEL.USERID.eq(userId))
                .fetchOneInto(VideoepisodeeditversionRecord.class);
        if (version == null) {
            throw error(404, "VIDEO_EDIT_VERSION_NOT_FOUND", "粗剪版本不存在");
        }
        return editVersionResponse(database.dsl(), version);
    }

    EpisodeMixHeadResponse saveMixVersion(
            String userId,
            String adaptationId,
            int episodeNo,
            SaveEpisodeMixVersionRequest request) {
        MixInput input = mixInput(request);
        Map<String, Object> requestPayload = new LinkedHashMap<>();
        requestPayload.put("adaptationId", adaptationId);
        requestPayload.put("episodeNo", episodeNo);
        requestPayload.put("clientRequestId", input.clientRequestId());
        requestPayload.put("expectedRevision", input.expectedRevision());
        requestPayload.put("basedOnVersionId", input.basedOnVersionId());
        requestPayload.put("editVersionId", input.editVersionId());
        requestPayload.put("audioClips", input.audioClips().stream().map(AudioClip::map).toList());
        requestPayload.put("subtitleCues", input.subtitleCues().stream().map(SubtitleCue::map).toList());
        String requestHash = hash(requestPayload);
        return database.transactionResult(transaction -> {
            VideoPostProductionCommands.lock(
                    transaction, "mix", userId, input.clientRequestId());
            VideoepisodemixversionRecord existing = transaction
                    .selectFrom(VIDEOEPISODEMIXVERSION)
                    .where(
                            VIDEOEPISODEMIXVERSION.CREATEDBYUSERID.eq(userId),
                            VIDEOEPISODEMIXVERSION.CLIENTREQUESTID.eq(
                                    input.clientRequestId()))
                    .fetchOne();
            if (existing != null) {
                if (!existing.getRequesthash().equals(requestHash)) {
                    throw error(
                            409,
                            "VIDEO_MIX_CLIENT_REQUEST_REUSED",
                            "clientRequestId 已用于不同的声音字幕请求");
                }
                return mixHeadResponse(
                        transaction,
                        existing.getEpisodeplanversionid(),
                        existing.getEpisodeno(),
                        null);
            }
            VideoPostProductionContext context =
                    VideoPostProductionDatabaseAccess.context(
                            transaction, userId, adaptationId, true);
            List<cn.inkforge.core.db.generated.tables.records.VideoshotRecord> episodeShots =
                    context.requireEpisode(episodeNo);
            Set<String> episodeShotIds = episodeShots.stream()
                    .map(cn.inkforge.core.db.generated.tables.records.VideoshotRecord::getId)
                    .collect(java.util.stream.Collectors.toSet());
            VideoepisodeeditversionRecord edit = transaction
                    .selectFrom(VIDEOEPISODEEDITVERSION)
                    .where(
                            VIDEOEPISODEEDITVERSION.ID.eq(input.editVersionId()),
                            VIDEOEPISODEEDITVERSION.EPISODEPLANVERSIONID.eq(
                                    context.episodePlan().getId()),
                            VIDEOEPISODEEDITVERSION.EPISODENO.eq(episodeNo),
                            VIDEOEPISODEEDITVERSION.ADAPTATIONID.eq(adaptationId))
                    .fetchOne();
            if (edit == null) {
                throw error(
                        404,
                        "VIDEO_MIX_EDIT_VERSION_NOT_FOUND",
                        "声音字幕所引用的粗剪版本不存在");
            }
            // Mix 永久绑定调用方选择的 editVersionId，不随当前粗剪 Head 自动漂移。
            VideoepisodemixheadRecord head = mixHead(
                    transaction, context, episodeNo, true);
            if (head.getRevision() != input.expectedRevision()) {
                throw error(
                        409,
                        "VIDEO_MIX_REVISION_CONFLICT",
                        "声音字幕版本已经变化，请刷新后重新保存");
            }
            String basedOn = head.getCurrentversionid();
            if (input.basedOnVersionId() != null) {
                VideoepisodemixversionRecord base = transaction
                        .selectFrom(VIDEOEPISODEMIXVERSION)
                        .where(
                                VIDEOEPISODEMIXVERSION.ID.eq(input.basedOnVersionId()),
                                VIDEOEPISODEMIXVERSION.EPISODEPLANVERSIONID.eq(
                                        context.episodePlan().getId()),
                                VIDEOEPISODEMIXVERSION.EPISODENO.eq(episodeNo))
                        .fetchOne();
                if (base == null) {
                    throw error(
                            404,
                            "VIDEO_MIX_BASE_VERSION_NOT_FOUND",
                            "声音字幕基线版本不存在或不属于当前分集");
                }
                basedOn = base.getId();
            }
            List<String> assetIds = input.audioClips().stream()
                    .map(AudioClip::assetId)
                    .distinct()
                    .toList();
            Map<String, VideoassetRecord> assets = new HashMap<>();
            if (!assetIds.isEmpty()) {
                transaction.selectFrom(VIDEOASSET)
                        .where(VIDEOASSET.ID.in(assetIds))
                        .fetch()
                        .forEach(asset -> assets.put(asset.getId(), asset));
            }
            for (AudioClip clip : input.audioClips()) {
                VideoassetRecord asset = assets.get(clip.assetId());
                if (asset == null
                        || !asset.getProjectid().equals(context.project().getId())
                        || !"audio".equals(asset.getModality())
                        || !Set.of("voice", "ambience", "sfx", "music")
                                .contains(asset.getDuty())
                        || !"confirmed".equals(asset.getRightsstatus())
                        || asset.getLockedat() == null) {
                    throw error(
                            409,
                            "VIDEO_MIX_AUDIO_ASSET_NOT_READY",
                            "音轨只能使用本项目已确认并锁定的音频素材");
                }
                if (asset.getDurationms() == null
                        || clip.sourceOutMs() > asset.getDurationms()) {
                    throw error(
                            422,
                            "VIDEO_MIX_AUDIO_RANGE_INVALID",
                            "音频片段出点超过素材的已知时长");
                }
                int audioEnd = Math.addExact(
                        clip.timelineStartMs(),
                        clip.sourceOutMs() - clip.sourceInMs());
                if (audioEnd > edit.getTotaldurationms()) {
                    throw error(
                            422,
                            "VIDEO_MIX_AUDIO_TIMELINE_OVERFLOW",
                            "音频片段超过粗剪总时长");
                }
                if (clip.shotId() != null && !episodeShotIds.contains(clip.shotId())) {
                    throw error(
                            422,
                            "VIDEO_MIX_AUDIO_SHOT_INVALID",
                            "音频片段引用了其他分集的镜头");
                }
            }
            for (SubtitleCue cue : input.subtitleCues()) {
                if (cue.endMs() > edit.getTotaldurationms()) {
                    throw error(
                            422,
                            "VIDEO_MIX_SUBTITLE_TIMELINE_OVERFLOW",
                            "字幕超过粗剪总时长");
                }
                if (cue.shotId() != null && !episodeShotIds.contains(cue.shotId())) {
                    throw error(
                            422,
                            "VIDEO_MIX_SUBTITLE_SHOT_INVALID",
                            "字幕引用了其他分集的镜头");
                }
            }
            Integer maximum = transaction
                    .select(DSL.coalesce(DSL.max(VIDEOEPISODEMIXVERSION.VERSIONNO), 0))
                    .from(VIDEOEPISODEMIXVERSION)
                    .where(
                            VIDEOEPISODEMIXVERSION.EPISODEPLANVERSIONID.eq(
                                    context.episodePlan().getId()),
                            VIDEOEPISODEMIXVERSION.EPISODENO.eq(episodeNo))
                    .fetchOne(0, Integer.class);
            int versionNo = (maximum == null ? 0 : maximum) + 1;
            Map<String, Object> content = new LinkedHashMap<>();
            content.put("episodePlanVersionId", context.episodePlan().getId());
            content.put("episodeNo", episodeNo);
            content.put("editVersionId", edit.getId());
            content.put("audioClips", input.audioClips().stream().map(AudioClip::map).toList());
            content.put("subtitleCues", input.subtitleCues().stream().map(SubtitleCue::map).toList());
            LocalDateTime now = DatabaseTimestamp.now(clock);
            String versionId = ids.next();
            transaction.insertInto(VIDEOEPISODEMIXVERSION)
                    .set(VIDEOEPISODEMIXVERSION.ID, versionId)
                    .set(VIDEOEPISODEMIXVERSION.ADAPTATIONID, adaptationId)
                    .set(VIDEOEPISODEMIXVERSION.PROJECTID, context.project().getId())
                    .set(VIDEOEPISODEMIXVERSION.NOVELID, context.adaptation().getNovelid())
                    .set(VIDEOEPISODEMIXVERSION.EPISODEPLANVERSIONID, context.episodePlan().getId())
                    .set(VIDEOEPISODEMIXVERSION.SHOTPLANVERSIONID, context.planId())
                    .set(VIDEOEPISODEMIXVERSION.EPISODENO, episodeNo)
                    .set(VIDEOEPISODEMIXVERSION.EDITVERSIONID, edit.getId())
                    .set(VIDEOEPISODEMIXVERSION.VERSIONNO, versionNo)
                    .set(VIDEOEPISODEMIXVERSION.BASEDONVERSIONID, basedOn)
                    .set(VIDEOEPISODEMIXVERSION.CLIENTREQUESTID, input.clientRequestId())
                    .set(VIDEOEPISODEMIXVERSION.REQUESTHASH, requestHash)
                    .set(VIDEOEPISODEMIXVERSION.CONTENTHASH, hash(content))
                    .set(VIDEOEPISODEMIXVERSION.CREATEDBYUSERID, userId)
                    .set(VIDEOEPISODEMIXVERSION.CREATEDAT, now)
                    .execute();
            int ordinal = 1;
            for (AudioClip clip : input.audioClips()) {
                transaction.insertInto(VIDEOEPISODEAUDIOCLIP)
                        .set(VIDEOEPISODEAUDIOCLIP.MIXVERSIONID, versionId)
                        .set(VIDEOEPISODEAUDIOCLIP.PROJECTID, context.project().getId())
                        .set(VIDEOEPISODEAUDIOCLIP.SHOTPLANVERSIONID, context.planId())
                        .set(VIDEOEPISODEAUDIOCLIP.ORDINAL, ordinal++)
                        .set(VIDEOEPISODEAUDIOCLIP.TRACKKIND, clip.trackKind())
                        .set(VIDEOEPISODEAUDIOCLIP.ASSETID, clip.assetId())
                        .set(VIDEOEPISODEAUDIOCLIP.SHOTID, clip.shotId())
                        .set(VIDEOEPISODEAUDIOCLIP.TIMELINESTARTMS, clip.timelineStartMs())
                        .set(VIDEOEPISODEAUDIOCLIP.SOURCEINMS, clip.sourceInMs())
                        .set(VIDEOEPISODEAUDIOCLIP.SOURCEOUTMS, clip.sourceOutMs())
                        .set(VIDEOEPISODEAUDIOCLIP.GAINMILLIBELS, clip.gainMillibels())
                        .set(VIDEOEPISODEAUDIOCLIP.FADEINMS, clip.fadeInMs())
                        .set(VIDEOEPISODEAUDIOCLIP.FADEOUTMS, clip.fadeOutMs())
                        .execute();
            }
            ordinal = 1;
            for (SubtitleCue cue : input.subtitleCues()) {
                transaction.insertInto(VIDEOEPISODESUBTITLECUE)
                        .set(VIDEOEPISODESUBTITLECUE.MIXVERSIONID, versionId)
                        .set(VIDEOEPISODESUBTITLECUE.SHOTPLANVERSIONID, context.planId())
                        .set(VIDEOEPISODESUBTITLECUE.ORDINAL, ordinal++)
                        .set(VIDEOEPISODESUBTITLECUE.SHOTID, cue.shotId())
                        .set(VIDEOEPISODESUBTITLECUE.STARTMS, cue.startMs())
                        .set(VIDEOEPISODESUBTITLECUE.ENDMS, cue.endMs())
                        .set(VIDEOEPISODESUBTITLECUE.SPEAKER, cue.speaker())
                        .set(VIDEOEPISODESUBTITLECUE.TEXT, cue.text())
                        .execute();
            }
            transaction.update(VIDEOEPISODEMIXHEAD)
                    .set(VIDEOEPISODEMIXHEAD.CURRENTVERSIONID, versionId)
                    .set(VIDEOEPISODEMIXHEAD.REVISION, head.getRevision() + 1)
                    .set(VIDEOEPISODEMIXHEAD.UPDATEDAT, now)
                    .where(
                            VIDEOEPISODEMIXHEAD.EPISODEPLANVERSIONID.eq(
                                    context.episodePlan().getId()),
                            VIDEOEPISODEMIXHEAD.EPISODENO.eq(episodeNo))
                    .execute();
            return mixHeadResponse(
                    transaction, context.episodePlan().getId(), episodeNo, edit.getId());
        });
    }

    EpisodeMixVersionResponse getMixVersion(String userId, String versionId) {
        VideoepisodemixversionRecord version = database.dsl()
                .select(VIDEOEPISODEMIXVERSION.fields())
                .from(VIDEOEPISODEMIXVERSION)
                .join(VIDEOPROJECT)
                .on(VIDEOPROJECT.ID.eq(VIDEOEPISODEMIXVERSION.PROJECTID))
                .join(NOVEL)
                .on(NOVEL.ID.eq(VIDEOPROJECT.NOVELID))
                .where(
                        VIDEOEPISODEMIXVERSION.ID.eq(versionId),
                        NOVEL.USERID.eq(userId))
                .fetchOneInto(VideoepisodemixversionRecord.class);
        if (version == null) {
            throw error(404, "VIDEO_MIX_VERSION_NOT_FOUND", "声音字幕版本不存在");
        }
        return mixVersionResponse(database.dsl(), version);
    }

    EpisodeEditHeadResponse editHeadResponse(
            DSLContext context, String episodePlanId, int episodeNo) {
        VideoepisodeeditheadRecord head = context.selectFrom(VIDEOEPISODEEDITHEAD)
                .where(
                        VIDEOEPISODEEDITHEAD.EPISODEPLANVERSIONID.eq(episodePlanId),
                        VIDEOEPISODEEDITHEAD.EPISODENO.eq(episodeNo))
                .fetchOne();
        if (head == null || head.getCurrentversionid() == null) {
            return new EpisodeEditHeadResponse(
                    null, episodeNo, episodePlanId, head == null ? 1 : head.getRevision());
        }
        VideoepisodeeditversionRecord version = context
                .selectFrom(VIDEOEPISODEEDITVERSION)
                .where(VIDEOEPISODEEDITVERSION.ID.eq(head.getCurrentversionid()))
                .fetchOne();
        if (version == null) {
            throw error(409, "VIDEO_EDIT_HEAD_INVALID", "当前粗剪版本指针无效");
        }
        return new EpisodeEditHeadResponse(
                editVersionResponse(context, version),
                episodeNo,
                episodePlanId,
                head.getRevision());
    }

    EpisodeMixHeadResponse mixHeadResponse(
            DSLContext context,
            String episodePlanId,
            int episodeNo,
            String currentEditId) {
        VideoepisodemixheadRecord head = context.selectFrom(VIDEOEPISODEMIXHEAD)
                .where(
                        VIDEOEPISODEMIXHEAD.EPISODEPLANVERSIONID.eq(episodePlanId),
                        VIDEOEPISODEMIXHEAD.EPISODENO.eq(episodeNo))
                .fetchOne();
        if (currentEditId == null) {
            VideoepisodeeditheadRecord editHead = context.selectFrom(VIDEOEPISODEEDITHEAD)
                    .where(
                            VIDEOEPISODEEDITHEAD.EPISODEPLANVERSIONID.eq(episodePlanId),
                            VIDEOEPISODEEDITHEAD.EPISODENO.eq(episodeNo))
                    .fetchOne();
            currentEditId = editHead == null ? null : editHead.getCurrentversionid();
        }
        if (head == null || head.getCurrentversionid() == null) {
            return new EpisodeMixHeadResponse(
                    null,
                    episodeNo,
                    episodePlanId,
                    head == null ? 1 : head.getRevision(),
                    false);
        }
        VideoepisodemixversionRecord version = context
                .selectFrom(VIDEOEPISODEMIXVERSION)
                .where(VIDEOEPISODEMIXVERSION.ID.eq(head.getCurrentversionid()))
                .fetchOne();
        if (version == null) {
            throw error(409, "VIDEO_MIX_HEAD_INVALID", "当前声音字幕版本指针无效");
        }
        return new EpisodeMixHeadResponse(
                mixVersionResponse(context, version),
                episodeNo,
                episodePlanId,
                head.getRevision(),
                currentEditId != null && !currentEditId.equals(version.getEditversionid()));
    }

    private VideoepisodeeditheadRecord editHead(
            DSLContext transaction,
            VideoPostProductionContext context,
            int episodeNo,
            boolean lock) {
        var query = transaction.selectFrom(VIDEOEPISODEEDITHEAD)
                .where(
                        VIDEOEPISODEEDITHEAD.EPISODEPLANVERSIONID.eq(
                                context.episodePlan().getId()),
                        VIDEOEPISODEEDITHEAD.EPISODENO.eq(episodeNo));
        VideoepisodeeditheadRecord head = lock ? query.forUpdate().fetchOne() : query.fetchOne();
        if (head != null) return head;
        LocalDateTime now = DatabaseTimestamp.now(clock);
        transaction.insertInto(VIDEOEPISODEEDITHEAD)
                .set(VIDEOEPISODEEDITHEAD.EPISODEPLANVERSIONID, context.episodePlan().getId())
                .set(VIDEOEPISODEEDITHEAD.SHOTPLANVERSIONID, context.planId())
                .set(VIDEOEPISODEEDITHEAD.ADAPTATIONID, context.adaptation().getId())
                .set(VIDEOEPISODEEDITHEAD.EPISODENO, episodeNo)
                .set(VIDEOEPISODEEDITHEAD.CURRENTVERSIONID, (String) null)
                .set(VIDEOEPISODEEDITHEAD.REVISION, 1)
                .set(VIDEOEPISODEEDITHEAD.UPDATEDAT, now)
                .execute();
        return transaction.selectFrom(VIDEOEPISODEEDITHEAD)
                .where(
                        VIDEOEPISODEEDITHEAD.EPISODEPLANVERSIONID.eq(
                                context.episodePlan().getId()),
                        VIDEOEPISODEEDITHEAD.EPISODENO.eq(episodeNo))
                .forUpdate()
                .fetchOne();
    }

    private VideoepisodemixheadRecord mixHead(
            DSLContext transaction,
            VideoPostProductionContext context,
            int episodeNo,
            boolean lock) {
        var query = transaction.selectFrom(VIDEOEPISODEMIXHEAD)
                .where(
                        VIDEOEPISODEMIXHEAD.EPISODEPLANVERSIONID.eq(
                                context.episodePlan().getId()),
                        VIDEOEPISODEMIXHEAD.EPISODENO.eq(episodeNo));
        VideoepisodemixheadRecord head = lock ? query.forUpdate().fetchOne() : query.fetchOne();
        if (head != null) return head;
        LocalDateTime now = DatabaseTimestamp.now(clock);
        transaction.insertInto(VIDEOEPISODEMIXHEAD)
                .set(VIDEOEPISODEMIXHEAD.EPISODEPLANVERSIONID, context.episodePlan().getId())
                .set(VIDEOEPISODEMIXHEAD.SHOTPLANVERSIONID, context.planId())
                .set(VIDEOEPISODEMIXHEAD.ADAPTATIONID, context.adaptation().getId())
                .set(VIDEOEPISODEMIXHEAD.EPISODENO, episodeNo)
                .set(VIDEOEPISODEMIXHEAD.CURRENTVERSIONID, (String) null)
                .set(VIDEOEPISODEMIXHEAD.REVISION, 1)
                .set(VIDEOEPISODEMIXHEAD.UPDATEDAT, now)
                .execute();
        return transaction.selectFrom(VIDEOEPISODEMIXHEAD)
                .where(
                        VIDEOEPISODEMIXHEAD.EPISODEPLANVERSIONID.eq(
                                context.episodePlan().getId()),
                        VIDEOEPISODEMIXHEAD.EPISODENO.eq(episodeNo))
                .forUpdate()
                .fetchOne();
    }

    private static EpisodeEditVersionResponse editVersionResponse(
            DSLContext context, VideoepisodeeditversionRecord version) {
        List<EpisodeEditClipResponse> clips = context.selectFrom(VIDEOEPISODEEDITCLIP)
                .where(VIDEOEPISODEEDITCLIP.EDITVERSIONID.eq(version.getId()))
                .orderBy(VIDEOEPISODEEDITCLIP.ORDINAL)
                .fetch()
                .stream()
                .map(JooqVideoTimelineRepository::editClipResponse)
                .toList();
        return new EpisodeEditVersionResponse(
                version.getAdaptationid(),
                version.getBasedonversionid(),
                clips,
                version.getContenthash(),
                DatabaseTimestamp.api(version.getCreatedat()),
                version.getEpisodeno(),
                version.getEpisodeplanversionid(),
                version.getId(),
                version.getShotplanversionid(),
                version.getTotaldurationms(),
                version.getVersionno());
    }

    private static EpisodeEditClipResponse editClipResponse(
            VideoepisodeeditclipRecord clip) {
        return new EpisodeEditClipResponse(
                        clip.getOrdinal(),
                        clip.getOutputdurationms(),
                        clip.getShotid(),
                        clip.getTimelinestartms())
                .takeId(clip.getTakeid())
                .sourceInMs(clip.getSourceinms())
                .sourceOutMs(clip.getSourceoutms())
                .transitionAfter(EpisodeEditClipResponse.TransitionAfterEnum.fromValue(
                        clip.getTransitionafter()))
                .transitionDurationMs(clip.getTransitiondurationms());
    }

    private static EpisodeMixVersionResponse mixVersionResponse(
            DSLContext context, VideoepisodemixversionRecord version) {
        List<Record> audioRows = context.select(VIDEOEPISODEAUDIOCLIP.fields())
                .select(VIDEOASSET.fields())
                .from(VIDEOEPISODEAUDIOCLIP)
                .join(VIDEOASSET)
                .on(VIDEOASSET.ID.eq(VIDEOEPISODEAUDIOCLIP.ASSETID))
                .where(VIDEOEPISODEAUDIOCLIP.MIXVERSIONID.eq(version.getId()))
                .orderBy(VIDEOEPISODEAUDIOCLIP.ORDINAL)
                .fetch();
        List<EpisodeAudioClipResponse> audio = audioRows.stream()
                .map(row -> audioResponse(
                        row.into(VIDEOEPISODEAUDIOCLIP), row.into(VIDEOASSET)))
                .toList();
        List<EpisodeSubtitleCueResponse> subtitles = context
                .selectFrom(VIDEOEPISODESUBTITLECUE)
                .where(VIDEOEPISODESUBTITLECUE.MIXVERSIONID.eq(version.getId()))
                .orderBy(VIDEOEPISODESUBTITLECUE.ORDINAL)
                .fetch()
                .stream()
                .map(JooqVideoTimelineRepository::subtitleResponse)
                .toList();
        return new EpisodeMixVersionResponse(
                version.getAdaptationid(),
                audio,
                version.getBasedonversionid(),
                version.getContenthash(),
                DatabaseTimestamp.api(version.getCreatedat()),
                version.getEditversionid(),
                version.getEpisodeno(),
                version.getEpisodeplanversionid(),
                version.getId(),
                version.getShotplanversionid(),
                subtitles,
                version.getVersionno());
    }

    private static EpisodeAudioClipResponse audioResponse(
            VideoepisodeaudioclipRecord clip, VideoassetRecord asset) {
        return new EpisodeAudioClipResponse(
                        JooqVideoPostProductionRepository.assetResponse(asset),
                        clip.getAssetid(),
                        clip.getOrdinal(),
                        clip.getSourceoutms(),
                        clip.getTimelinestartms(),
                        EpisodeAudioClipResponse.TrackKindEnum.fromValue(
                                clip.getTrackkind()))
                .shotId(clip.getShotid())
                .sourceInMs(clip.getSourceinms())
                .gainMillibels(clip.getGainmillibels())
                .fadeInMs(clip.getFadeinms())
                .fadeOutMs(clip.getFadeoutms());
    }

    private static EpisodeSubtitleCueResponse subtitleResponse(
            VideoepisodesubtitlecueRecord cue) {
        return new EpisodeSubtitleCueResponse(
                        cue.getEndms(), cue.getOrdinal(), cue.getStartms(), cue.getText())
                .shotId(cue.getShotid())
                .speaker(cue.getSpeaker());
    }

    private static EditInput editInput(SaveEpisodeEditVersionRequest request) {
        String requestId = VideoPostProductionCommands.requestId(request.getClientRequestId());
        String basedOn = nullable(request.getBasedOnVersionId());
        List<EpisodeEditClipInput> supplied = request.getClips();
        if (request.getExpectedRevision() == null
                || request.getExpectedRevision() < 1
                || supplied == null
                || supplied.isEmpty()
                || supplied.size() > 500) {
            throw validation("粗剪请求无效");
        }
        List<EditClip> clips = supplied.stream()
                .map(JooqVideoTimelineRepository::editClip)
                .toList();
        if (clips.stream().map(EditClip::shotId).distinct().count() != clips.size()) {
            throw validation("同一粗剪版本中镜头不能重复");
        }
        return new EditInput(
                requestId, request.getExpectedRevision(), basedOn, clips);
    }

    private static EditClip editClip(EpisodeEditClipInput input) {
        String shotId = text(input.getShotId());
        String takeId = nullable(input.getTakeId());
        Integer sourceIn = nullable(input.getSourceInMs());
        Integer sourceOut = nullable(input.getSourceOutMs());
        Integer duration = input.getOutputDurationMs();
        String transition = input.getTransitionAfter() == null
                ? null
                : input.getTransitionAfter().getValue();
        Integer transitionDuration = input.getTransitionDurationMs();
        boolean invalidTrim = takeId == null
                ? sourceIn != null || sourceOut != null
                : sourceIn == null || sourceOut == null || sourceOut <= sourceIn;
        if (duration == null
                || duration < 500
                || duration > 120_000
                || transition == null
                || !Set.of("cut", "fade_black").contains(transition)
                || transitionDuration == null
                || transitionDuration < 0
                || transitionDuration > 2_000
                || invalidTrim
                || "cut".equals(transition) && transitionDuration != 0
                || "fade_black".equals(transition) && transitionDuration == 0
                || transitionDuration * 2 > duration) {
            throw validation("粗剪片段无效");
        }
        return new EditClip(
                shotId,
                takeId,
                sourceIn,
                sourceOut,
                duration,
                transition,
                transitionDuration);
    }

    private static MixInput mixInput(SaveEpisodeMixVersionRequest request) {
        String requestId = VideoPostProductionCommands.requestId(request.getClientRequestId());
        String basedOn = nullable(request.getBasedOnVersionId());
        String editVersionId = text(request.getEditVersionId());
        List<EpisodeAudioClipInput> audioInput =
                request.getAudioClips() == null ? List.of() : request.getAudioClips();
        List<EpisodeSubtitleCueInput> subtitleInput =
                request.getSubtitleCues() == null ? List.of() : request.getSubtitleCues();
        if (request.getExpectedRevision() == null
                || request.getExpectedRevision() < 1
                || audioInput.size() > 1_000
                || subtitleInput.size() > 2_000) {
            throw validation("声音字幕请求无效");
        }
        return new MixInput(
                requestId,
                request.getExpectedRevision(),
                basedOn,
                editVersionId,
                audioInput.stream().map(JooqVideoTimelineRepository::audioClip).toList(),
                subtitleInput.stream().map(JooqVideoTimelineRepository::subtitleCue).toList());
    }

    private static AudioClip audioClip(EpisodeAudioClipInput input) {
        String track = input.getTrackKind() == null
                ? null
                : input.getTrackKind().getValue();
        String assetId = text(input.getAssetId());
        String shotId = nullable(input.getShotId());
        Integer timeline = input.getTimelineStartMs();
        Integer sourceIn = input.getSourceInMs();
        Integer sourceOut = input.getSourceOutMs();
        Integer gain = input.getGainMillibels();
        Integer fadeIn = input.getFadeInMs();
        Integer fadeOut = input.getFadeOutMs();
        int duration = sourceIn == null || sourceOut == null ? -1 : sourceOut - sourceIn;
        if (track == null
                || !Set.of("dialogue", "narration", "ambience", "sfx", "music").contains(track)
                || timeline == null
                || timeline < 0
                || sourceIn == null
                || sourceIn < 0
                || sourceOut == null
                || sourceOut <= 0
                || duration <= 0
                || gain == null
                || gain < -6_000
                || gain > 1_200
                || fadeIn == null
                || fadeIn < 0
                || fadeIn > 10_000
                || fadeOut == null
                || fadeOut < 0
                || fadeOut > 10_000
                || fadeIn + fadeOut > duration) {
            throw validation("音频片段无效");
        }
        return new AudioClip(
                track,
                assetId,
                shotId,
                timeline,
                sourceIn,
                sourceOut,
                gain,
                fadeIn,
                fadeOut);
    }

    private static SubtitleCue subtitleCue(EpisodeSubtitleCueInput input) {
        String shotId = nullable(input.getShotId());
        String speaker = nullable(input.getSpeaker());
        String text = text(input.getText());
        if (input.getStartMs() == null
                || input.getStartMs() < 0
                || input.getEndMs() == null
                || input.getEndMs() <= input.getStartMs()
                || text.codePointCount(0, text.length()) > 2_000
                || speaker != null && speaker.codePointCount(0, speaker.length()) > 120) {
            throw validation("字幕片段无效");
        }
        return new SubtitleCue(
                shotId, input.getStartMs(), input.getEndMs(), speaker, text);
    }

    private String hash(Object value) {
        return VideoPostProductionCommands.hash(value, json);
    }

    private static String text(String value) {
        if (value == null || value.isEmpty()) throw validation("文本字段不能为空");
        return value;
    }

    private static <T> T nullable(JsonNullable<T> value) {
        return value == null || value.isUndefined() ? null : value.orElse(null);
    }

    private static ApiException validation(String message) {
        return error(422, "VALIDATION_ERROR", message);
    }

    private static ApiException error(int status, String code, String message) {
        return VideoPostProductionCommands.error(status, code, message);
    }

    private record TakeAsset(VideoshottakeRecord take, VideoassetRecord asset) {}

    private record EditInput(
            String clientRequestId,
            int expectedRevision,
            String basedOnVersionId,
            List<EditClip> clips) {}

    private record EditClip(
            String shotId,
            String takeId,
            Integer sourceInMs,
            Integer sourceOutMs,
            int outputDurationMs,
            String transitionAfter,
            int transitionDurationMs) {

        Map<String, Object> map() {
            Map<String, Object> value = new LinkedHashMap<>();
            value.put("shotId", shotId);
            value.put("takeId", takeId);
            value.put("sourceInMs", sourceInMs);
            value.put("sourceOutMs", sourceOutMs);
            value.put("outputDurationMs", outputDurationMs);
            value.put("transitionAfter", transitionAfter);
            value.put("transitionDurationMs", transitionDurationMs);
            return value;
        }
    }

    private record NormalizedEditClip(EditClip clip, int timelineStartMs) {

        Map<String, Object> map() {
            Map<String, Object> value = new LinkedHashMap<>(clip.map());
            value.put("timelineStartMs", timelineStartMs);
            return value;
        }
    }

    private record MixInput(
            String clientRequestId,
            int expectedRevision,
            String basedOnVersionId,
            String editVersionId,
            List<AudioClip> audioClips,
            List<SubtitleCue> subtitleCues) {}

    private record AudioClip(
            String trackKind,
            String assetId,
            String shotId,
            int timelineStartMs,
            int sourceInMs,
            int sourceOutMs,
            int gainMillibels,
            int fadeInMs,
            int fadeOutMs) {

        Map<String, Object> map() {
            Map<String, Object> value = new LinkedHashMap<>();
            value.put("trackKind", trackKind);
            value.put("assetId", assetId);
            value.put("shotId", shotId);
            value.put("timelineStartMs", timelineStartMs);
            value.put("sourceInMs", sourceInMs);
            value.put("sourceOutMs", sourceOutMs);
            value.put("gainMillibels", gainMillibels);
            value.put("fadeInMs", fadeInMs);
            value.put("fadeOutMs", fadeOutMs);
            return value;
        }
    }

    private record SubtitleCue(
            String shotId, int startMs, int endMs, String speaker, String text) {

        Map<String, Object> map() {
            Map<String, Object> value = new LinkedHashMap<>();
            value.put("shotId", shotId);
            value.put("startMs", startMs);
            value.put("endMs", endMs);
            value.put("speaker", speaker);
            value.put("text", text);
            return value;
        }
    }
}
