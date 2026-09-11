package cn.inkforge.core.video.infrastructure;

import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.video.application.CompletedEpisodeExport;
import cn.inkforge.core.video.application.EpisodeExportClaim;
import cn.inkforge.core.video.application.VideoAssetFile;
import cn.inkforge.core.video.application.VideoEpisodeExportManifest;
import cn.inkforge.core.video.application.VideoEpisodeExportManifest.FfmpegSettings;
import cn.inkforge.core.video.application.VideoEpisodeExportManifest.FrozenAsset;
import cn.inkforge.core.video.application.VideoEpisodeExportManifest.FrozenAudioClip;
import cn.inkforge.core.video.application.VideoEpisodeExportManifest.FrozenSubtitleCue;
import cn.inkforge.core.video.application.VideoEpisodeExportManifest.FrozenVideoClip;
import cn.inkforge.core.video.application.VideoEpisodePostProductionRepository;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.jooq.DSLContext;
import org.jooq.Record;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

/**
 * 独立分集后期仓储。
 *
 * <p>粗剪和混音只追加版本并分别更新基线级 head。导出创建时冻结全部媒体哈希和 FFmpeg 参数，worker 不再读取
 * 当前 head；旧基线因此可以明确重导出而不会混入新版制作事实。
 */
public final class JooqVideoEpisodePostProductionRepository
        implements VideoEpisodePostProductionRepository {
    private static final Set<String> TRACK_KINDS =
            Set.of("dialogue", "narration", "ambience", "sfx", "music");
    private static final Set<String> ACTIVE_EXPORT = Set.of("pending", "rendering");

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final ObjectMapper json;
    private final VideoEpisodeExportManifestCodec manifests;

    public JooqVideoEpisodePostProductionRepository(
            CoreDatabase database, CuidV1Generator ids, Clock clock, ObjectMapper json) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
        this.manifests = new VideoEpisodeExportManifestCodec(json);
    }

    @Override
    public ObjectNode createEditVersion(
            String userId, String episodeId, String baselineId, JsonNode request) {
        return write(
                userId,
                episodeId,
                "episode.edit-version.create",
                commandRequest(request, baselineId, null),
                (tx, episode) -> createEdit(tx, episode, baselineId, userId, request));
    }

    @Override
    public ObjectNode listEditVersions(
            String userId,
            String episodeId,
            String baselineId,
            Integer beforeVersionNo,
            int limit) {
        return read(
                userId,
                episodeId,
                (tx, episode) -> {
                    requireBaseline(tx, episode, baselineId);
                    Record head = ensureEditHead(tx, episodeId, baselineId, false);
                    List<Record> rows =
                            beforeVersionNo == null
                                    ? tx.fetch(
                                            editSummarySql("")
                                                    + " ORDER BY v.\"versionNo\" DESC LIMIT ?",
                                            episodeId,
                                            baselineId,
                                            checkedLimit(limit) + 1)
                                    : tx.fetch(
                                            editSummarySql(" AND v.\"versionNo\"<?")
                                                    + " ORDER BY v.\"versionNo\" DESC LIMIT ?",
                                            episodeId,
                                            baselineId,
                                            beforeVersionNo,
                                            checkedLimit(limit) + 1);
                    return versionPage(
                            "versions",
                            episodeId,
                            baselineId,
                            head,
                            rows,
                            checkedLimit(limit),
                            this::editSummary);
                });
    }

    @Override
    public ObjectNode getEditVersion(
            String userId, String episodeId, String baselineId, String versionId) {
        return read(
                userId,
                episodeId,
                (tx, episode) -> {
                    requireBaseline(tx, episode, baselineId);
                    return editVersion(tx, episodeId, baselineId, versionId);
                });
    }

    @Override
    public ObjectNode createMixVersion(
            String userId, String episodeId, String baselineId, JsonNode request) {
        return write(
                userId,
                episodeId,
                "episode.mix-version.create",
                commandRequest(request, baselineId, null),
                (tx, episode) -> createMix(tx, episode, baselineId, userId, request));
    }

    @Override
    public ObjectNode listMixVersions(
            String userId,
            String episodeId,
            String baselineId,
            Integer beforeVersionNo,
            int limit) {
        return read(
                userId,
                episodeId,
                (tx, episode) -> {
                    requireBaseline(tx, episode, baselineId);
                    Record head = ensureMixHead(tx, episodeId, baselineId, false);
                    List<Record> rows =
                            beforeVersionNo == null
                                    ? tx.fetch(
                                            mixSummarySql("")
                                                    + " ORDER BY v.\"versionNo\" DESC LIMIT ?",
                                            episodeId,
                                            baselineId,
                                            checkedLimit(limit) + 1)
                                    : tx.fetch(
                                            mixSummarySql(" AND v.\"versionNo\"<?")
                                                    + " ORDER BY v.\"versionNo\" DESC LIMIT ?",
                                            episodeId,
                                            baselineId,
                                            beforeVersionNo,
                                            checkedLimit(limit) + 1);
                    return versionPage(
                            "versions",
                            episodeId,
                            baselineId,
                            head,
                            rows,
                            checkedLimit(limit),
                            this::mixSummary);
                });
    }

    @Override
    public ObjectNode getMixVersion(
            String userId, String episodeId, String baselineId, String versionId) {
        return read(
                userId,
                episodeId,
                (tx, episode) -> {
                    requireBaseline(tx, episode, baselineId);
                    return mixVersion(tx, episodeId, baselineId, versionId);
                });
    }

    @Override
    public ObjectNode createExportTask(
            String userId, String episodeId, String baselineId, JsonNode request) {
        return write(
                userId,
                episodeId,
                "episode.export-task.start",
                commandRequest(request, baselineId, null),
                (tx, episode) ->
                        createExport(tx, episode, baselineId, userId, request, null));
    }

    @Override
    public ObjectNode retryExportTask(
            String userId,
            String episodeId,
            String baselineId,
            String taskId,
            JsonNode request) {
        return write(
                userId,
                episodeId,
                "episode.export-task.retry",
                commandRequest(request, baselineId, taskId),
                (tx, episode) ->
                        retryExport(tx, episode, baselineId, taskId, userId, request));
    }

    @Override
    public ObjectNode getExportTask(
            String userId, String episodeId, String baselineId, String taskId) {
        return read(
                userId,
                episodeId,
                (tx, episode) -> exportTask(tx, episodeId, baselineId, taskId));
    }

    @Override
    public ObjectNode getDelivery(
            String userId, String episodeId, String baselineId, String exportId) {
        return read(
                userId,
                episodeId,
                (tx, episode) -> delivery(tx, episodeId, baselineId, exportId));
    }

    @Override
    public VideoAssetFile getDeliveryFile(
            String userId, String episodeId, String baselineId, String exportId) {
        return database.transactionResult(
                tx -> {
                    Record episode = owned(tx, userId, episodeId, false);
                    requireBaseline(tx, episode, baselineId);
                    Record row = deliveryRecord(tx, episodeId, baselineId, exportId);
                    return new VideoAssetFile(
                            row.get("storageKey", String.class),
                            row.get("mimeType", String.class),
                            row.get("name", String.class));
                });
    }

    @Override
    public List<EpisodeExportClaim> claimDueExportTasks(int limit) {
        if (limit < 1) throw new IllegalArgumentException("导出任务领取数量必须为正整数");
        LocalDateTime now = now();
        LocalDateTime lease = now.plusMinutes(30);
        return database.transactionResult(
                tx -> {
                    List<Record> tasks =
                            tx.fetch(
                                    "SELECT * FROM \"VideoEpisodeExportTask\" WHERE"
                                            + " \"videoEpisodeId\" IS NOT NULL AND status IN"
                                            + " ('pending','rendering') AND \"nextAttemptAt\"<=?"
                                            + " ORDER BY \"nextAttemptAt\",\"createdAt\" LIMIT ?"
                                            + " FOR UPDATE SKIP LOCKED",
                                    now,
                                    limit);
                    List<EpisodeExportClaim> claims = new ArrayList<>();
                    for (Record task : tasks) {
                        VideoEpisodeExportManifest manifest =
                                manifests.parse(
                                        task.get("requestManifestJson", String.class),
                                        task.get("inputHash", String.class));
                        tx.execute(
                                "UPDATE \"VideoEpisodeExportTask\" SET status='rendering',"
                                        + " \"attemptCount\"=\"attemptCount\"+1,"
                                        + " \"nextAttemptAt\"=?,\"startedAt\"=COALESCE(\"startedAt\",?),"
                                        + " \"updatedAt\"=? WHERE id=?",
                                lease,
                                now,
                                now,
                                task.get("id"));
                        claims.add(
                                new EpisodeExportClaim(
                                        task.get("id", String.class),
                                        task.get("projectId", String.class),
                                        manifest));
                    }
                    return List.copyOf(claims);
                });
    }

    @Override
    public ObjectNode completeExport(CompletedEpisodeExport completed) {
        return database.transactionResult(tx -> completeExport(tx, completed));
    }

    @Override
    public boolean failExport(String taskId, String code, String message) {
        return database.transactionResult(
                tx -> {
                    Record task =
                            tx.fetchOne(
                                    "SELECT * FROM \"VideoEpisodeExportTask\" WHERE id=? AND"
                                            + " \"videoEpisodeId\" IS NOT NULL FOR UPDATE",
                                    taskId);
                    if (task == null || !"rendering".equals(task.get("status"))) return false;
                    LocalDateTime now = now();
                    tx.execute(
                            "UPDATE \"VideoEpisodeExportTask\" SET status='failed',"
                                    + " \"lastErrorCode\"=?,\"lastErrorMessage\"=?,"
                                    + " \"nextAttemptAt\"=?,\"updatedAt\"=?,\"completedAt\"=?"
                                    + " WHERE id=?",
                            code,
                            message,
                            now,
                            now,
                            now,
                            taskId);
                    return true;
                });
    }

    private ObjectNode createEdit(
            DSLContext tx,
            Record episode,
            String baselineId,
            String userId,
            JsonNode request) {
        requireBaseline(tx, episode, baselineId);
        String episodeId = episode.get("id", String.class);
        Record head = ensureEditHead(tx, episodeId, baselineId, true);
        requireHead(
                head,
                request.path("expectedHeadRevision").asInt(-1),
                text(request, "basedOnVersionId"),
                "VIDEO_EDIT_HEAD_CONFLICT");
        JsonNode requestedClips = request.path("clips");
        JsonNode requestedOmissions = request.path("omissions");
        if (!requestedClips.isArray()
                || requestedClips.size() == 0
                || requestedClips.size() > 500
                || !requestedOmissions.isArray()
                || requestedOmissions.size() > 300) {
            throw invalid("VIDEO_EDIT_DOCUMENT_INVALID", "粗剪片段或省略决定数量无效");
        }
        Map<String, String> baselineShots = baselineShots(tx, episodeId, baselineId);
        Set<String> handled = new HashSet<>();
        Set<String> tempKeys = new HashSet<>();
        List<EditClip> clips = new ArrayList<>();
        long timeline = 0;
        int ordinal = 0;
        for (JsonNode item : requestedClips) {
            ordinal++;
            String tempKey = requiredText(item, "tempKey");
            if (!tempKeys.add(tempKey)) {
                throw invalid("VIDEO_EDIT_CLIP_DUPLICATE", "粗剪片段临时身份不能重复");
            }
            String adoptionId = requiredText(item, "adoptionId");
            String takeId = requiredText(item, "takeId");
            Record source =
                    tx.fetchOne(
                            "SELECT d.\"targetShotId\",d.\"targetShotVersionId\","
                                    + "d.\"sourceTakeId\",a.\"durationMs\" FROM"
                                    + " \"VideoTakeAdoption\" d"
                                    + " JOIN \"VideoProductionBaselineShot\" bs"
                                    + " ON bs.\"adoptionId\"=d.id AND bs.\"baselineId\"=?"
                                    + " AND bs.\"episodeId\"=d.\"episodeId\""
                                    + " AND bs.\"shotId\"=d.\"targetShotId\""
                                    + " AND bs.\"shotVersionId\"=d.\"targetShotVersionId\""
                                    + " JOIN \"VideoShotTake\" t ON t.id=d.\"sourceTakeId\""
                                    + " AND t.\"videoEpisodeId\"=d.\"episodeId\""
                                    + " AND t.\"projectId\"=d.\"projectId\""
                                    + " JOIN \"VideoAsset\" a ON a.id=t.\"assetId\""
                                    + " AND a.\"projectId\"=t.\"projectId\""
                                    + " WHERE d.id=? AND d.\"episodeId\"=?"
                                    + " AND d.\"projectId\"=? AND d.\"sourceTakeId\"=?"
                                    + " AND a.modality='video' AND a.\"durationMs\">0"
                                    + " AND a.\"rightsStatus\"='confirmed'"
                                    + " AND a.\"lockedAt\" IS NOT NULL",
                            baselineId,
                            adoptionId,
                            episodeId,
                            episode.get("projectId"),
                            takeId);
            if (source == null) {
                throw invalid(
                        "VIDEO_EDIT_ADOPTION_INVALID",
                        "粗剪只能使用目标基线已采用且媒体锁定的 Take");
            }
            String shotVersionId = source.get("targetShotVersionId", String.class);
            String shotId = source.get("targetShotId", String.class);
            if (!shotId.equals(baselineShots.get(shotVersionId))) {
                throw invalid("VIDEO_EDIT_ADOPTION_INVALID", "采用记录不属于目标制作基线");
            }
            int sourceIn = item.path("sourceInMs").asInt(-1);
            int sourceOut = item.path("sourceOutMs").asInt(-1);
            int mediaDuration = source.get("durationMs", Integer.class);
            if (sourceIn < 0
                    || sourceOut <= sourceIn
                    || sourceOut > mediaDuration
                    || sourceOut - sourceIn < 500) {
                throw invalid("VIDEO_EDIT_RANGE_INVALID", "粗剪区间无效或越过实测媒体时长");
            }
            String audioMode = requiredText(item, "sourceAudioMode");
            if (!Set.of("keep", "mute").contains(audioMode)) {
                throw invalid("VIDEO_EDIT_AUDIO_MODE_INVALID", "片段原声决定无效");
            }
            String transition = item.path("transitionAfter").asText("cut");
            int transitionDuration = item.path("transitionDurationMs").asInt(0);
            validateTransition(transition, transitionDuration, sourceOut - sourceIn);
            if (timeline > Integer.MAX_VALUE - (sourceOut - sourceIn)) {
                throw invalid("VIDEO_EDIT_DURATION_INVALID", "粗剪总时长超出支持范围");
            }
            clips.add(
                    new EditClip(
                            ids.next(),
                            ordinal,
                            adoptionId,
                            takeId,
                            shotId,
                            shotVersionId,
                            sourceIn,
                            sourceOut,
                            (int) timeline,
                            sourceOut - sourceIn,
                            audioMode,
                            transition,
                            transitionDuration));
            timeline += sourceOut - sourceIn;
            handled.add(shotVersionId);
        }
        ArrayNode omissions = json.createArrayNode();
        Set<String> omitted = new HashSet<>();
        for (JsonNode item : requestedOmissions) {
            String shotVersionId = requiredText(item, "shotVersionId");
            String shotId = baselineShots.get(shotVersionId);
            String reason = requiredText(item, "reason").strip();
            if (shotId == null
                    || reason.length() > 1_000
                    || !omitted.add(shotVersionId)
                    || handled.contains(shotVersionId)) {
                throw invalid("VIDEO_EDIT_OMISSION_INVALID", "省略决定无效或与粗剪片段冲突");
            }
            omissions.add(
                    object(
                            "shotId",
                            shotId,
                            "shotVersionId",
                            shotVersionId,
                            "reason",
                            reason));
        }
        Set<String> complete = new HashSet<>(handled);
        complete.addAll(omitted);
        if (!complete.equals(baselineShots.keySet())) {
            throw invalid(
                    "VIDEO_EDIT_BASELINE_INCOMPLETE",
                    "目标基线的每个镜头必须有粗剪片段或明确省略决定");
        }

        String versionId = ids.next();
        int versionNo = nextVersion(tx, "VideoEpisodeEditVersion", episodeId);
        ObjectNode content =
                object(
                        "schemaVersion",
                        "video-episode-edit/1.0",
                        "episodeId",
                        episodeId,
                        "productionBaselineId",
                        baselineId,
                        "versionNo",
                        versionNo,
                        "basedOnVersionId",
                        text(request, "basedOnVersionId"),
                        "clips",
                        clips.stream().map(this::editClipNode).toList(),
                        "omissions",
                        omissions,
                        "totalDurationMs",
                        (int) timeline);
        String requestHash = hash(commandRequest(request, baselineId, null));
        tx.execute(
                "INSERT INTO \"VideoEpisodeEditVersion\""
                        + " (id,\"projectId\",\"novelId\",\"versionNo\",\"basedOnVersionId\","
                        + " \"totalDurationMs\",\"clientRequestId\",\"requestHash\",\"contentHash\","
                        + " \"createdByUserId\",\"createdAt\",\"videoEpisodeId\","
                        + " \"productionBaselineId\",\"omissionsJson\")"
                        + " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                versionId,
                episode.get("projectId"),
                episode.get("novelId"),
                versionNo,
                text(request, "basedOnVersionId"),
                (int) timeline,
                requiredRequestId(request),
                requestHash,
                hash(content),
                userId,
                now(),
                episodeId,
                baselineId,
                omissions.toString());
        for (EditClip clip : clips) {
            tx.execute(
                    "INSERT INTO \"VideoEpisodeEditClip\""
                            + " (\"editVersionId\",ordinal,\"takeId\",\"sourceInMs\","
                            + " \"sourceOutMs\",\"timelineStartMs\",\"outputDurationMs\","
                            + " \"transitionAfter\",\"transitionDurationMs\",\"videoEpisodeId\","
                            + " \"productionBaselineId\",\"episodeShotId\","
                            + " \"episodeShotVersionId\",\"adoptionId\",\"sourceAudioMode\",\"clipId\")"
                            + " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    versionId,
                    clip.ordinal(),
                    clip.takeId(),
                    clip.sourceInMs(),
                    clip.sourceOutMs(),
                    clip.timelineStartMs(),
                    clip.outputDurationMs(),
                    clip.transitionAfter(),
                    clip.transitionDurationMs(),
                    episodeId,
                    baselineId,
                    clip.shotId(),
                    clip.shotVersionId(),
                    clip.adoptionId(),
                    clip.sourceAudioMode(),
                    clip.clipId());
        }
        tx.execute(
                "UPDATE \"VideoProductionEditHead\" SET \"currentVersionId\"=?,"
                        + " revision=revision+1,\"updatedAt\"=? WHERE \"episodeId\"=?"
                        + " AND \"productionBaselineId\"=?",
                versionId,
                now(),
                episodeId,
                baselineId);
        return editVersion(tx, episodeId, baselineId, versionId);
    }

    private ObjectNode createMix(
            DSLContext tx,
            Record episode,
            String baselineId,
            String userId,
            JsonNode request) {
        Record baseline = requireBaseline(tx, episode, baselineId);
        String episodeId = episode.get("id", String.class);
        Record head = ensureMixHead(tx, episodeId, baselineId, true);
        requireHead(
                head,
                request.path("expectedHeadRevision").asInt(-1),
                text(request, "basedOnVersionId"),
                "VIDEO_MIX_HEAD_CONFLICT");
        String editVersionId = requiredText(request, "editVersionId");
        Record edit = requireEdit(tx, episodeId, baselineId, editVersionId);
        int totalDuration = edit.get("totalDurationMs", Integer.class);
        JsonNode requestedAudio = request.path("audioClips");
        JsonNode requestedSubtitles = request.path("subtitleCues");
        if (!requestedAudio.isArray()
                || requestedAudio.size() > 1_000
                || !requestedSubtitles.isArray()
                || requestedSubtitles.size() > 2_000) {
            throw invalid("VIDEO_MIX_DOCUMENT_INVALID", "声音或字幕数量无效");
        }
        Map<String, String> baselineShots = baselineShots(tx, episodeId, baselineId);
        List<AudioClip> audio = new ArrayList<>();
        int ordinal = 0;
        for (JsonNode item : requestedAudio) {
            ordinal++;
            String trackKind = requiredText(item, "trackKind");
            if (!TRACK_KINDS.contains(trackKind)) {
                throw invalid("VIDEO_MIX_TRACK_INVALID", "声音轨道类型无效");
            }
            Record asset = lockedAsset(tx, episode, requiredText(item, "assetId"), "audio");
            String shotVersionId = text(item, "shotVersionId");
            String shotId = shotVersionId == null ? null : baselineShots.get(shotVersionId);
            if (shotVersionId != null && shotId == null) {
                throw invalid("VIDEO_MIX_SHOT_INVALID", "声音绑定镜头不属于目标基线");
            }
            if (Set.of("dialogue", "narration", "sfx").contains(trackKind)
                    && shotVersionId == null) {
                throw invalid("VIDEO_MIX_SHOT_REQUIRED", "对白、旁白和音效必须绑定目标镜头");
            }
            int start = item.path("timelineStartMs").asInt(-1);
            int sourceIn = item.path("sourceInMs").asInt(-1);
            int sourceOut = item.path("sourceOutMs").asInt(-1);
            int duration = asset.get("durationMs", Integer.class);
            int fadeIn = item.path("fadeInMs").asInt(0);
            int fadeOut = item.path("fadeOutMs").asInt(0);
            int gain = item.path("gainMillibels").asInt(0);
            if (start < 0
                    || sourceIn < 0
                    || sourceOut <= sourceIn
                    || sourceOut > duration
                    || start + sourceOut - sourceIn > totalDuration
                    || fadeIn < 0
                    || fadeOut < 0
                    || fadeIn + fadeOut > sourceOut - sourceIn
                    || gain < -6_000
                    || gain > 1_200) {
                throw invalid("VIDEO_MIX_AUDIO_RANGE_INVALID", "声音片段区间或增益无效");
            }
            audio.add(
                    new AudioClip(
                            ordinal,
                            trackKind,
                            asset.get("id", String.class),
                            shotId,
                            shotVersionId,
                            start,
                            sourceIn,
                            sourceOut,
                            gain,
                            fadeIn,
                            fadeOut));
        }
        Set<String> scriptLines = scriptLineIds(tx, baseline.get("scriptVersionId", String.class));
        List<SubtitleCue> subtitles = new ArrayList<>();
        ordinal = 0;
        for (JsonNode item : requestedSubtitles) {
            ordinal++;
            String shotVersionId = requiredText(item, "shotVersionId");
            String shotId = baselineShots.get(shotVersionId);
            String scriptLineId = requiredText(item, "scriptLineId");
            int start = item.path("startMs").asInt(-1);
            int end = item.path("endMs").asInt(-1);
            String cueText = requiredText(item, "text").strip();
            String speaker = text(item, "speaker");
            if (shotId == null
                    || !scriptLines.contains(scriptLineId)
                    || !shotContainsLine(tx, shotVersionId, scriptLineId)
                    || start < 0
                    || end <= start
                    || end > totalDuration
                    || cueText.length() > 2_000
                    || speaker != null && speaker.length() > 120) {
                throw invalid("VIDEO_MIX_SUBTITLE_INVALID", "字幕台词身份或时间范围无效");
            }
            subtitles.add(
                    new SubtitleCue(
                            ordinal,
                            shotId,
                            shotVersionId,
                            scriptLineId,
                            start,
                            end,
                            speaker,
                            cueText));
        }
        int versionNo = nextVersion(tx, "VideoEpisodeMixVersion", episodeId);
        String versionId = ids.next();
        ObjectNode content =
                object(
                        "schemaVersion",
                        "video-episode-mix/1.0",
                        "episodeId",
                        episodeId,
                        "productionBaselineId",
                        baselineId,
                        "editVersionId",
                        editVersionId,
                        "versionNo",
                        versionNo,
                        "basedOnVersionId",
                        text(request, "basedOnVersionId"),
                        "audioClips",
                        audio.stream().map(this::audioClipNode).toList(),
                        "subtitleCues",
                        subtitles.stream().map(this::subtitleNode).toList());
        tx.execute(
                "INSERT INTO \"VideoEpisodeMixVersion\""
                        + " (id,\"projectId\",\"novelId\",\"editVersionId\",\"versionNo\","
                        + " \"basedOnVersionId\",\"clientRequestId\",\"requestHash\",\"contentHash\","
                        + " \"createdByUserId\",\"createdAt\",\"videoEpisodeId\","
                        + " \"productionBaselineId\") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                versionId,
                episode.get("projectId"),
                episode.get("novelId"),
                editVersionId,
                versionNo,
                text(request, "basedOnVersionId"),
                requiredRequestId(request),
                hash(commandRequest(request, baselineId, null)),
                hash(content),
                userId,
                now(),
                episodeId,
                baselineId);
        for (AudioClip clip : audio) {
            tx.execute(
                    "INSERT INTO \"VideoEpisodeAudioClip\""
                            + " (\"mixVersionId\",\"projectId\",ordinal,\"trackKind\",\"assetId\","
                            + " \"timelineStartMs\",\"sourceInMs\",\"sourceOutMs\","
                            + " \"gainMillibels\",\"fadeInMs\",\"fadeOutMs\",\"videoEpisodeId\","
                            + " \"productionBaselineId\",\"episodeShotId\",\"episodeShotVersionId\")"
                            + " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    versionId,
                    episode.get("projectId"),
                    clip.ordinal(),
                    clip.trackKind(),
                    clip.assetId(),
                    clip.timelineStartMs(),
                    clip.sourceInMs(),
                    clip.sourceOutMs(),
                    clip.gainMillibels(),
                    clip.fadeInMs(),
                    clip.fadeOutMs(),
                    episodeId,
                    baselineId,
                    clip.shotId(),
                    clip.shotVersionId());
        }
        for (SubtitleCue cue : subtitles) {
            tx.execute(
                    "INSERT INTO \"VideoEpisodeSubtitleCue\""
                            + " (\"mixVersionId\",ordinal,\"shotId\",\"startMs\",\"endMs\","
                            + " speaker,text,\"videoEpisodeId\",\"productionBaselineId\","
                            + " \"episodeShotId\",\"episodeShotVersionId\",\"scriptLineId\")"
                            + " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    versionId,
                    cue.ordinal(),
                    null,
                    cue.startMs(),
                    cue.endMs(),
                    cue.speaker(),
                    cue.text(),
                    episodeId,
                    baselineId,
                    cue.shotId(),
                    cue.shotVersionId(),
                    cue.scriptLineId());
        }
        tx.execute(
                "UPDATE \"VideoProductionMixHead\" SET \"currentVersionId\"=?,"
                        + " revision=revision+1,\"updatedAt\"=? WHERE \"episodeId\"=?"
                        + " AND \"productionBaselineId\"=?",
                versionId,
                now(),
                episodeId,
                baselineId);
        return mixVersion(tx, episodeId, baselineId, versionId);
    }

    private ObjectNode createExport(
            DSLContext tx,
            Record episode,
            String baselineId,
            String userId,
            JsonNode request,
            String retryOfTaskId) {
        Record baseline = requireBaseline(tx, episode, baselineId);
        String episodeId = episode.get("id", String.class);
        requireNoActiveExport(tx, episodeId);
        String resolution = request.path("resolution").asText("720p");
        int framesPerSecond = request.path("framesPerSecond").asInt(24);
        if (!Set.of("720p", "1080p").contains(resolution)
                || !Set.of(24, 25, 30).contains(framesPerSecond)) {
            throw invalid("VIDEO_EXPORT_OUTPUT_INVALID", "导出分辨率或帧率无效");
        }
        VideoEpisodeExportManifest manifest =
                buildManifest(
                        tx,
                        episode,
                        baseline,
                        requiredText(request, "editVersionId"),
                        requiredText(request, "mixVersionId"),
                        resolution,
                        framesPerSecond,
                        request.path("burnSubtitles").asBoolean(true));
        return insertExportTask(
                tx,
                episode,
                baselineId,
                userId,
                requiredRequestId(request),
                retryOfTaskId,
                manifest,
                resolution,
                framesPerSecond,
                request.path("burnSubtitles").asBoolean(true));
    }

    private ObjectNode retryExport(
            DSLContext tx,
            Record episode,
            String baselineId,
            String taskId,
            String userId,
            JsonNode request) {
        requireBaseline(tx, episode, baselineId);
        Record source =
                tx.fetchOne(
                        "SELECT * FROM \"VideoEpisodeExportTask\" WHERE id=? AND"
                                + " \"videoEpisodeId\"=? AND \"productionBaselineId\"=?"
                                + " FOR UPDATE",
                        taskId,
                        episode.get("id"),
                        baselineId);
        if (source == null) {
            throw missing("VIDEO_EXPORT_TASK_NOT_FOUND", "整集导出任务不存在");
        }
        if (!"failed".equals(source.get("status"))) {
            throw conflict("VIDEO_EXPORT_TASK_NOT_RETRYABLE", "只有失败任务可以按原清单重试");
        }
        requireNoActiveExport(tx, episode.get("id", String.class));
        VideoEpisodeExportManifest manifest =
                manifests.parse(
                        source.get("requestManifestJson", String.class),
                        source.get("inputHash", String.class));
        return insertExportTask(
                tx,
                episode,
                baselineId,
                userId,
                requiredRequestId(request),
                taskId,
                manifest,
                source.get("resolution", String.class),
                source.get("framesPerSecond", Integer.class),
                source.get("burnSubtitles", Boolean.class));
    }

    private ObjectNode insertExportTask(
            DSLContext tx,
            Record episode,
            String baselineId,
            String userId,
            String clientRequestId,
            String retryOfTaskId,
            VideoEpisodeExportManifest manifest,
            String resolution,
            int framesPerSecond,
            boolean burnSubtitles) {
        LocalDateTime now = now();
        String taskId = ids.next();
        tx.execute(
                "INSERT INTO \"VideoEpisodeExportTask\""
                        + " (id,\"requestedByUserId\",\"projectId\",\"novelId\","
                        + " \"editVersionId\",\"mixVersionId\",\"retryOfTaskId\","
                        + " \"clientRequestId\",status,\"inputHash\",\"requestManifestJson\","
                        + " resolution,\"framesPerSecond\",\"burnSubtitles\",\"attemptCount\","
                        + " \"nextAttemptAt\",\"createdAt\",\"updatedAt\",\"videoEpisodeId\","
                        + " \"productionBaselineId\")"
                        + " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                taskId,
                userId,
                episode.get("projectId"),
                episode.get("novelId"),
                manifest.editVersionId(),
                manifest.mixVersionId(),
                retryOfTaskId,
                clientRequestId,
                "pending",
                manifests.hash(manifest),
                manifests.serialize(manifest),
                resolution,
                framesPerSecond,
                burnSubtitles,
                0,
                now,
                now,
                now,
                episode.get("id"),
                baselineId);
        return exportTask(tx, episode.get("id", String.class), baselineId, taskId);
    }

    private VideoEpisodeExportManifest buildManifest(
            DSLContext tx,
            Record episode,
            Record baseline,
            String editVersionId,
            String mixVersionId,
            String resolution,
            int framesPerSecond,
            boolean burnSubtitles) {
        String episodeId = episode.get("id", String.class);
        String baselineId = baseline.get("id", String.class);
        Record edit = requireEdit(tx, episodeId, baselineId, editVersionId);
        Record mix = requireMix(tx, episodeId, baselineId, mixVersionId);
        if (!editVersionId.equals(mix.get("editVersionId"))) {
            throw conflict("VIDEO_EXPORT_MIX_STALE", "声音字幕版本不是基于所选粗剪");
        }
        Record project =
                tx.fetchOne(
                        "SELECT \"targetAspectRatio\" FROM \"VideoProject\" WHERE id=?",
                        episode.get("projectId"));
        String ratio = project == null ? null : project.get("targetAspectRatio", String.class);
        if (ratio == null
                || "adaptive".equals(ratio)
                || !Set.of("16:9", "4:3", "1:1", "3:4", "9:16", "21:9")
                        .contains(ratio)) {
            throw conflict("VIDEO_EXPORT_FIXED_RATIO_REQUIRED", "整集导出必须使用固定项目画幅");
        }
        List<Record> videoRows =
                tx.fetch(
                        "SELECT c.*,t.\"assetId\",a.modality,a.\"storageKey\",a.sha256,"
                                + "a.\"mimeType\",a.\"durationMs\",a.\"rightsStatus\","
                                + "a.\"lockedAt\" FROM \"VideoEpisodeEditClip\" c"
                                + " JOIN \"VideoShotTake\" t ON t.id=c.\"takeId\""
                                + " AND t.\"videoEpisodeId\"=c.\"videoEpisodeId\""
                                + " JOIN \"VideoAsset\" a ON a.id=t.\"assetId\""
                                + " AND a.\"projectId\"=t.\"projectId\""
                                + " WHERE c.\"editVersionId\"=? AND c.\"videoEpisodeId\"=?"
                                + " AND c.\"productionBaselineId\"=? ORDER BY c.ordinal",
                        editVersionId,
                        episodeId,
                        baselineId);
        if (videoRows.isEmpty()) {
            throw conflict("VIDEO_EXPORT_EDIT_EMPTY", "粗剪没有可导出的视频片段");
        }
        List<FrozenVideoClip> videos = new ArrayList<>();
        for (Record row : videoRows) {
            FrozenAsset asset = frozenAsset(row, "video");
            int sourceIn = row.get("sourceInMs", Integer.class);
            int sourceOut = row.get("sourceOutMs", Integer.class);
            if (asset.durationMs() == null || sourceOut > asset.durationMs()) {
                throw conflict("VIDEO_EXPORT_CLIP_RANGE_INVALID", "粗剪区间超过冻结视频时长");
            }
            videos.add(
                    new FrozenVideoClip(
                            row.get("ordinal", Integer.class),
                            row.get("clipId", String.class),
                            row.get("adoptionId", String.class),
                            row.get("episodeShotId", String.class),
                            row.get("episodeShotVersionId", String.class),
                            row.get("takeId", String.class),
                            asset,
                            sourceIn,
                            sourceOut,
                            row.get("outputDurationMs", Integer.class),
                            row.get("sourceAudioMode", String.class),
                            row.get("transitionAfter", String.class),
                            row.get("transitionDurationMs", Integer.class)));
        }
        List<Record> audioRows =
                tx.fetch(
                        "SELECT c.*,a.modality,a.\"storageKey\",a.sha256,a.\"mimeType\","
                                + "a.\"durationMs\",a.\"rightsStatus\",a.\"lockedAt\""
                                + " FROM \"VideoEpisodeAudioClip\" c JOIN \"VideoAsset\" a"
                                + " ON a.id=c.\"assetId\" AND a.\"projectId\"=c.\"projectId\""
                                + " WHERE c.\"mixVersionId\"=? AND c.\"videoEpisodeId\"=?"
                                + " AND c.\"productionBaselineId\"=? ORDER BY c.ordinal",
                        mixVersionId,
                        episodeId,
                        baselineId);
        List<FrozenAudioClip> audio = new ArrayList<>();
        for (Record row : audioRows) {
            audio.add(
                    new FrozenAudioClip(
                            row.get("ordinal", Integer.class),
                            row.get("trackKind", String.class),
                            row.get("episodeShotId", String.class),
                            row.get("episodeShotVersionId", String.class),
                            frozenAsset(row, "audio"),
                            row.get("timelineStartMs", Integer.class),
                            row.get("sourceInMs", Integer.class),
                            row.get("sourceOutMs", Integer.class),
                            row.get("gainMillibels", Integer.class),
                            row.get("fadeInMs", Integer.class),
                            row.get("fadeOutMs", Integer.class)));
        }
        List<FrozenSubtitleCue> subtitles =
                tx.fetch(
                                "SELECT * FROM \"VideoEpisodeSubtitleCue\" WHERE"
                                        + " \"mixVersionId\"=? AND \"videoEpisodeId\"=?"
                                        + " AND \"productionBaselineId\"=? ORDER BY ordinal",
                                mixVersionId,
                                episodeId,
                                baselineId)
                        .stream()
                        .map(
                                row ->
                                        new FrozenSubtitleCue(
                                                row.get("ordinal", Integer.class),
                                                row.get("episodeShotId", String.class),
                                                row.get("episodeShotVersionId", String.class),
                                                row.get("scriptLineId", String.class),
                                                row.get("startMs", Integer.class),
                                                row.get("endMs", Integer.class),
                                                row.get("speaker", String.class),
                                                row.get("text", String.class)))
                        .toList();
        return new VideoEpisodeExportManifest(
                VideoEpisodeExportManifest.NATIVE_SCHEMA_VERSION,
                null,
                episodeId,
                baselineId,
                baseline.get("contentHash", String.class),
                baseline.get("scriptVersionId", String.class),
                baseline.get("storyboardVersionId", String.class),
                episode.get("projectId", String.class),
                episode.get("novelId", String.class),
                null,
                null,
                null,
                editVersionId,
                edit.get("contentHash", String.class),
                mixVersionId,
                mix.get("contentHash", String.class),
                ratio,
                resolution,
                framesPerSecond,
                burnSubtitles,
                edit.get("totalDurationMs", Integer.class),
                FfmpegSettings.productionDefault(),
                videos,
                audio,
                subtitles);
    }

    private ObjectNode completeExport(DSLContext tx, CompletedEpisodeExport completed) {
        // 用户写入口统一先锁 Episode 再锁导出任务。worker 只先非锁读取作用域，随后保持同一
        // Episode→ExportTask 锁序，避免与重试并发时形成反向等待。
        Record scope =
                tx.fetchOne(
                        "SELECT \"videoEpisodeId\",\"projectId\",\"novelId\""
                                + " FROM \"VideoEpisodeExportTask\" WHERE id=?"
                                + " AND \"videoEpisodeId\" IS NOT NULL",
                        completed.taskId());
        if (scope == null) throw new IllegalStateException("独立分集导出任务不存在");
        Record episode =
                tx.fetchOne(
                        "SELECT id FROM \"VideoEpisode\" WHERE id=? AND \"projectId\"=?"
                                + " AND \"novelId\"=? AND \"archivedAt\" IS NULL FOR UPDATE",
                        scope.get("videoEpisodeId"),
                        scope.get("projectId"),
                        scope.get("novelId"));
        if (episode == null) {
            throw new IllegalStateException("独立分集导出任务所属剧集不存在");
        }
        Record task =
                tx.fetchOne(
                        "SELECT * FROM \"VideoEpisodeExportTask\" WHERE id=? AND"
                                + " \"videoEpisodeId\"=? AND \"projectId\"=? AND \"novelId\"=?"
                                + " FOR UPDATE",
                        completed.taskId(),
                        scope.get("videoEpisodeId"),
                        scope.get("projectId"),
                        scope.get("novelId"));
        if (task == null) throw new IllegalStateException("独立分集导出任务不存在");
        Record existing =
                tx.fetchOne(
                        "SELECT id FROM \"VideoEpisodeExport\" WHERE \"taskId\"=?",
                        completed.taskId());
        if (existing != null) {
            return exportTask(
                    tx,
                    task.get("videoEpisodeId", String.class),
                    task.get("productionBaselineId", String.class),
                    completed.taskId());
        }
        if (!"rendering".equals(task.get("status"))) {
            throw new IllegalStateException("独立分集导出任务不在渲染阶段");
        }
        if (!completed.assetId().equals("export_" + completed.taskId())) {
            throw new IllegalArgumentException("成片必须使用任务确定性素材标识");
        }
        int versionNo =
                tx.fetchOne(
                                "SELECT COALESCE(MAX(\"versionNo\"),0)+1 n FROM"
                                        + " \"VideoEpisodeExport\" WHERE \"videoEpisodeId\"=?",
                                task.get("videoEpisodeId"))
                        .get("n", Integer.class);
        LocalDateTime now = now();
        tx.execute(
                "INSERT INTO \"VideoAsset\""
                        + " (id,\"projectId\",name,modality,duty,\"storageKey\",\"mimeType\","
                        + " \"byteSize\",\"durationMs\",sha256,\"sourceKind\",\"rightsStatus\","
                        + " \"lockedAt\",\"createdAt\",\"updatedAt\")"
                        + " VALUES (?,?,'独立分集成片 v' || ?,'video','episode_export',?,?,?,?,?,'model_generated','confirmed',?,?,?)",
                completed.assetId(),
                task.get("projectId"),
                versionNo,
                completed.stored().storageKey(),
                completed.stored().mimeType(),
                completed.stored().byteSize(),
                completed.durationMs(),
                completed.stored().sha256(),
                now,
                now,
                now);
        String exportId = ids.next();
        tx.execute(
                "INSERT INTO \"VideoEpisodeExport\""
                        + " (id,\"taskId\",\"projectId\",\"editVersionId\",\"mixVersionId\","
                        + " \"assetId\",\"versionNo\",\"inputHash\",\"createdAt\","
                        + " \"videoEpisodeId\",\"productionBaselineId\")"
                        + " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                exportId,
                completed.taskId(),
                task.get("projectId"),
                task.get("editVersionId"),
                task.get("mixVersionId"),
                completed.assetId(),
                versionNo,
                task.get("inputHash"),
                now,
                task.get("videoEpisodeId"),
                task.get("productionBaselineId"));
        tx.execute(
                "UPDATE \"VideoEpisodeExportTask\" SET status='succeeded',"
                        + " \"lastErrorCode\"=NULL,\"lastErrorMessage\"=NULL,"
                        + " \"nextAttemptAt\"=?,\"updatedAt\"=?,\"completedAt\"=? WHERE id=?",
                now,
                now,
                now,
                completed.taskId());
        int episodeUpdated =
                tx.execute(
                        "UPDATE \"VideoEpisode\" SET \"latestDeliveryVersionId\"=?,"
                                + " \"deliveryRevision\"=\"deliveryRevision\"+1,"
                                + " revision=revision+1,\"updatedAt\"=?"
                                + " WHERE id=? AND \"projectId\"=? AND \"novelId\"=?"
                                + " AND \"archivedAt\" IS NULL",
                        exportId,
                        now,
                        task.get("videoEpisodeId"),
                        task.get("projectId"),
                        task.get("novelId"));
        if (episodeUpdated != 1) {
            throw new IllegalStateException("独立分集交付 head 更新失败");
        }
        return exportTask(
                tx,
                task.get("videoEpisodeId", String.class),
                task.get("productionBaselineId", String.class),
                completed.taskId());
    }

    private ObjectNode editVersion(
            DSLContext tx, String episodeId, String baselineId, String versionId) {
        Record version = requireEdit(tx, episodeId, baselineId, versionId);
        List<ObjectNode> clips =
                tx.fetch(
                                "SELECT c.*,a.id \"assetId\",a.name \"assetName\","
                                        + "a.modality \"assetModality\",a.\"mimeType\" \"assetMimeType\","
                                        + "a.\"durationMs\" \"assetDurationMs\","
                                        + "a.\"byteSize\" \"assetByteSize\",a.sha256 \"assetSha256\""
                                        + " FROM \"VideoEpisodeEditClip\" c"
                                        + " JOIN \"VideoShotTake\" t ON t.id=c.\"takeId\""
                                        + " JOIN \"VideoAsset\" a ON a.id=t.\"assetId\""
                                        + " WHERE c.\"editVersionId\"=? AND c.\"videoEpisodeId\"=?"
                                        + " AND c.\"productionBaselineId\"=? ORDER BY c.ordinal",
                                versionId,
                                episodeId,
                                baselineId)
                        .stream()
                        .map(this::editClipResponse)
                        .toList();
        ArrayNode omissions =
                (ArrayNode) json.readTree(version.get("omissionsJson", String.class));
        Record head = ensureEditHead(tx, episodeId, baselineId, false);
        return object(
                "id",
                versionId,
                "episodeId",
                episodeId,
                "productionBaselineId",
                baselineId,
                "versionNo",
                version.get("versionNo"),
                "basedOnVersionId",
                version.get("basedOnVersionId"),
                "clipCount",
                clips.size(),
                "omissionCount",
                omissions.size(),
                "totalDurationMs",
                version.get("totalDurationMs"),
                "contentHash",
                version.get("contentHash"),
                "createdAt",
                apiTime(version, "createdAt"),
                "clips",
                clips,
                "omissions",
                omissions,
                "headRevision",
                head == null ? 1 : head.get("revision"));
    }

    private ObjectNode mixVersion(
            DSLContext tx, String episodeId, String baselineId, String versionId) {
        Record version = requireMix(tx, episodeId, baselineId, versionId);
        List<ObjectNode> audio =
                tx.fetch(
                                "SELECT c.*,a.id \"assetId\",a.name \"assetName\","
                                        + "a.modality \"assetModality\",a.\"mimeType\" \"assetMimeType\","
                                        + "a.\"durationMs\" \"assetDurationMs\","
                                        + "a.\"byteSize\" \"assetByteSize\",a.sha256 \"assetSha256\""
                                        + " FROM \"VideoEpisodeAudioClip\" c"
                                        + " JOIN \"VideoAsset\" a ON a.id=c.\"assetId\""
                                        + " WHERE c.\"mixVersionId\"=? AND c.\"videoEpisodeId\"=?"
                                        + " AND c.\"productionBaselineId\"=? ORDER BY c.ordinal",
                                versionId,
                                episodeId,
                                baselineId)
                        .stream()
                        .map(this::audioClipResponse)
                        .toList();
        List<ObjectNode> subtitles =
                tx.fetch(
                                "SELECT * FROM \"VideoEpisodeSubtitleCue\" WHERE"
                                        + " \"mixVersionId\"=? AND \"videoEpisodeId\"=?"
                                        + " AND \"productionBaselineId\"=? ORDER BY ordinal",
                                versionId,
                                episodeId,
                                baselineId)
                        .stream()
                        .map(this::subtitleResponse)
                        .toList();
        Record head = ensureMixHead(tx, episodeId, baselineId, false);
        return object(
                "id",
                versionId,
                "episodeId",
                episodeId,
                "productionBaselineId",
                baselineId,
                "editVersionId",
                version.get("editVersionId"),
                "versionNo",
                version.get("versionNo"),
                "basedOnVersionId",
                version.get("basedOnVersionId"),
                "audioClipCount",
                audio.size(),
                "subtitleCueCount",
                subtitles.size(),
                "contentHash",
                version.get("contentHash"),
                "createdAt",
                apiTime(version, "createdAt"),
                "audioClips",
                audio,
                "subtitleCues",
                subtitles,
                "headRevision",
                head == null ? 1 : head.get("revision"));
    }

    private ObjectNode editSummary(Record row) {
        return object(
                "id",
                row.get("id"),
                "episodeId",
                row.get("videoEpisodeId"),
                "productionBaselineId",
                row.get("productionBaselineId"),
                "versionNo",
                row.get("versionNo"),
                "basedOnVersionId",
                row.get("basedOnVersionId"),
                "clipCount",
                row.get("clipCount"),
                "omissionCount",
                row.get("omissionCount"),
                "totalDurationMs",
                row.get("totalDurationMs"),
                "contentHash",
                row.get("contentHash"),
                "createdAt",
                apiTime(row, "createdAt"));
    }

    private ObjectNode mixSummary(Record row) {
        return object(
                "id",
                row.get("id"),
                "episodeId",
                row.get("videoEpisodeId"),
                "productionBaselineId",
                row.get("productionBaselineId"),
                "editVersionId",
                row.get("editVersionId"),
                "versionNo",
                row.get("versionNo"),
                "basedOnVersionId",
                row.get("basedOnVersionId"),
                "audioClipCount",
                row.get("audioClipCount"),
                "subtitleCueCount",
                row.get("subtitleCueCount"),
                "contentHash",
                row.get("contentHash"),
                "createdAt",
                apiTime(row, "createdAt"));
    }

    private ObjectNode exportTask(
            DSLContext tx, String episodeId, String baselineId, String taskId) {
        Record task =
                tx.fetchOne(
                        "SELECT * FROM \"VideoEpisodeExportTask\" WHERE id=? AND"
                                + " \"videoEpisodeId\"=? AND \"productionBaselineId\"=?",
                        taskId,
                        episodeId,
                        baselineId);
        if (task == null) {
            throw missing("VIDEO_EXPORT_TASK_NOT_FOUND", "整集导出任务不存在");
        }
        Record exported =
                tx.fetchOne(
                        "SELECT id FROM \"VideoEpisodeExport\" WHERE \"taskId\"=? AND"
                                + " \"videoEpisodeId\"=? AND \"productionBaselineId\"=?",
                        taskId,
                        episodeId,
                        baselineId);
        return object(
                "id",
                taskId,
                "episodeId",
                episodeId,
                "productionBaselineId",
                baselineId,
                "editVersionId",
                task.get("editVersionId"),
                "mixVersionId",
                task.get("mixVersionId"),
                "retryOfTaskId",
                task.get("retryOfTaskId"),
                "status",
                task.get("status"),
                "clientRequestId",
                task.get("clientRequestId"),
                "inputHash",
                task.get("inputHash"),
                "resolution",
                task.get("resolution"),
                "framesPerSecond",
                task.get("framesPerSecond"),
                "burnSubtitles",
                task.get("burnSubtitles"),
                "attemptCount",
                task.get("attemptCount"),
                "lastErrorCode",
                task.get("lastErrorCode"),
                "lastErrorMessage",
                task.get("lastErrorMessage"),
                "createdAt",
                apiTime(task, "createdAt"),
                "updatedAt",
                apiTime(task, "updatedAt"),
                "startedAt",
                apiTime(task, "startedAt"),
                "completedAt",
                apiTime(task, "completedAt"),
                "export",
                exported == null
                        ? null
                        : delivery(
                                tx,
                                episodeId,
                                baselineId,
                                exported.get("id", String.class)));
    }

    private ObjectNode delivery(
            DSLContext tx, String episodeId, String baselineId, String exportId) {
        Record row = deliveryRecord(tx, episodeId, baselineId, exportId);
        return object(
                "id",
                row.get("id"),
                "taskId",
                row.get("taskId"),
                "episodeId",
                episodeId,
                "productionBaselineId",
                baselineId,
                "versionNo",
                row.get("versionNo"),
                "editVersionId",
                row.get("editVersionId"),
                "mixVersionId",
                row.get("mixVersionId"),
                "inputHash",
                row.get("inputHash"),
                "createdAt",
                apiTime(row, "createdAt"),
                "asset",
                object(
                        "id",
                        row.get("assetId"),
                        "name",
                        row.get("name"),
                        "modality",
                        row.get("modality"),
                        "mimeType",
                        row.get("mimeType"),
                        "durationMs",
                        row.get("durationMs"),
                        "byteSize",
                        row.get("byteSize"),
                        "sha256",
                        row.get("sha256"),
                        "contentUrl",
                        "/api/v1/video/episodes/"
                                + episodeId
                                + "/production-baselines/"
                                + baselineId
                                + "/exports/"
                                + exportId
                                + "/content"));
    }

    private Record deliveryRecord(
            DSLContext tx, String episodeId, String baselineId, String exportId) {
        Record row =
                tx.fetchOne(
                        "SELECT e.*,a.name,a.modality,a.\"storageKey\",a.\"mimeType\","
                                + "a.\"durationMs\",a.\"byteSize\",a.sha256 FROM"
                                + " \"VideoEpisodeExport\" e JOIN \"VideoAsset\" a"
                                + " ON a.id=e.\"assetId\" AND a.\"projectId\"=e.\"projectId\""
                                + " WHERE e.id=? AND e.\"videoEpisodeId\"=?"
                                + " AND e.\"productionBaselineId\"=?",
                        exportId,
                        episodeId,
                        baselineId);
        if (row == null) {
            throw missing("VIDEO_EPISODE_EXPORT_NOT_FOUND", "整集交付不存在");
        }
        return row;
    }

    private ObjectNode editClipResponse(Record row) {
        return object(
                "clipId",
                row.get("clipId"),
                "ordinal",
                row.get("ordinal"),
                "adoptionId",
                row.get("adoptionId"),
                "takeId",
                row.get("takeId"),
                "shotId",
                row.get("episodeShotId"),
                "shotVersionId",
                row.get("episodeShotVersionId"),
                "sourceInMs",
                row.get("sourceInMs"),
                "sourceOutMs",
                row.get("sourceOutMs"),
                "timelineStartMs",
                row.get("timelineStartMs"),
                "outputDurationMs",
                row.get("outputDurationMs"),
                "sourceAudioMode",
                row.get("sourceAudioMode"),
                "transitionAfter",
                row.get("transitionAfter"),
                "transitionDurationMs",
                row.get("transitionDurationMs"),
                "asset",
                assetNode(row));
    }

    private ObjectNode audioClipResponse(Record row) {
        return object(
                "ordinal",
                row.get("ordinal"),
                "trackKind",
                row.get("trackKind"),
                "assetId",
                row.get("assetId"),
                "shotId",
                row.get("episodeShotId"),
                "shotVersionId",
                row.get("episodeShotVersionId"),
                "timelineStartMs",
                row.get("timelineStartMs"),
                "sourceInMs",
                row.get("sourceInMs"),
                "sourceOutMs",
                row.get("sourceOutMs"),
                "gainMillibels",
                row.get("gainMillibels"),
                "fadeInMs",
                row.get("fadeInMs"),
                "fadeOutMs",
                row.get("fadeOutMs"),
                "asset",
                assetNode(row));
    }

    private ObjectNode subtitleResponse(Record row) {
        return object(
                "ordinal",
                row.get("ordinal"),
                "shotId",
                row.get("episodeShotId"),
                "shotVersionId",
                row.get("episodeShotVersionId"),
                "scriptLineId",
                row.get("scriptLineId"),
                "startMs",
                row.get("startMs"),
                "endMs",
                row.get("endMs"),
                "speaker",
                row.get("speaker"),
                "text",
                row.get("text"));
    }

    private ObjectNode assetNode(Record row) {
        return object(
                "id",
                row.get("assetId"),
                "name",
                row.get("assetName"),
                "modality",
                row.get("assetModality"),
                "mimeType",
                row.get("assetMimeType"),
                "durationMs",
                row.get("assetDurationMs"),
                "byteSize",
                row.get("assetByteSize"),
                "sha256",
                row.get("assetSha256"));
    }

    private ObjectNode editClipNode(EditClip clip) {
        return object(
                "clipId",
                clip.clipId(),
                "ordinal",
                clip.ordinal(),
                "adoptionId",
                clip.adoptionId(),
                "takeId",
                clip.takeId(),
                "shotId",
                clip.shotId(),
                "shotVersionId",
                clip.shotVersionId(),
                "sourceInMs",
                clip.sourceInMs(),
                "sourceOutMs",
                clip.sourceOutMs(),
                "timelineStartMs",
                clip.timelineStartMs(),
                "outputDurationMs",
                clip.outputDurationMs(),
                "sourceAudioMode",
                clip.sourceAudioMode(),
                "transitionAfter",
                clip.transitionAfter(),
                "transitionDurationMs",
                clip.transitionDurationMs());
    }

    private ObjectNode audioClipNode(AudioClip clip) {
        return object(
                "ordinal",
                clip.ordinal(),
                "trackKind",
                clip.trackKind(),
                "assetId",
                clip.assetId(),
                "shotId",
                clip.shotId(),
                "shotVersionId",
                clip.shotVersionId(),
                "timelineStartMs",
                clip.timelineStartMs(),
                "sourceInMs",
                clip.sourceInMs(),
                "sourceOutMs",
                clip.sourceOutMs(),
                "gainMillibels",
                clip.gainMillibels(),
                "fadeInMs",
                clip.fadeInMs(),
                "fadeOutMs",
                clip.fadeOutMs());
    }

    private ObjectNode subtitleNode(SubtitleCue cue) {
        return object(
                "ordinal",
                cue.ordinal(),
                "shotId",
                cue.shotId(),
                "shotVersionId",
                cue.shotVersionId(),
                "scriptLineId",
                cue.scriptLineId(),
                "startMs",
                cue.startMs(),
                "endMs",
                cue.endMs(),
                "speaker",
                cue.speaker(),
                "text",
                cue.text());
    }

    private ObjectNode versionPage(
            String key,
            String episodeId,
            String baselineId,
            Record head,
            List<Record> rows,
            int limit,
            java.util.function.Function<Record, ObjectNode> mapper) {
        boolean hasMore = rows.size() > limit;
        List<Record> visible = hasMore ? rows.subList(0, limit) : rows;
        Integer next =
                hasMore && !visible.isEmpty()
                        ? visible.get(visible.size() - 1).get("versionNo", Integer.class)
                        : null;
        return object(
                "episodeId",
                episodeId,
                "productionBaselineId",
                baselineId,
                "headRevision",
                head == null ? 1 : head.get("revision"),
                "currentVersionId",
                head == null ? null : head.get("currentVersionId"),
                key,
                visible.stream().map(mapper).toList(),
                "nextBeforeVersionNo",
                next);
    }

    private static String editSummarySql(String cursor) {
        return "SELECT v.*,(SELECT count(*) FROM \"VideoEpisodeEditClip\" c"
                + " WHERE c.\"editVersionId\"=v.id) \"clipCount\","
                + "jsonb_array_length(v.\"omissionsJson\"::jsonb) \"omissionCount\""
                + " FROM \"VideoEpisodeEditVersion\" v WHERE v.\"videoEpisodeId\"=?"
                + " AND v.\"productionBaselineId\"=?"
                + cursor;
    }

    private static String mixSummarySql(String cursor) {
        return "SELECT v.*,(SELECT count(*) FROM \"VideoEpisodeAudioClip\" c"
                + " WHERE c.\"mixVersionId\"=v.id) \"audioClipCount\","
                + "(SELECT count(*) FROM \"VideoEpisodeSubtitleCue\" c"
                + " WHERE c.\"mixVersionId\"=v.id) \"subtitleCueCount\""
                + " FROM \"VideoEpisodeMixVersion\" v WHERE v.\"videoEpisodeId\"=?"
                + " AND v.\"productionBaselineId\"=?"
                + cursor;
    }

    private Record ensureEditHead(
            DSLContext tx, String episodeId, String baselineId, boolean lock) {
        if (lock) {
            tx.execute(
                    "INSERT INTO \"VideoProductionEditHead\""
                            + " (\"episodeId\",\"productionBaselineId\",revision,\"updatedAt\")"
                            + " VALUES (?,?,1,?) ON CONFLICT"
                            + " (\"episodeId\",\"productionBaselineId\") DO NOTHING",
                    episodeId,
                    baselineId,
                    now());
        }
        return tx.fetchOne(
                "SELECT * FROM \"VideoProductionEditHead\" WHERE \"episodeId\"=?"
                        + " AND \"productionBaselineId\"=?"
                        + (lock ? " FOR UPDATE" : ""),
                episodeId,
                baselineId);
    }

    private Record ensureMixHead(
            DSLContext tx, String episodeId, String baselineId, boolean lock) {
        if (lock) {
            tx.execute(
                    "INSERT INTO \"VideoProductionMixHead\""
                            + " (\"episodeId\",\"productionBaselineId\",revision,\"updatedAt\")"
                            + " VALUES (?,?,1,?) ON CONFLICT"
                            + " (\"episodeId\",\"productionBaselineId\") DO NOTHING",
                    episodeId,
                    baselineId,
                    now());
        }
        return tx.fetchOne(
                "SELECT * FROM \"VideoProductionMixHead\" WHERE \"episodeId\"=?"
                        + " AND \"productionBaselineId\"=?"
                        + (lock ? " FOR UPDATE" : ""),
                episodeId,
                baselineId);
    }

    private static void requireHead(
            Record head, int expectedRevision, String basedOnVersionId, String code) {
        if (head == null
                || head.get("revision", Integer.class) != expectedRevision
                || !Objects.equals(
                        head.get("currentVersionId", String.class), basedOnVersionId)) {
            throw conflict(code, "后期 head 已变化，请保留输入并重新读取");
        }
    }

    private Record requireBaseline(DSLContext tx, Record episode, String baselineId) {
        Record row =
                tx.fetchOne(
                        "SELECT * FROM \"VideoProductionBaseline\" WHERE id=? AND"
                                + " \"episodeId\"=? AND \"projectId\"=?",
                        baselineId,
                        episode.get("id"),
                        episode.get("projectId"));
        if (row == null) {
            throw missing("VIDEO_PRODUCTION_BASELINE_NOT_FOUND", "制作基线不存在或不属于本集");
        }
        return row;
    }

    private Record requireEdit(
            DSLContext tx, String episodeId, String baselineId, String versionId) {
        Record row =
                tx.fetchOne(
                        "SELECT * FROM \"VideoEpisodeEditVersion\" WHERE id=? AND"
                                + " \"videoEpisodeId\"=? AND \"productionBaselineId\"=?",
                        versionId,
                        episodeId,
                        baselineId);
        if (row == null) {
            throw missing("VIDEO_EDIT_VERSION_NOT_FOUND", "粗剪版本不存在或不属于目标基线");
        }
        return row;
    }

    private Record requireMix(
            DSLContext tx, String episodeId, String baselineId, String versionId) {
        Record row =
                tx.fetchOne(
                        "SELECT * FROM \"VideoEpisodeMixVersion\" WHERE id=? AND"
                                + " \"videoEpisodeId\"=? AND \"productionBaselineId\"=?",
                        versionId,
                        episodeId,
                        baselineId);
        if (row == null) {
            throw missing("VIDEO_MIX_VERSION_NOT_FOUND", "声音字幕版本不存在或不属于目标基线");
        }
        return row;
    }

    private Map<String, String> baselineShots(
            DSLContext tx, String episodeId, String baselineId) {
        Map<String, String> result = new LinkedHashMap<>();
        tx.fetch(
                        "SELECT \"shotVersionId\",\"shotId\" FROM"
                                + " \"VideoProductionBaselineShot\" WHERE \"baselineId\"=?"
                                + " AND \"episodeId\"=? ORDER BY ordinal",
                        baselineId,
                        episodeId)
                .forEach(
                        row ->
                                result.put(
                                        row.get("shotVersionId", String.class),
                                        row.get("shotId", String.class)));
        if (result.isEmpty()) {
            throw conflict("VIDEO_BASELINE_SHOTS_MISSING", "制作基线缺少逐镜冻结输入");
        }
        return result;
    }

    private Record lockedAsset(
            DSLContext tx, Record episode, String assetId, String modality) {
        Record row =
                tx.fetchOne(
                        "SELECT * FROM \"VideoAsset\" WHERE id=? AND \"projectId\"=?"
                                + " AND modality=? AND \"durationMs\">0"
                                + " AND \"rightsStatus\"='confirmed' AND \"lockedAt\" IS NOT NULL",
                        assetId,
                        episode.get("projectId"),
                        modality);
        if (row == null) {
            throw invalid("VIDEO_MIX_ASSET_INVALID", "声音素材不存在、未锁定或不属于当前项目");
        }
        return row;
    }

    private FrozenAsset frozenAsset(Record row, String expectedModality) {
        String modality = row.get("modality", String.class);
        if (!expectedModality.equals(modality)
                || !"confirmed".equals(row.get("rightsStatus", String.class))
                || row.get("lockedAt") == null) {
            throw conflict("VIDEO_EXPORT_ASSET_INVALID", "导出素材未锁定或模态不匹配");
        }
        return new FrozenAsset(
                row.get("assetId", String.class),
                row.get("storageKey", String.class),
                row.get("sha256", String.class),
                row.get("mimeType", String.class),
                row.get("durationMs", Integer.class));
    }

    private Set<String> scriptLineIds(DSLContext tx, String scriptVersionId) {
        Record script =
                tx.fetchOne(
                        "SELECT \"documentJson\" FROM \"VideoEpisodeScriptVersion\" WHERE id=?",
                        scriptVersionId);
        if (script == null) {
            throw conflict("VIDEO_SCRIPT_VERSION_MISSING", "制作基线引用的正式剧本不存在");
        }
        Set<String> result = new HashSet<>();
        JsonNode document = json.readTree(script.get("documentJson", String.class));
        document.path("scenes")
                .forEach(
                        scene ->
                                scene.path("lines")
                                        .forEach(
                                                line -> {
                                                    String id = text(line, "id");
                                                    if (id != null) result.add(id);
                                                }));
        return result;
    }

    private boolean shotContainsLine(DSLContext tx, String shotVersionId, String scriptLineId) {
        Record shot =
                tx.fetchOne(
                        "SELECT \"scriptLineIdsJson\" FROM \"VideoShotVersion\" WHERE id=?",
                        shotVersionId);
        if (shot == null) return false;
        String encoded = shot.get("scriptLineIdsJson", String.class);
        for (JsonNode value : json.readTree(encoded)) {
            if (scriptLineId.equals(value.asText())) return true;
        }
        return false;
    }

    private void requireNoActiveExport(DSLContext tx, String episodeId) {
        Boolean active =
                tx.fetchOne(
                                "SELECT EXISTS(SELECT 1 FROM \"VideoEpisodeExportTask\""
                                        + " WHERE \"videoEpisodeId\"=?"
                                        + " AND status IN ('pending','rendering')) active",
                                episodeId)
                        .get("active", Boolean.class);
        if (Boolean.TRUE.equals(active)) {
            throw conflict("VIDEO_EXPORT_TASK_ACTIVE", "本集已有导出任务正在执行");
        }
    }

    private int nextVersion(DSLContext tx, String table, String episodeId) {
        return tx.fetchOne(
                        "SELECT COALESCE(MAX(\"versionNo\"),0)+1 n FROM \""
                                + table
                                + "\" WHERE \"videoEpisodeId\"=?",
                        episodeId)
                .get("n", Integer.class);
    }

    private int checkedLimit(int limit) {
        if (limit < 1 || limit > 100) {
            throw invalid("VIDEO_PAGE_LIMIT_INVALID", "分页数量须为 1 至 100");
        }
        return limit;
    }

    private static void validateTransition(
            String transition, int transitionDuration, int clipDuration) {
        if (!Set.of("cut", "fade_black").contains(transition)
                || transitionDuration < 0
                || transitionDuration > 2_000
                || "cut".equals(transition) && transitionDuration != 0
                || "fade_black".equals(transition) && transitionDuration == 0
                || transitionDuration * 2 > clipDuration) {
            throw invalid("VIDEO_EDIT_TRANSITION_INVALID", "粗剪转场参数无效");
        }
    }

    private ObjectNode write(
            String userId,
            String episodeId,
            String operation,
            ObjectNode commandRequest,
            Work work) {
        String clientRequestId = requiredRequestId(commandRequest);
        String requestHash = hash(commandRequest);
        return database.transactionResult(
                tx -> {
                    // VideoEpisodeCommand 的唯一键横跨剧本、制作和后期入口。必须先用同一
                    // advisory namespace 串行，再进入统一 Episode→子资源锁序。
                    tx.fetchOne(
                            "SELECT pg_advisory_xact_lock(hashtextextended(?,0))",
                            "video-episode-command:" + userId + ":" + clientRequestId);
                    Record episode = owned(tx, userId, episodeId, true);
                    Record previous =
                            tx.fetchOne(
                                    "SELECT * FROM \"VideoEpisodeCommand\" WHERE"
                                            + " \"actorUserId\"=? AND \"clientRequestId\"=?",
                                    userId,
                                    clientRequestId);
                    if (previous != null) {
                        if (!episodeId.equals(previous.get("episodeId"))
                                || !operation.equals(previous.get("operation"))
                                || !requestHash.equals(previous.get("requestHash"))) {
                            throw conflict(
                                    "VIDEO_EPISODE_CLIENT_REQUEST_REUSED",
                                    "clientRequestId 已用于不同请求");
                        }
                        return (ObjectNode)
                                json.readTree(previous.get("resultJson", String.class));
                    }
                    ObjectNode result = work.run(tx, episode);
                    tx.execute(
                            "INSERT INTO \"VideoEpisodeCommand\""
                                    + " (id,\"actorUserId\",\"clientRequestId\",\"projectId\","
                                    + " \"novelId\",\"episodeId\",operation,\"requestHash\","
                                    + " \"resultJson\",\"createdAt\") VALUES (?,?,?,?,?,?,?,?,?,?)",
                            ids.next(),
                            userId,
                            clientRequestId,
                            episode.get("projectId"),
                            episode.get("novelId"),
                            episodeId,
                            operation,
                            requestHash,
                            result.toString(),
                            now());
                    return result;
                });
    }

    private ObjectNode read(String userId, String episodeId, Work work) {
        return database.transactionResult(tx -> work.run(tx, owned(tx, userId, episodeId, false)));
    }

    private Record owned(DSLContext tx, String userId, String episodeId, boolean lock) {
        String query =
                "SELECT e.* FROM \"VideoEpisode\" e JOIN \"VideoProject\" p"
                        + " ON p.id=e.\"projectId\" JOIN \"Novel\" n ON n.id=p.\"novelId\""
                        + " WHERE e.id=? AND e.\"archivedAt\" IS NULL AND n.\"userId\"=?"
                        + (lock ? " FOR UPDATE OF e" : "");
        Record episode = tx.fetchOne(query, episodeId, userId);
        if (episode == null) {
            throw missing("VIDEO_EPISODE_NOT_FOUND", "分集不存在");
        }
        return episode;
    }

    private ObjectNode commandRequest(
            JsonNode request, String baselineId, String taskId) {
        if (!request.isObject()) {
            throw invalid("VIDEO_EPISODE_INPUT_INVALID", "请求必须是对象");
        }
        ObjectNode value = (ObjectNode) request.deepCopy();
        value.put("_productionBaselineId", baselineId);
        if (taskId != null) value.put("_taskId", taskId);
        return value;
    }

    private String requiredRequestId(JsonNode request) {
        String value = requiredText(request, "clientRequestId").strip();
        int length = value.codePointCount(0, value.length());
        if (length < 16 || length > 128) {
            throw invalid("VIDEO_EPISODE_INPUT_INVALID", "clientRequestId 长度无效");
        }
        return value;
    }

    private ObjectNode object(Object... values) {
        ObjectNode result = json.createObjectNode();
        for (int index = 0; index < values.length; index += 2) {
            Object value = values[index + 1];
            result.set(
                    (String) values[index],
                    json.valueToTree(
                            value instanceof OffsetDateTime time ? time.toString() : value));
        }
        return result;
    }

    private String hash(JsonNode node) {
        return sha(canonical(node));
    }

    private String canonical(JsonNode node) {
        if (node.isObject()) {
            var sorted = new java.util.TreeMap<String, JsonNode>();
            node.properties().forEach(entry -> sorted.put(entry.getKey(), entry.getValue()));
            return "{"
                    + sorted.entrySet().stream()
                            .map(
                                    entry ->
                                            json.writeValueAsString(entry.getKey())
                                                    + ":"
                                                    + canonical(entry.getValue()))
                            .collect(java.util.stream.Collectors.joining(","))
                    + "}";
        }
        if (node.isArray()) {
            List<String> values = new ArrayList<>();
            node.forEach(value -> values.add(canonical(value)));
            return "[" + String.join(",", values) + "]";
        }
        return node.toString();
    }

    private static String sha(String value) {
        try {
            return HexFormat.of()
                    .formatHex(
                            MessageDigest.getInstance("SHA-256")
                                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (java.security.NoSuchAlgorithmException error) {
            throw new IllegalStateException(error);
        }
    }

    private LocalDateTime now() {
        return DatabaseTimestamp.now(clock);
    }

    private static OffsetDateTime apiTime(Record row, String column) {
        return DatabaseTimestamp.api(row.get(column, LocalDateTime.class));
    }

    private static String text(JsonNode node, String key) {
        return node.hasNonNull(key) ? node.path(key).asText() : null;
    }

    private static String requiredText(JsonNode node, String key) {
        String value = text(node, key);
        if (value == null || value.isBlank()) {
            throw invalid("VIDEO_EPISODE_INPUT_INVALID", key + " 不能为空");
        }
        return value;
    }

    private static ApiException invalid(String code, String message) {
        return new ApiException(422, code, message);
    }

    private static ApiException conflict(String code, String message) {
        return new ApiException(409, code, message);
    }

    private static ApiException missing(String code, String message) {
        return new ApiException(404, code, message);
    }

    @FunctionalInterface
    private interface Work {
        ObjectNode run(DSLContext tx, Record episode);
    }

    private record EditClip(
            String clipId,
            int ordinal,
            String adoptionId,
            String takeId,
            String shotId,
            String shotVersionId,
            int sourceInMs,
            int sourceOutMs,
            int timelineStartMs,
            int outputDurationMs,
            String sourceAudioMode,
            String transitionAfter,
            int transitionDurationMs) {}

    private record AudioClip(
            int ordinal,
            String trackKind,
            String assetId,
            String shotId,
            String shotVersionId,
            int timelineStartMs,
            int sourceInMs,
            int sourceOutMs,
            int gainMillibels,
            int fadeInMs,
            int fadeOutMs) {}

    private record SubtitleCue(
            int ordinal,
            String shotId,
            String shotVersionId,
            String scriptLineId,
            int startMs,
            int endMs,
            String speaker,
            String text) {}
}
