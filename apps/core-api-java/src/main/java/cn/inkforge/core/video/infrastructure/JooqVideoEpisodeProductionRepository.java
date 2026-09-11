package cn.inkforge.core.video.infrastructure;

import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.video.application.VideoEpisodeProductionRepository;
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
 * 独立剧集的分镜与制作基线仓储。
 *
 * <p>稳定镜头身份只在工作稿保存事务内由 Core 分配；正式分镜、逐镜版本和制作基线只追加，head 切换使用显式
 * revision。旧基线因此不会在新版剧本或分镜确认时被悄悄改写。
 */
public final class JooqVideoEpisodeProductionRepository
        implements VideoEpisodeProductionRepository {
    private static final Set<String> FRAMINGS =
            Set.of(
                    "extreme_wide",
                    "wide",
                    "medium",
                    "close_up",
                    "detail",
                    "over_shoulder",
                    "pov");
    private static final Set<String> CAMERA_MOVEMENTS =
            Set.of(
                    "static",
                    "pan",
                    "tilt",
                    "dolly",
                    "truck",
                    "crane",
                    "handheld",
                    "orbit",
                    "zoom");
    private static final Set<String> KEYFRAME_ROLES =
            Set.of("initial_state", "transition_anchor", "end_state");
    private static final Set<String> KEYFRAME_DUTIES =
            Set.of("identity", "costume", "scene", "prop", "storyboard", "keyframe");
    private static final Set<String> IMAGE_MIME_TYPES =
            Set.of("image/jpeg", "image/png", "image/webp");

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final ObjectMapper json;
    private final String seedanceModel;
    private final String executionMode;
    private final boolean seedanceConfigured;
    private final boolean seedanceEnabled;
    private final boolean videoPreviewEnabled;

    public JooqVideoEpisodeProductionRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock clock,
            ObjectMapper json,
            String seedanceModel,
            String executionMode,
            boolean seedanceConfigured,
            boolean seedanceEnabled,
            boolean videoPreviewEnabled) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
        this.seedanceModel = Objects.requireNonNull(seedanceModel);
        this.executionMode = Objects.requireNonNull(executionMode);
        this.seedanceConfigured = seedanceConfigured;
        this.seedanceEnabled = seedanceEnabled;
        this.videoPreviewEnabled = videoPreviewEnabled;
    }

    @Override
    public ObjectNode capabilities() {
        return object(
                "provider",
                "seedance",
                "model",
                seedanceModel,
                "generationMode",
                "reference",
                "executionMode",
                executionMode,
                "feeConfirmationRequired",
                "live".equals(executionMode),
                "videoPreviewEnabled",
                videoPreviewEnabled,
                "providerConfigured",
                seedanceConfigured,
                "providerEnabled",
                seedanceEnabled,
                "allowedDurationSeconds",
                List.of(4, 5, 6, 7, 8, 9, 10, 11, 12),
                "allowedResolution",
                "720p",
                "allowedOutputFormat",
                "mp4",
                "maxImageReferences",
                20);
    }

    @Override
    public ObjectNode getStoryboardDraft(String userId, String episodeId) {
        return read(userId, episodeId, (tx, episode) -> draft(tx, episodeId, Map.of()));
    }

    @Override
    public ObjectNode saveStoryboardDraft(String userId, String episodeId, JsonNode request) {
        return write(
                userId,
                episodeId,
                "episode.storyboard.save",
                request,
                (tx, episode) -> {
                    Record current = requireDraft(tx, episodeId);
                    requireRevision(
                            current,
                            request.path("expectedRevision").asInt(),
                            "VIDEO_STORYBOARD_DRAFT_REVISION_CONFLICT");
                    String scriptVersionId = requiredText(request, "scriptVersionId");
                    Record script = requireScriptVersion(tx, episodeId, scriptVersionId);
                    String baseVersionId = text(request, "baseStoryboardVersionId");
                    JsonNode baseDocument = null;
                    if (baseVersionId != null) {
                        baseDocument =
                                requireStoryboardVersion(tx, episodeId, baseVersionId)
                                        .map(r -> parse(r, "documentJson"))
                                        .orElseThrow();
                    }
                    Map<String, String> mappings = new LinkedHashMap<>();
                    ObjectNode document =
                            normalizeDocument(
                                    tx,
                                    episode,
                                    script,
                                    request.path("document"),
                                    parse(current, "documentJson"),
                                    baseDocument,
                                    userId,
                                    mappings);
                    tx.execute(
                            "UPDATE \"VideoStoryboardDraft\" SET"
                                    + " \"basedOnStoryboardVersionId\"=?,\"scriptVersionId\"=?,\"documentJson\"=?,\"contentHash\"=?,revision=revision+1,\"updatedAt\"=?"
                                    + " WHERE \"episodeId\"=?",
                            baseVersionId,
                            scriptVersionId,
                            document.toString(),
                            hash(document),
                            now(),
                            episodeId);
                    return draft(tx, episodeId, mappings);
                });
    }

    @Override
    public ObjectNode prepareStoryboardConfirmation(
            String userId, String episodeId, JsonNode request) {
        return write(
                userId,
                episodeId,
                "episode.storyboard.prepare",
                request,
                (tx, episode) -> {
                    Record current = requireDraft(tx, episodeId);
                    requireRevision(
                            episode,
                            request.path("expectedEpisodeRevision").asInt(),
                            "VIDEO_EPISODE_REVISION_CONFLICT");
                    requireRevision(
                            current,
                            request.path("expectedDraftRevision").asInt(),
                            "VIDEO_STORYBOARD_DRAFT_REVISION_CONFLICT");
                    String scriptVersionId = current.get("scriptVersionId", String.class);
                    if (scriptVersionId == null) {
                        throw invalid("VIDEO_STORYBOARD_SCRIPT_REQUIRED", "确认分镜前必须选择正式剧本版本");
                    }
                    Record script = requireScriptVersion(tx, episodeId, scriptVersionId);
                    ObjectNode document =
                            normalizeDocument(
                                    tx,
                                    episode,
                                    script,
                                    parse(current, "documentJson"),
                                    parse(current, "documentJson"),
                                    null,
                                    userId,
                                    new LinkedHashMap<>());
                    requireConfirmable(document);
                    ObjectNode payload =
                            object(
                                    "applyTarget",
                                    "video_episode_storyboard_confirmation",
                                    "episodeId",
                                    episodeId,
                                    "episodeRevision",
                                    episode.get("revision"),
                                    "draftRevision",
                                    current.get("revision"),
                                    "scriptVersionId",
                                    scriptVersionId,
                                    "baseStoryboardVersionId",
                                    current.get("basedOnStoryboardVersionId"),
                                    "document",
                                    document);
                    payload.put("confirmationHash", hash(payload));
                    String artifactId = insertArtifact(tx, episode, payload);
                    return confirmation(tx, episodeId, artifactId);
                });
    }

    @Override
    public ObjectNode getStoryboardConfirmation(
            String userId, String episodeId, String artifactId) {
        return read(userId, episodeId, (tx, episode) -> confirmation(tx, episodeId, artifactId));
    }

    @Override
    public ObjectNode approveStoryboardConfirmation(
            String userId, String episodeId, String artifactId, JsonNode request) {
        ObjectNode command = (ObjectNode) request.deepCopy();
        command.put("artifactId", artifactId);
        return write(
                userId,
                episodeId,
                "episode.storyboard.approve",
                command,
                (tx, episode) -> {
                    Record artifact = requireArtifact(tx, episodeId, artifactId);
                    ObjectNode payload = parse(artifact, "payloadJson");
                    Record current = requireDraft(tx, episodeId);
                    requireTarget(payload, "video_episode_storyboard_confirmation");
                    requireRevision(
                            artifact,
                            request.path("expectedArtifactRevision").asInt(),
                            "VIDEO_ARTIFACT_REVISION_CONFLICT");
                    requireRevision(
                            episode,
                            request.path("expectedEpisodeRevision").asInt(),
                            "VIDEO_EPISODE_REVISION_CONFLICT");
                    requireRevision(
                            current,
                            request.path("expectedDraftRevision").asInt(),
                            "VIDEO_STORYBOARD_DRAFT_REVISION_CONFLICT");
                    if (!"awaiting_user".equals(artifact.get("status", String.class))
                            || payload.path("episodeRevision").asInt()
                                    != episode.get("revision", Integer.class)
                            || payload.path("draftRevision").asInt()
                                    != current.get("revision", Integer.class)
                            || !payload.path("confirmationHash")
                                    .asText()
                                    .equals(request.path("confirmationHash").asText())
                            || !payload.path("document").equals(parse(current, "documentJson"))) {
                        throw conflict(
                                "VIDEO_STORYBOARD_CONFIRMATION_CHANGED",
                                "待确认分镜或工作稿已经变化，请重新准备确认");
                    }
                    String scriptVersionId = requiredText(payload, "scriptVersionId");
                    Record script = requireScriptVersion(tx, episodeId, scriptVersionId);
                    ObjectNode document =
                            normalizeDocument(
                                    tx,
                                    episode,
                                    script,
                                    payload.path("document"),
                                    payload.path("document"),
                                    null,
                                    userId,
                                    new LinkedHashMap<>());
                    requireConfirmable(document);

                    String versionId = ids.next();
                    int versionNo = nextVersion(tx, "VideoStoryboardVersion", episodeId);
                    tx.execute(
                            "INSERT INTO \"VideoStoryboardVersion\""
                                    + " (id,\"episodeId\",\"projectId\",\"versionNo\",\"basedOnVersionId\",\"scriptVersionId\",\"documentJson\",\"contentHash\",\"reviewArtifactId\",\"approvedByUserId\",\"createdAt\")"
                                    + " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                            versionId,
                            episodeId,
                            episode.get("projectId"),
                            versionNo,
                            text(payload, "baseStoryboardVersionId"),
                            scriptVersionId,
                            document.toString(),
                            hash(document),
                            artifactId,
                            userId,
                            now());
                    int ordinal = 0;
                    for (JsonNode shot : document.path("shots")) {
                        ordinal++;
                        String shotId = requiredText(shot, "id");
                        int shotVersionNo =
                                tx.fetchOne(
                                                "SELECT COALESCE(MAX(\"versionNo\"),0)+1 n FROM"
                                                        + " \"VideoShotVersion\" WHERE \"shotId\"=?",
                                                shotId)
                                        .get("n", Integer.class);
                        tx.execute(
                                "INSERT INTO \"VideoShotVersion\""
                                        + " (id,\"shotId\",\"episodeId\",\"projectId\",\"storyboardVersionId\",ordinal,\"versionNo\",\"scriptSceneId\",\"scriptLineIdsJson\",\"contentJson\",\"contentHash\",\"createdAt\")"
                                        + " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                                ids.next(),
                                shotId,
                                episodeId,
                                episode.get("projectId"),
                                versionId,
                                ordinal,
                                shotVersionNo,
                                requiredText(shot, "scriptSceneId"),
                                shot.path("scriptLineIds").toString(),
                                shot.toString(),
                                hash(shot),
                                now());
                    }
                    tx.execute(
                            "UPDATE \"VideoEpisode\" SET"
                                    + " \"currentStoryboardVersionId\"=?,revision=revision+1,\"updatedAt\"=? WHERE id=?",
                            versionId,
                            now(),
                            episodeId);
                    tx.execute(
                            "UPDATE \"VideoStoryboardDraft\" SET"
                                    + " \"basedOnStoryboardVersionId\"=?,revision=revision+1,\"updatedAt\"=? WHERE \"episodeId\"=?",
                            versionId,
                            now(),
                            episodeId);
                    applyArtifact(tx, artifactId);
                    return storyboardVersion(tx, episodeId, versionId);
                });
    }

    @Override
    public ObjectNode listStoryboardVersions(
            String userId, String episodeId, Integer beforeVersionNo, int limit) {
        return read(
                userId,
                episodeId,
                (tx, episode) ->
                        pagedStoryboardVersions(tx, episodeId, beforeVersionNo, checkedLimit(limit)));
    }

    @Override
    public ObjectNode getStoryboardVersion(
            String userId, String episodeId, String versionId) {
        return read(
                userId,
                episodeId,
                (tx, episode) -> storyboardVersion(tx, episodeId, versionId));
    }

    @Override
    public ObjectNode createTakeAdoption(String userId, String episodeId, JsonNode request) {
        return write(
                userId,
                episodeId,
                "episode.take-adoption.create",
                request,
                (tx, episode) -> {
                    if (episode.get("productionRevision", Integer.class)
                            != request.path("expectedProductionRevision").asInt()) {
                        throw conflict(
                                "VIDEO_PRODUCTION_BASELINE_REVISION_CONFLICT",
                                "制作基线已经变化，请重新核对素材采用依据");
                    }
                    String targetShotVersionId =
                            requiredText(request, "targetShotVersionId");
                    Record target =
                            tx.fetchOne(
                                    "SELECT * FROM \"VideoShotVersion\" WHERE id=? AND"
                                            + " \"episodeId\"=? AND \"projectId\"=?",
                                    targetShotVersionId,
                                    episodeId,
                                    episode.get("projectId"));
                    if (target == null) {
                        throw invalid(
                                "VIDEO_TAKE_ADOPTION_TARGET_INVALID",
                                "采用目标必须是当前分集的正式镜头版本");
                    }
                    String sourceTakeId = requiredText(request, "sourceTakeId");
                    String sourceBaselineId = requiredText(request, "sourceBaselineId");
                    Record source =
                            tx.fetchOne(
                                    "SELECT t.* FROM \"VideoShotTake\" t"
                                            + " JOIN \"VideoAsset\" a ON a.id=t.\"assetId\""
                                            + " AND a.\"projectId\"=t.\"projectId\""
                                            + " JOIN \"VideoProductionBaselineShot\" bs"
                                            + " ON bs.\"baselineId\"=t.\"productionBaselineId\""
                                            + " AND bs.\"episodeId\"=t.\"videoEpisodeId\""
                                            + " AND bs.\"shotId\"=t.\"episodeShotId\""
                                            + " AND bs.\"shotVersionId\"=t.\"episodeShotVersionId\""
                                            + " WHERE t.id=? AND t.\"videoEpisodeId\"=?"
                                            + " AND t.\"projectId\"=? AND t.\"productionBaselineId\"=?"
                                            + " AND t.provider='seedance' AND a.modality='video'"
                                            + " AND a.\"mimeType\"='video/mp4' AND a.\"durationMs\">0"
                                            + " AND a.\"rightsStatus\"='confirmed'"
                                            + " AND a.\"lockedAt\" IS NOT NULL",
                                    sourceTakeId,
                                    episodeId,
                                    episode.get("projectId"),
                                    sourceBaselineId);
                    if (source == null) {
                        throw invalid(
                                "VIDEO_TAKE_ADOPTION_SOURCE_INVALID",
                                "只能采用同项目、同分集且生成依据明确的不可变 Take");
                    }
                    requireBaseline(tx, episodeId, sourceBaselineId);
                    JsonNode comparison = request.path("comparison");
                    if (!comparison.isObject()
                            || !sourceBaselineId.equals(
                                    comparison.path("sourceBaselineId").asText())
                            || !targetShotVersionId.equals(
                                    comparison.path("targetShotVersionId").asText())
                            || requiredText(comparison, "summary").length() > 4_000) {
                        throw invalid(
                                "VIDEO_TAKE_ADOPTION_COMPARISON_INVALID",
                                "素材采用必须冻结源基线、目标镜头版本和人工核对说明");
                    }
                    ObjectNode decision =
                            object(
                                    "episodeId",
                                    episodeId,
                                    "targetShotVersionId",
                                    targetShotVersionId,
                                    "sourceTakeId",
                                    sourceTakeId,
                                    "sourceBaselineId",
                                    sourceBaselineId,
                                    "comparison",
                                    comparison);
                    String id = ids.next();
                    tx.execute(
                            "INSERT INTO \"VideoTakeAdoption\""
                                    + " (id,\"episodeId\",\"projectId\",\"targetShotId\",\"targetShotVersionId\",\"sourceTakeId\",\"sourceBaselineId\",\"comparisonJson\",\"decisionHash\",\"createdByUserId\",\"createdAt\")"
                                    + " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                            id,
                            episodeId,
                            episode.get("projectId"),
                            target.get("shotId"),
                            targetShotVersionId,
                            sourceTakeId,
                            sourceBaselineId,
                            comparison.toString(),
                            hash(decision),
                            userId,
                            now());
                    return adoption(tx, episodeId, id);
                });
    }

    @Override
    public ObjectNode getTakeAdoption(String userId, String episodeId, String adoptionId) {
        return read(userId, episodeId, (tx, episode) -> adoption(tx, episodeId, adoptionId));
    }

    @Override
    public ObjectNode listTakeCandidates(
            String userId,
            String episodeId,
            String targetShotVersionId,
            String beforeTakeId,
            int limit) {
        return read(
                userId,
                episodeId,
                (tx, episode) -> {
                    Record target =
                            tx.fetchOne(
                                    "SELECT id FROM \"VideoShotVersion\" WHERE id=? AND"
                                            + " \"episodeId\"=? AND \"projectId\"=?",
                                    targetShotVersionId,
                                    episodeId,
                                    episode.get("projectId"));
                    if (target == null) {
                        throw invalid(
                                "VIDEO_TAKE_TARGET_INVALID",
                                "Take 候选目标必须是当前分集的正式镜头版本");
                    }
                    return takeCandidates(
                            tx,
                            episode,
                            targetShotVersionId,
                            beforeTakeId,
                            checkedLimit(limit));
                });
    }

    @Override
    public ObjectNode createProductionBaseline(
            String userId, String episodeId, JsonNode request) {
        return write(
                userId,
                episodeId,
                "episode.production-baseline.create",
                request,
                (tx, episode) -> {
                    requireRevision(
                            episode,
                            request.path("expectedEpisodeRevision").asInt(),
                            "VIDEO_EPISODE_REVISION_CONFLICT");
                    int expectedProductionRevision =
                            request.path("expectedProductionRevision").asInt();
                    if (episode.get("productionRevision", Integer.class)
                            != expectedProductionRevision) {
                        throw conflict(
                                "VIDEO_PRODUCTION_BASELINE_REVISION_CONFLICT",
                                "制作基线已经变化，请保留选择并重新读取");
                    }
                    String storyboardVersionId =
                            requiredText(request, "storyboardVersionId");
                    String scriptVersionId = requiredText(request, "scriptVersionId");
                    Record storyboard =
                            requireStoryboardVersion(tx, episodeId, storyboardVersionId)
                                    .orElseThrow();
                    if (!scriptVersionId.equals(storyboard.get("scriptVersionId"))) {
                        throw invalid(
                                "VIDEO_PRODUCTION_BASELINE_SCRIPT_MISMATCH",
                                "制作基线的剧本与分镜冻结依据不一致");
                    }
                    String basedOn = text(request, "basedOnBaselineId");
                    String current = episode.get("currentProductionBaselineId", String.class);
                    if (!Objects.equals(current, basedOn)) {
                        throw conflict(
                                "VIDEO_PRODUCTION_BASELINE_HEAD_CHANGED",
                                "制作基线 head 已变化，请基于当前版本重新确认");
                    }
                    if (basedOn != null) {
                        requireBaseline(tx, episodeId, basedOn);
                    }
                    List<Record> shots =
                            tx.fetch(
                                    "SELECT * FROM \"VideoShotVersion\" WHERE"
                                            + " \"storyboardVersionId\"=? AND \"episodeId\"=? ORDER BY ordinal",
                                    storyboardVersionId,
                                    episodeId);
                    if (shots.isEmpty()) {
                        throw invalid("VIDEO_PRODUCTION_BASELINE_EMPTY", "空分镜不能创建制作基线");
                    }
                    Map<String, Record> adoptions =
                            baselineAdoptions(
                                    tx, episode, shots, request.path("shotAdoptions"));
                    String baselineId = ids.next();
                    Map<String, List<ObjectNode>> keyframes =
                            baselineKeyframes(
                                    tx,
                                    episode,
                                    shots,
                                    request.path("keyframes"),
                                    baselineId,
                                    requiredText(request, "clientRequestId"),
                                    userId);
                    ArrayNode manifestShots = json.createArrayNode();
                    List<ObjectNode> frozenShots = new ArrayList<>();
                    for (Record shot : shots) {
                        ObjectNode shotContent = parse(shot, "contentJson");
                        ObjectNode generation =
                                (ObjectNode) shotContent.path("productionIntent").deepCopy();
                        freezeReferences(tx, episode, generation);
                        List<ObjectNode> shotKeyframes =
                                keyframes.getOrDefault(shot.get("id", String.class), List.of());
                        if (generation.path("references").size() + shotKeyframes.size() > 20) {
                            throw invalid(
                                    "VIDEO_PRODUCTION_IMAGE_LIMIT_EXCEEDED",
                                    "单镜视觉参考与关键帧合计不能超过 20 张");
                        }
                        String providerPrompt =
                                providerPrompt(
                                        generation.path("prompt").asText(),
                                        generation.path("references").size(),
                                        shotKeyframes);
                        String promptVersionId = ids.next();
                        int promptVersionNo =
                                tx.fetchOne(
                                                "SELECT COALESCE(MAX(\"versionNo\"),0)+1 n FROM"
                                                        + " \"VideoShotPromptVersion\" WHERE"
                                                        + " \"episodeShotId\"=?",
                                                shot.get("shotId"))
                                        .get("n", Integer.class);
                        ObjectNode inputSnapshot =
                                object(
                                        "schemaVersion",
                                        "video-production-shot-input/1.2",
                                        "shotId",
                                        shot.get("shotId"),
                                        "shotVersionId",
                                        shot.get("id"),
                                        "shotVersionNo",
                                        shot.get("versionNo"),
                                        "shotContentHash",
                                        shot.get("contentHash"),
                                        "scriptSceneId",
                                        shot.get("scriptSceneId"),
                                        "scriptLineIds",
                                        json.readTree(
                                                shot.get("scriptLineIdsJson", String.class)),
                                        "provider",
                                        generation.path("provider"),
                                        "model",
                                        generation.path("model"),
                                        "generationMode",
                                        generation.path("generationMode"),
                                        "executionMode",
                                        generation.path("executionMode"),
                                        "feeConfirmed",
                                        generation.path("feeConfirmed"),
                                        "promptVersionId",
                                        promptVersionId,
                                        "prompt",
                                        providerPrompt,
                                        "ratio",
                                        generation.path("ratio"),
                                        "durationSeconds",
                                        generation.path("durationSeconds"),
                                        "resolution",
                                        generation.path("resolution"),
                                        "generateAudio",
                                        generation.path("generateAudio"),
                                        "watermark",
                                        generation.path("watermark"),
                                        "outputFormat",
                                        generation.path("outputFormat"),
                                        "references",
                                        generation.path("references"),
                                        "keyframes",
                                        shotKeyframes.stream()
                                                .map(this::keyframeSnapshot)
                                                .toList());
                        Record adoption = adoptions.get(shot.get("id", String.class));
                        ObjectNode manifestShot =
                                object(
                                        "ordinal",
                                        shot.get("ordinal"),
                                        "shotId",
                                        shot.get("shotId"),
                                        "shotVersionId",
                                        shot.get("id"),
                                        "adoptionId",
                                        adoption == null ? null : adoption.get("id"),
                                        "inputHash",
                                        hash(inputSnapshot));
                        manifestShots.add(manifestShot);
                        frozenShots.add(
                                object(
                                        "ordinal",
                                        shot.get("ordinal"),
                                        "shotId",
                                        shot.get("shotId"),
                                        "shotVersionId",
                                        shot.get("id"),
                                        "adoptionId",
                                        adoption == null ? null : adoption.get("id"),
                                        "promptVersionId",
                                        promptVersionId,
                                        "promptVersionNo",
                                        promptVersionNo,
                                        "promptText",
                                        providerPrompt,
                                        "status",
                                        adoption == null ? "pending" : "adopted",
                                        "inputSnapshot",
                                        inputSnapshot,
                                        "inputHash",
                                        hash(inputSnapshot),
                                        "keyframeRows",
                                        shotKeyframes));
                    }
                    ObjectNode manifest =
                            object(
                                    "schemaVersion",
                                    "video-production-baseline/1.0",
                                    "episodeId",
                                    episodeId,
                                    "scriptVersionId",
                                    scriptVersionId,
                                    "storyboardVersionId",
                                    storyboardVersionId,
                                    "shots",
                                    manifestShots);
                    int versionNo = nextVersion(tx, "VideoProductionBaseline", episodeId);
                    tx.execute(
                            "INSERT INTO \"VideoProductionBaseline\""
                                    + " (id,\"episodeId\",\"projectId\",\"versionNo\",\"basedOnBaselineId\",\"scriptVersionId\",\"storyboardVersionId\",\"manifestJson\",\"contentHash\",\"createdByUserId\",\"createdAt\")"
                                    + " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                            baselineId,
                            episodeId,
                            episode.get("projectId"),
                            versionNo,
                            basedOn,
                            scriptVersionId,
                            storyboardVersionId,
                            manifest.toString(),
                            hash(manifest),
                            userId,
                            now());
                    for (ObjectNode shot : frozenShots) {
                        tx.execute(
                                "INSERT INTO \"VideoProductionBaselineShot\""
                                        + " (\"baselineId\",\"episodeId\",\"projectId\",ordinal,\"shotId\",\"shotVersionId\",\"adoptionId\",status,\"inputSnapshotJson\",\"inputHash\")"
                                        + " VALUES (?,?,?,?,?,?,?,?,?,?)",
                                baselineId,
                                episodeId,
                                episode.get("projectId"),
                                shot.path("ordinal").asInt(),
                                text(shot, "shotId"),
                                text(shot, "shotVersionId"),
                                text(shot, "adoptionId"),
                                text(shot, "status"),
                                shot.path("inputSnapshot").toString(),
                                text(shot, "inputHash"));
                        tx.execute(
                                "INSERT INTO \"VideoShotPromptVersion\""
                                        + " (id,\"shotId\",\"shotPlanVersionId\",\"sourceTaskId\",\"versionNo\",\"basedOnVersionId\",\"generatedText\",\"currentText\",\"contentHash\",\"createdByUserId\",\"createdAt\",\"videoEpisodeId\",\"episodeShotId\",\"episodeShotVersionId\",\"productionBaselineId\")"
                                        + " VALUES (?,NULL,NULL,NULL,?,NULL,NULL,?,?,?,?,?,?,?,?)",
                                text(shot, "promptVersionId"),
                                shot.path("promptVersionNo").asInt(),
                                text(shot, "promptText"),
                                sha(text(shot, "promptText")),
                                userId,
                                now(),
                                episodeId,
                                text(shot, "shotId"),
                                text(shot, "shotVersionId"),
                                baselineId);
                        for (JsonNode keyframe : shot.path("keyframeRows")) {
                            tx.execute(
                                    "INSERT INTO \"VideoShotKeyframeVersion\""
                                            + " (id,\"adaptationId\",\"projectId\",\"novelId\",\"shotId\",\"shotPlanVersionId\",role,\"versionNo\",\"basedOnVersionId\",\"assetId\",\"sourceKind\",\"sourceTakeId\",\"sourceTimeMs\",\"clientRequestId\",\"requestHash\",\"contentHash\",\"createdByUserId\",\"createdAt\",\"videoEpisodeId\",\"episodeShotId\",\"episodeShotVersionId\",\"productionBaselineId\")"
                                            + " VALUES (?,NULL,?,?,NULL,NULL,?,?,NULL,?,'asset',NULL,NULL,?,?,?,?,?,?,?,?,?)",
                                    text(keyframe, "keyframeVersionId"),
                                    episode.get("projectId"),
                                    episode.get("novelId"),
                                    text(keyframe, "role"),
                                    keyframe.path("versionNo").asInt(),
                                    text(keyframe, "assetId"),
                                    text(keyframe, "clientRequestId"),
                                    text(keyframe, "requestHash"),
                                    text(keyframe, "contentHash"),
                                    userId,
                                    now(),
                                    episodeId,
                                    text(shot, "shotId"),
                                    text(shot, "shotVersionId"),
                                    baselineId);
                        }
                    }
                    tx.execute(
                            "UPDATE \"VideoEpisode\" SET"
                                    + " \"currentProductionBaselineId\"=?,\"productionRevision\"=\"productionRevision\"+1,revision=revision+1,\"updatedAt\"=?"
                                    + " WHERE id=?",
                            baselineId,
                            now(),
                            episodeId);
                    return baseline(tx, episodeId, baselineId);
                });
    }

    @Override
    public ObjectNode listProductionBaselines(
            String userId, String episodeId, Integer beforeVersionNo, int limit) {
        return read(
                userId,
                episodeId,
                (tx, episode) ->
                        pagedBaselines(tx, episodeId, beforeVersionNo, checkedLimit(limit)));
    }

    @Override
    public ObjectNode getProductionBaseline(
            String userId, String episodeId, String baselineId) {
        return read(userId, episodeId, (tx, episode) -> baseline(tx, episodeId, baselineId));
    }

    private ObjectNode draft(DSLContext tx, String episodeId, Map<String, String> mappings) {
        Record row = requireDraft(tx, episodeId);
        return object(
                "episodeId",
                episodeId,
                "revision",
                row.get("revision"),
                "scriptVersionId",
                row.get("scriptVersionId"),
                "baseStoryboardVersionId",
                row.get("basedOnStoryboardVersionId"),
                "document",
                parse(row, "documentJson"),
                "shotIdMappings",
                mappings,
                "updatedAt",
                apiTime(row, "updatedAt"));
    }

    private ObjectNode confirmation(DSLContext tx, String episodeId, String artifactId) {
        Record artifact = requireArtifact(tx, episodeId, artifactId);
        ObjectNode payload = parse(artifact, "payloadJson");
        requireTarget(payload, "video_episode_storyboard_confirmation");
        return object(
                "artifactId",
                artifactId,
                "artifactRevision",
                artifact.get("revision"),
                "episodeId",
                episodeId,
                "episodeRevision",
                payload.path("episodeRevision"),
                "draftRevision",
                payload.path("draftRevision"),
                "scriptVersionId",
                payload.path("scriptVersionId"),
                "baseStoryboardVersionId",
                payload.path("baseStoryboardVersionId"),
                "document",
                payload.path("document"),
                "confirmationHash",
                payload.path("confirmationHash"),
                "createdAt",
                apiTime(artifact, "createdAt"));
    }

    private ObjectNode storyboardVersion(DSLContext tx, String episodeId, String versionId) {
        Record row = requireStoryboardVersion(tx, episodeId, versionId).orElseThrow();
        List<ObjectNode> shots =
                tx.fetch(
                                "SELECT * FROM \"VideoShotVersion\" WHERE"
                                        + " \"storyboardVersionId\"=? AND \"episodeId\"=? ORDER BY ordinal",
                                versionId,
                                episodeId)
                        .stream()
                        .map(this::shotVersion)
                        .toList();
        return object(
                "id",
                row.get("id"),
                "episodeId",
                episodeId,
                "versionNo",
                row.get("versionNo"),
                "basedOnVersionId",
                row.get("basedOnVersionId"),
                "scriptVersionId",
                row.get("scriptVersionId"),
                "document",
                parse(row, "documentJson"),
                "shots",
                shots,
                "contentHash",
                row.get("contentHash"),
                "confirmationArtifactId",
                row.get("reviewArtifactId"),
                "createdAt",
                apiTime(row, "createdAt"));
    }

    private ObjectNode shotVersion(Record row) {
        return object(
                "id",
                row.get("id"),
                "shotId",
                row.get("shotId"),
                "storyboardVersionId",
                row.get("storyboardVersionId"),
                "ordinal",
                row.get("ordinal"),
                "versionNo",
                row.get("versionNo"),
                "scriptSceneId",
                row.get("scriptSceneId"),
                "scriptLineIds",
                json.readTree(row.get("scriptLineIdsJson", String.class)),
                "content",
                parse(row, "contentJson"),
                "contentHash",
                row.get("contentHash"),
                "createdAt",
                apiTime(row, "createdAt"));
    }

    private ObjectNode adoption(DSLContext tx, String episodeId, String adoptionId) {
        Record row =
                tx.fetchOne(
                        "SELECT * FROM \"VideoTakeAdoption\" WHERE id=? AND \"episodeId\"=?",
                        adoptionId,
                        episodeId);
        if (row == null) {
            throw missing("VIDEO_TAKE_ADOPTION_NOT_FOUND", "素材采用记录不存在或不属于本集");
        }
        return object(
                "id",
                row.get("id"),
                "episodeId",
                episodeId,
                "targetShotId",
                row.get("targetShotId"),
                "targetShotVersionId",
                row.get("targetShotVersionId"),
                "sourceTakeId",
                row.get("sourceTakeId"),
                "sourceBaselineId",
                row.get("sourceBaselineId"),
                "comparison",
                parse(row, "comparisonJson"),
                "decisionHash",
                row.get("decisionHash"),
                "createdAt",
                apiTime(row, "createdAt"));
    }

    private ObjectNode takeCandidates(
            DSLContext tx,
            Record episode,
            String targetShotVersionId,
            String beforeTakeId,
            int limit) {
        String episodeId = episode.get("id", String.class);
        String projectId = episode.get("projectId", String.class);
        LocalDateTime beforeCreatedAt = null;
        if (beforeTakeId != null) {
            Record cursor =
                    tx.fetchOne(
                            "SELECT t.\"createdAt\" FROM \"VideoShotTake\" t"
                                    + " JOIN \"VideoAsset\" a ON a.id=t.\"assetId\""
                                    + " AND a.\"projectId\"=t.\"projectId\""
                                    + " WHERE t.id=? AND t.\"videoEpisodeId\"=?"
                                    + " AND t.\"projectId\"=? AND a.modality='video'"
                                    + " AND a.\"mimeType\"='video/mp4'"
                                    + " AND a.\"rightsStatus\"='confirmed' AND a.\"lockedAt\" IS NOT NULL",
                            beforeTakeId,
                            episodeId,
                            projectId);
            if (cursor == null) {
                throw invalid(
                        "VIDEO_TAKE_CURSOR_INVALID",
                        "Take 分页游标不存在或不属于当前分集");
            }
            beforeCreatedAt = cursor.get("createdAt", LocalDateTime.class);
        }

        String select =
                "SELECT t.*,a.\"durationMs\" \"mediaDurationMs\","
                        + "a.\"byteSize\" \"mediaByteSize\",a.\"mimeType\" \"mediaMimeType\","
                        + "adopted.id \"adoptionId\" FROM \"VideoShotTake\" t"
                        + " JOIN \"VideoAsset\" a ON a.id=t.\"assetId\""
                        + " AND a.\"projectId\"=t.\"projectId\""
                        + " JOIN \"VideoProductionBaseline\" b ON b.id=t.\"productionBaselineId\""
                        + " AND b.\"episodeId\"=t.\"videoEpisodeId\""
                        + " AND b.\"projectId\"=t.\"projectId\""
                        + " JOIN \"VideoProductionBaselineShot\" bs"
                        + " ON bs.\"baselineId\"=t.\"productionBaselineId\""
                        + " AND bs.\"episodeId\"=t.\"videoEpisodeId\""
                        + " AND bs.\"shotId\"=t.\"episodeShotId\""
                        + " AND bs.\"shotVersionId\"=t.\"episodeShotVersionId\""
                        + " LEFT JOIN LATERAL (SELECT d.id FROM \"VideoTakeAdoption\" d"
                        + " WHERE d.\"episodeId\"=t.\"videoEpisodeId\""
                        + " AND d.\"projectId\"=t.\"projectId\""
                        + " AND d.\"targetShotVersionId\"=? AND d.\"sourceTakeId\"=t.id"
                        + " ORDER BY d.\"createdAt\" DESC,d.id DESC LIMIT 1) adopted ON TRUE"
                        + " WHERE t.\"videoEpisodeId\"=? AND t.\"projectId\"=?"
                        + " AND t.provider='seedance' AND a.modality='video'"
                        + " AND a.\"mimeType\"='video/mp4' AND a.\"durationMs\">0"
                        + " AND a.\"byteSize\">0 AND a.\"rightsStatus\"='confirmed'"
                        + " AND a.\"lockedAt\" IS NOT NULL";
        List<Record> rows =
                beforeCreatedAt == null
                        ? tx.fetch(
                                select + " ORDER BY t.\"createdAt\" DESC,t.id DESC LIMIT ?",
                                targetShotVersionId,
                                episodeId,
                                projectId,
                                limit + 1)
                        : tx.fetch(
                                select
                                        + " AND (t.\"createdAt\"<? OR"
                                        + " (t.\"createdAt\"=? AND t.id<?))"
                                        + " ORDER BY t.\"createdAt\" DESC,t.id DESC LIMIT ?",
                                targetShotVersionId,
                                episodeId,
                                projectId,
                                beforeCreatedAt,
                                beforeCreatedAt,
                                beforeTakeId,
                                limit + 1);
        boolean hasMore = rows.size() > limit;
        List<Record> visible = hasMore ? rows.subList(0, limit) : rows;
        String next =
                hasMore && !visible.isEmpty()
                        ? visible.get(visible.size() - 1).get("id", String.class)
                        : null;
        return object(
                "episodeId",
                episodeId,
                "targetShotVersionId",
                targetShotVersionId,
                "takes",
                visible.stream().map(this::takeCandidate).toList(),
                "nextBeforeTakeId",
                next);
    }

    private ObjectNode takeCandidate(Record row) {
        String adoptionId = row.get("adoptionId", String.class);
        return object(
                "id",
                row.get("id"),
                "takeNo",
                row.get("takeNo"),
                "sourceBaselineId",
                row.get("productionBaselineId"),
                "sourceShotId",
                row.get("episodeShotId"),
                "sourceShotVersionId",
                row.get("episodeShotVersionId"),
                "promptVersionId",
                row.get("promptVersionId"),
                "assetId",
                row.get("assetId"),
                "lastFrameAssetId",
                row.get("lastFrameAssetId"),
                "provider",
                row.get("provider"),
                "model",
                row.get("model"),
                "inputHash",
                row.get("inputHash"),
                "durationMs",
                row.get("mediaDurationMs"),
                "byteSize",
                row.get("mediaByteSize"),
                "mimeType",
                row.get("mediaMimeType"),
                "width",
                mediaDimension(row, "width"),
                "height",
                mediaDimension(row, "height"),
                "adopted",
                adoptionId != null,
                "adoptionId",
                adoptionId,
                "createdAt",
                apiTime(row, "createdAt"));
    }

    private Integer mediaDimension(Record row, String key) {
        JsonNode metadata = json.readTree(row.get("providerMetadataJson", String.class));
        JsonNode value = metadata.path("media").path(key);
        if (!value.isIntegralNumber()) {
            value = metadata.path(key);
        }
        int dimension = value.asInt(-1);
        return dimension > 0 ? dimension : null;
    }

    private Map<String, Record> baselineAdoptions(
            DSLContext tx, Record episode, List<Record> shots, JsonNode requested) {
        if (!requested.isArray() || requested.size() > shots.size()) {
            throw invalid(
                    "VIDEO_PRODUCTION_BASELINE_ADOPTION_INVALID",
                    "基线素材采用必须是分镜镜头范围内的有序集合");
        }
        Set<String> allowed = new HashSet<>();
        shots.forEach(shot -> allowed.add(shot.get("id", String.class)));
        Map<String, Record> result = new HashMap<>();
        for (JsonNode item : requested) {
            String shotVersionId = requiredText(item, "shotVersionId");
            String adoptionId = requiredText(item, "adoptionId");
            if (!allowed.contains(shotVersionId) || result.containsKey(shotVersionId)) {
                throw invalid(
                        "VIDEO_PRODUCTION_BASELINE_ADOPTION_INVALID",
                        "每个正式镜头版本最多选择一条采用记录");
            }
            Record adoption =
                    tx.fetchOne(
                            "SELECT * FROM \"VideoTakeAdoption\" WHERE id=? AND"
                                    + " \"episodeId\"=? AND \"projectId\"=? AND"
                                    + " \"targetShotVersionId\"=?",
                            adoptionId,
                            episode.get("id"),
                            episode.get("projectId"),
                            shotVersionId);
            if (adoption == null) {
                throw invalid(
                        "VIDEO_PRODUCTION_BASELINE_ADOPTION_INVALID",
                        "采用记录与目标镜头版本或分集不匹配");
            }
            result.put(shotVersionId, adoption);
        }
        return result;
    }

    /**
     * 把作者为本次基线选择的关键帧转换为待写入的不可变版本。
     *
     * <p>关键帧版本和基线镜头存在互相引用，因此这里只校验并预分配身份；调用方先写基线镜头，再在同一事务写版本。
     */
    private Map<String, List<ObjectNode>> baselineKeyframes(
            DSLContext tx,
            Record episode,
            List<Record> shots,
            JsonNode requested,
            String baselineId,
            String baselineRequestId,
            String userId) {
        if (requested.isMissingNode() || requested.isNull()) {
            requested = json.createArrayNode();
        }
        if (!requested.isArray() || requested.size() > shots.size() * 3) {
            throw invalid(
                    "VIDEO_PRODUCTION_KEYFRAME_INVALID",
                    "关键帧选择必须位于正式分镜范围内，且每镜最多三个角色");
        }
        Map<String, Record> allowed = new HashMap<>();
        shots.forEach(shot -> allowed.put(shot.get("id", String.class), shot));
        Set<String> unique = new HashSet<>();
        Map<String, List<ObjectNode>> result = new HashMap<>();
        for (JsonNode item : requested) {
            String shotVersionId = requiredText(item, "shotVersionId");
            String role = requiredText(item, "role");
            String assetId = requiredText(item, "assetId");
            Record shot = allowed.get(shotVersionId);
            if (shot == null
                    || !KEYFRAME_ROLES.contains(role)
                    || !unique.add(shotVersionId + "\0" + role)) {
                throw invalid(
                        "VIDEO_PRODUCTION_KEYFRAME_INVALID",
                        "关键帧目标、角色或唯一性无效");
            }
            Record asset =
                    tx.fetchOne(
                            "SELECT * FROM \"VideoAsset\" WHERE id=? AND \"projectId\"=?"
                                    + " AND modality='image' AND \"rightsStatus\"='confirmed'"
                                    + " AND \"lockedAt\" IS NOT NULL",
                            assetId,
                            episode.get("projectId"));
            String mimeType = asset == null ? null : asset.get("mimeType", String.class);
            String duty = asset == null ? null : asset.get("duty", String.class);
            if (asset == null
                    || !IMAGE_MIME_TYPES.contains(mimeType)
                    || !KEYFRAME_DUTIES.contains(duty)) {
                throw invalid(
                        "VIDEO_PRODUCTION_KEYFRAME_ASSET_INVALID",
                        "关键帧必须使用本项目已确认并锁定的图片素材");
            }
            int versionNo =
                    tx.fetchOne(
                                    "SELECT COALESCE(MAX(\"versionNo\"),0)+1 n FROM"
                                            + " \"VideoShotKeyframeVersion\" WHERE"
                                            + " \"episodeShotId\"=? AND role=?",
                                    shot.get("shotId"),
                                    role)
                            .get("n", Integer.class);
            String versionId = ids.next();
            ObjectNode content =
                    object(
                            "schemaVersion",
                            "video-episode-keyframe/1.0",
                            "episodeId",
                            episode.get("id"),
                            "productionBaselineId",
                            baselineId,
                            "shotId",
                            shot.get("shotId"),
                            "shotVersionId",
                            shotVersionId,
                            "role",
                            role,
                            "assetId",
                            assetId,
                            "sha256",
                            asset.get("sha256"),
                            "mimeType",
                            mimeType,
                            "duty",
                            duty,
                            "rightsStatus",
                            asset.get("rightsStatus"),
                            "lockedAt",
                            apiTime(asset, "lockedAt"));
            String contentHash = hash(content);
            ObjectNode row =
                    object(
                            "keyframeVersionId",
                            versionId,
                            "versionNo",
                            versionNo,
                            "role",
                            role,
                            "assetId",
                            assetId,
                            "sha256",
                            asset.get("sha256"),
                            "mimeType",
                            mimeType,
                            "duty",
                            duty,
                            "rightsStatus",
                            asset.get("rightsStatus"),
                            "lockedAt",
                            apiTime(asset, "lockedAt"),
                            "contentHash",
                            contentHash,
                            "clientRequestId",
                            baselineRequestId + ":keyframe:" + shotVersionId + ":" + role,
                            "requestHash",
                            hash(item));
            result.computeIfAbsent(shotVersionId, ignored -> new ArrayList<>()).add(row);
        }
        for (List<ObjectNode> values : result.values()) {
            values.sort(
                    java.util.Comparator.comparingInt(
                            value -> keyframeRoleOrder(text(value, "role"))));
            for (int index = 0; index < values.size(); index++) {
                values.get(index).put("ordinal", index + 1);
            }
        }
        return result;
    }

    private ObjectNode keyframeSnapshot(ObjectNode row) {
        return object(
                "ordinal",
                row.path("ordinal"),
                "keyframeVersionId",
                row.path("keyframeVersionId"),
                "role",
                row.path("role"),
                "assetId",
                row.path("assetId"),
                "sha256",
                row.path("sha256"),
                "mimeType",
                row.path("mimeType"),
                "duty",
                row.path("duty"),
                "rightsStatus",
                row.path("rightsStatus"),
                "lockedAt",
                row.path("lockedAt"),
                "contentHash",
                row.path("contentHash"));
    }

    private static int keyframeRoleOrder(String role) {
        return switch (role) {
            case "initial_state" -> 0;
            case "transition_anchor" -> 1;
            case "end_state" -> 2;
            default -> throw new IllegalArgumentException("未知关键帧角色");
        };
    }

    /** 供应商只接收有序 reference_image，因此把每张冻结图片的用途写进同一版提示词。 */
    private static String providerPrompt(
            String prompt, int referenceCount, List<ObjectNode> keyframes) {
        int next = 1;
        List<String> rules = new ArrayList<>();
        if (keyframes.stream()
                .anyMatch(value -> "initial_state".equals(text(value, "role")))) {
            rules.add("第" + next + "张固定镜头起始状态");
            next++;
        }
        if (referenceCount > 0) {
            int end = next + referenceCount - 1;
            rules.add(
                    next == end
                            ? "第" + next + "张仅用于角色、服装、场景和道具一致性"
                            : "第"
                                    + next
                                    + "至第"
                                    + end
                                    + "张仅用于角色、服装、场景和道具一致性");
            next = end + 1;
        }
        if (keyframes.stream()
                .anyMatch(value -> "transition_anchor".equals(text(value, "role")))) {
            rules.add("第" + next + "张固定动作转折状态");
            next++;
        }
        if (keyframes.stream().anyMatch(value -> "end_state".equals(text(value, "role")))) {
            rules.add("第" + next + "张固定镜头结束状态");
        }
        String compiled = "参考图使用规则：" + String.join("；", rules) + "。用途不可互换。\n" + prompt;
        if (compiled.codePointCount(0, compiled.length()) > 2_500) {
            throw invalid(
                    "VIDEO_PRODUCTION_PROMPT_TOO_LONG",
                    "加入冻结参考图用途后的供应商提示词超过 2500 字符，请精简镜头提示词");
        }
        return compiled;
    }

    private ObjectNode pagedStoryboardVersions(
            DSLContext tx, String episodeId, Integer beforeVersionNo, int limit) {
        String cursor = beforeVersionNo == null ? "" : " AND \"versionNo\" < ?";
        List<Record> rows =
                beforeVersionNo == null
                        ? tx.fetch(
                                "SELECT v.*,(SELECT count(*) FROM \"VideoShotVersion\" s WHERE"
                                        + " s.\"storyboardVersionId\"=v.id) \"shotCount\" FROM"
                                        + " \"VideoStoryboardVersion\" v WHERE v.\"episodeId\"=? ORDER BY"
                                        + " v.\"versionNo\" DESC LIMIT ?",
                                episodeId,
                                limit + 1)
                        : tx.fetch(
                                "SELECT v.*,(SELECT count(*) FROM \"VideoShotVersion\" s WHERE"
                                        + " s.\"storyboardVersionId\"=v.id) \"shotCount\" FROM"
                                        + " \"VideoStoryboardVersion\" v WHERE v.\"episodeId\"=?"
                                        + cursor
                                        + " ORDER BY v.\"versionNo\" DESC LIMIT ?",
                                episodeId,
                                beforeVersionNo,
                                limit + 1);
        return page(
                "versions",
                rows,
                limit,
                row ->
                        object(
                                "id",
                                row.get("id"),
                                "episodeId",
                                episodeId,
                                "versionNo",
                                row.get("versionNo"),
                                "basedOnVersionId",
                                row.get("basedOnVersionId"),
                                "scriptVersionId",
                                row.get("scriptVersionId"),
                                "shotCount",
                                row.get("shotCount"),
                                "contentHash",
                                row.get("contentHash"),
                                "createdAt",
                                apiTime(row, "createdAt")));
    }

    private ObjectNode baseline(DSLContext tx, String episodeId, String baselineId) {
        Record row = requireBaseline(tx, episodeId, baselineId);
        List<ObjectNode> shots =
                tx.fetch(
                                "SELECT * FROM \"VideoProductionBaselineShot\" WHERE"
                                        + " \"baselineId\"=? AND \"episodeId\"=? ORDER BY ordinal",
                                baselineId,
                                episodeId)
                        .stream()
                        .map(
                                shot ->
                                        object(
                                                "ordinal",
                                                shot.get("ordinal"),
                                                "shotId",
                                                shot.get("shotId"),
                                                "shotVersionId",
                                                shot.get("shotVersionId"),
                                                "adoptionId",
                                                shot.get("adoptionId"),
                                                "status",
                                                shot.get("status"),
                                                "inputSnapshot",
                                                parse(shot, "inputSnapshotJson"),
                                                "inputHash",
                                                shot.get("inputHash")))
                        .toList();
        Record episode = requireEpisode(tx, episodeId, false);
        return object(
                "id",
                row.get("id"),
                "episodeId",
                episodeId,
                "versionNo",
                row.get("versionNo"),
                "basedOnBaselineId",
                row.get("basedOnBaselineId"),
                "scriptVersionId",
                row.get("scriptVersionId"),
                "storyboardVersionId",
                row.get("storyboardVersionId"),
                "manifest",
                parse(row, "manifestJson"),
                "shots",
                shots,
                "contentHash",
                row.get("contentHash"),
                "productionRevision",
                episode.get("productionRevision"),
                "createdAt",
                apiTime(row, "createdAt"));
    }

    private ObjectNode pagedBaselines(
            DSLContext tx, String episodeId, Integer beforeVersionNo, int limit) {
        List<Record> rows =
                beforeVersionNo == null
                        ? tx.fetch(
                                "SELECT b.*,(SELECT count(*) FROM"
                                        + " \"VideoProductionBaselineShot\" s WHERE s.\"baselineId\"=b.id)"
                                        + " \"shotCount\" FROM \"VideoProductionBaseline\" b WHERE"
                                        + " b.\"episodeId\"=? ORDER BY b.\"versionNo\" DESC LIMIT ?",
                                episodeId,
                                limit + 1)
                        : tx.fetch(
                                "SELECT b.*,(SELECT count(*) FROM"
                                        + " \"VideoProductionBaselineShot\" s WHERE s.\"baselineId\"=b.id)"
                                        + " \"shotCount\" FROM \"VideoProductionBaseline\" b WHERE"
                                        + " b.\"episodeId\"=? AND b.\"versionNo\" < ? ORDER BY"
                                        + " b.\"versionNo\" DESC LIMIT ?",
                                episodeId,
                                beforeVersionNo,
                                limit + 1);
        return page(
                "baselines",
                rows,
                limit,
                row ->
                        object(
                                "id",
                                row.get("id"),
                                "episodeId",
                                episodeId,
                                "versionNo",
                                row.get("versionNo"),
                                "basedOnBaselineId",
                                row.get("basedOnBaselineId"),
                                "scriptVersionId",
                                row.get("scriptVersionId"),
                                "storyboardVersionId",
                                row.get("storyboardVersionId"),
                                "shotCount",
                                row.get("shotCount"),
                                "contentHash",
                                row.get("contentHash"),
                                "createdAt",
                                apiTime(row, "createdAt")));
    }

    private ObjectNode page(
            String key,
            List<Record> rows,
            int limit,
            java.util.function.Function<Record, ObjectNode> mapper) {
        boolean hasMore = rows.size() > limit;
        List<Record> visible = hasMore ? rows.subList(0, limit) : rows;
        Integer next =
                hasMore && !visible.isEmpty()
                        ? visible.get(visible.size() - 1).get("versionNo", Integer.class)
                        : null;
        return object(key, visible.stream().map(mapper).toList(), "nextBeforeVersionNo", next);
    }

    private ObjectNode normalizeDocument(
            DSLContext tx,
            Record episode,
            Record script,
            JsonNode input,
            JsonNode current,
            JsonNode basedOn,
            String userId,
            Map<String, String> mappings) {
        if (!input.isObject()
                || !"video-episode-storyboard/1.0"
                        .equals(input.path("schemaVersion").asText())) {
            throw invalid("VIDEO_STORYBOARD_DOCUMENT_INVALID", "分镜文档版本无效");
        }
        if (!input.path("shots").isArray() || input.path("shots").size() > 300) {
            throw invalid("VIDEO_STORYBOARD_DOCUMENT_INVALID", "分镜必须是最多 300 项的数组");
        }
        ObjectNode document = (ObjectNode) input.deepCopy();
        Map<String, Set<String>> scriptNodes = scriptNodes(parse(script, "documentJson"));
        Set<String> permitted = new HashSet<>();
        collectShotIds(current, permitted);
        collectShotIds(basedOn, permitted);
        Set<String> usedIds = new HashSet<>();
        Set<String> usedKeys = new HashSet<>();
        Set<String> replacementTargets = new HashSet<>();

        for (JsonNode raw : document.path("shots")) {
            if (!raw.isObject()) {
                throw invalid("VIDEO_STORYBOARD_SHOT_INVALID", "镜头必须是结构化对象");
            }
            ObjectNode shot = (ObjectNode) raw;
            String id = text(shot, "id");
            String tempKey = text(shot, "tempKey");
            if ((id == null) == (tempKey == null)) {
                throw invalid(
                        "VIDEO_STORYBOARD_SHOT_ID_INVALID", "镜头必须提供已有 id 或新建 tempKey");
            }
            if (id != null) {
                if (!permitted.contains(id)) {
                    throw invalid(
                            "VIDEO_STORYBOARD_SHOT_ID_INVALID",
                            "不能伪造其他分集或已删除镜头的身份");
                }
                requireShot(tx, episode, id);
                JsonNode recordedLineage = lineage(tx, id);
                if (shot.has("lineage") && !recordedLineage.equals(shot.path("lineage"))) {
                    throw invalid("VIDEO_STORYBOARD_LINEAGE_INVALID", "镜头沿袭关系不可修改");
                }
                shot.set("lineage", recordedLineage);
            } else {
                if (!usedKeys.add(tempKey)) {
                    throw invalid("VIDEO_STORYBOARD_SHOT_ID_DUPLICATE", "镜头临时身份不能重复");
                }
                List<LineageInput> lineage = validateLineage(shot.path("lineage"), permitted);
                id = ids.next();
                tx.execute(
                        "INSERT INTO \"VideoEpisodeShot\""
                                + " (id,\"episodeId\",\"projectId\",\"createdByUserId\",\"createdAt\")"
                                + " VALUES (?,?,?,?,?)",
                        id,
                        episode.get("id"),
                        episode.get("projectId"),
                        userId,
                        now());
                int lineageOrdinal = 0;
                for (LineageInput source : lineage) {
                    lineageOrdinal++;
                    tx.execute(
                            "INSERT INTO \"VideoShotLineage\""
                                    + " (\"childShotId\",\"sourceShotId\",\"episodeId\",ordinal,relation)"
                                    + " VALUES (?,?,?,?,?)",
                            id,
                            source.sourceShotId(),
                            episode.get("id"),
                            lineageOrdinal,
                            source.relation());
                    if ("replacement".equals(source.relation())) {
                        if (!replacementTargets.add(source.sourceShotId())) {
                            throw invalid(
                                    "VIDEO_STORYBOARD_LINEAGE_INVALID",
                                    "同一工作稿中的原镜头只能被替换一次");
                        }
                    }
                }
                mappings.put(tempKey, id);
                shot.put("id", id);
                shot.putNull("tempKey");
            }
            if (!usedIds.add(id)) {
                throw invalid("VIDEO_STORYBOARD_SHOT_ID_DUPLICATE", "同一分镜不能重复使用镜头身份");
            }
            validateShotContent(tx, episode, shot, scriptNodes);
        }
        for (String replaced : replacementTargets) {
            if (usedIds.contains(replaced)) {
                throw invalid(
                        "VIDEO_STORYBOARD_LINEAGE_INVALID", "替换镜头与原镜头不能同时留在同一工作稿");
            }
        }
        return document;
    }

    private void validateShotContent(
            DSLContext tx,
            Record episode,
            ObjectNode shot,
            Map<String, Set<String>> scriptNodes) {
        String sceneId = requiredText(shot, "scriptSceneId");
        Set<String> allowedLines = scriptNodes.get(sceneId);
        if (allowedLines == null) {
            throw invalid("VIDEO_STORYBOARD_SCRIPT_TARGET_INVALID", "镜头场次不属于所选正式剧本");
        }
        JsonNode lineIds = shot.path("scriptLineIds");
        if (!lineIds.isArray() || lineIds.size() > 100) {
            throw invalid("VIDEO_STORYBOARD_SCRIPT_TARGET_INVALID", "镜头台词范围无效");
        }
        Set<String> seenLines = new HashSet<>();
        for (JsonNode line : lineIds) {
            String id = line.asText();
            if (!allowedLines.contains(id) || !seenLines.add(id)) {
                throw invalid(
                        "VIDEO_STORYBOARD_SCRIPT_TARGET_INVALID",
                        "镜头台词必须唯一且属于指定场次");
            }
        }
        requiredText(shot, "title");
        requiredText(shot, "action");
        if (!FRAMINGS.contains(shot.path("framing").asText())) {
            throw invalid("VIDEO_STORYBOARD_FRAMING_INVALID", "镜头景别无效");
        }
        if (!CAMERA_MOVEMENTS.contains(shot.path("cameraMovement").asText())) {
            throw invalid("VIDEO_STORYBOARD_CAMERA_INVALID", "镜头运动无效");
        }
        int durationMs = shot.path("durationMs").asInt(-1);
        JsonNode intent = shot.path("productionIntent");
        if (!intent.isObject()) {
            throw invalid("VIDEO_STORYBOARD_INTENT_INVALID", "镜头制作意图必须是结构化对象");
        }
        validateProductionIntent(tx, episode, (ObjectNode) intent);
        if (durationMs < 4_000
                || durationMs > 12_000
                || durationMs != intent.path("durationSeconds").asInt() * 1_000) {
            throw invalid(
                    "VIDEO_STORYBOARD_DURATION_INVALID",
                    "首批单镜时长须为 4000 至 12000 毫秒并与生成秒数一致");
        }
    }

    private void validateProductionIntent(DSLContext tx, Record episode, ObjectNode intent) {
        if (!"seedance".equals(intent.path("provider").asText())
                || !seedanceModel.equals(requiredText(intent, "model"))
                || !"reference".equals(intent.path("generationMode").asText())) {
            throw invalid(
                    "VIDEO_STORYBOARD_INTENT_INVALID",
                    "首批制作意图必须明确使用 Seedance 参考图模式及模型");
        }
        String executionMode = intent.path("executionMode").asText();
        if (!this.executionMode.equals(executionMode)
                || !intent.path("feeConfirmed").isBoolean()
                || ("live".equals(executionMode) && !intent.path("feeConfirmed").asBoolean())
                || ("simulated".equals(executionMode)
                        && intent.path("feeConfirmed").asBoolean())) {
            throw invalid(
                    "VIDEO_STORYBOARD_FEE_CONFIRMATION_INVALID",
                    "模拟模式不得确认费用，live 模式必须明确确认供应商费用");
        }
        if ("live".equals(executionMode) && (!seedanceConfigured || !seedanceEnabled)) {
            throw new ApiException(
                    503,
                    "VIDEO_SEEDANCE_NOT_READY",
                    "真实 Seedance 尚未完成配置并显式启用");
        }
        String prompt = requiredText(intent, "prompt");
        if (prompt.length() > 2_500) {
            throw invalid("VIDEO_STORYBOARD_PROMPT_INVALID", "供应商提示词不能超过 2500 个字符");
        }
        if (!Set.of("16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive")
                        .contains(intent.path("ratio").asText())
                || intent.path("durationSeconds").asInt(-1) < 4
                || intent.path("durationSeconds").asInt(-1) > 12
                || !"720p".equals(intent.path("resolution").asText())
                || !intent.path("generateAudio").isBoolean()
                || !intent.path("watermark").isBoolean()
                || !"mp4".equals(intent.path("outputFormat").asText())) {
            throw invalid(
                    "VIDEO_STORYBOARD_OUTPUT_INVALID",
                    "首批只支持显式画幅、4 至 12 秒、720p、MP4 及布尔音频/水印选项");
        }
        freezeReferences(tx, episode, intent);
    }

    /** 创建分镜稿和制作基线时都从当前数据库重取权利与锁定事实，不能照抄调用方或旧稿中的声明。 */
    private void freezeReferences(DSLContext tx, Record episode, ObjectNode intent) {
        JsonNode references = intent.path("references");
        if (!references.isArray() || references.isEmpty() || references.size() > 20) {
            throw invalid(
                    "VIDEO_STORYBOARD_REFERENCE_INVALID", "参考图模式须冻结 1 至 20 份有序图片参考");
        }
        ArrayNode normalized = json.createArrayNode();
        Set<String> versions = new HashSet<>();
        int ordinal = 0;
        for (JsonNode reference : references) {
            ordinal++;
            String canonVersionId = requiredText(reference, "canonVersionId");
            if (!versions.add(canonVersionId)) {
                throw invalid("VIDEO_STORYBOARD_REFERENCE_INVALID", "同一视觉版本不能重复引用");
            }
            Record row =
                    tx.fetchOne(
                            "SELECT v.id,v.\"assetId\",v.\"contentHash\",v.\"defaultStrength\","
                                    + " a.sha256,a.\"mimeType\",a.duty,a.\"rightsStatus\",a.\"lockedAt\""
                                    + " FROM \"VideoVisualCanonVersion\" v JOIN \"VideoAsset\" a ON"
                                    + " a.id=v.\"assetId\" AND a.\"projectId\"=v.\"projectId\" WHERE"
                                    + " v.id=? AND v.\"projectId\"=?",
                            canonVersionId,
                            episode.get("projectId"));
            if (row == null
                    || !"confirmed".equals(row.get("rightsStatus", String.class))
                    || row.get("lockedAt") == null
                    || !Set.of("image/jpeg", "image/png", "image/webp")
                            .contains(row.get("mimeType", String.class))) {
                throw invalid(
                        "VIDEO_STORYBOARD_REFERENCE_INVALID",
                        "参考版本必须属于本项目并使用已锁定、权利核验的 JPEG、PNG 或 WebP 素材");
            }
            int strength =
                    reference.hasNonNull("strength")
                            ? reference.path("strength").asInt(-1)
                            : row.get("defaultStrength", Integer.class);
            if (strength < 1 || strength > 100) {
                throw invalid("VIDEO_STORYBOARD_REFERENCE_INVALID", "参考强度须为 1 至 100");
            }
            normalized.add(
                    object(
                            "ordinal",
                            ordinal,
                            "canonVersionId",
                            canonVersionId,
                            "canonContentHash",
                            row.get("contentHash"),
                            "assetId",
                            row.get("assetId"),
                            "sha256",
                            row.get("sha256"),
                            "mimeType",
                            row.get("mimeType"),
                            "duty",
                            row.get("duty"),
                            "rightsStatus",
                            row.get("rightsStatus"),
                            "lockedAt",
                            apiTime(row, "lockedAt"),
                            "strength",
                            strength));
        }
        intent.set("references", normalized);
    }

    private List<LineageInput> validateLineage(JsonNode node, Set<String> permitted) {
        if (!node.isArray() || node.size() > 20) {
            throw invalid("VIDEO_STORYBOARD_LINEAGE_INVALID", "镜头沿袭关系必须是最多 20 项的数组");
        }
        List<LineageInput> result = new ArrayList<>();
        Set<String> sources = new HashSet<>();
        Set<String> relations = new HashSet<>();
        for (JsonNode item : node) {
            String source = requiredText(item, "sourceShotId");
            String relation = requiredText(item, "relation");
            if (!Set.of("replacement", "copy", "split", "merge").contains(relation)
                    || !permitted.contains(source)
                    || !sources.add(source)) {
                throw invalid(
                        "VIDEO_STORYBOARD_LINEAGE_INVALID",
                        "沿袭来源必须唯一、属于当前稿或基础版本且关系类型有效");
            }
            relations.add(relation);
            result.add(new LineageInput(source, relation));
        }
        if (relations.size() > 1
                || (relations.contains("merge") && result.size() < 2)
                || (!relations.contains("merge") && result.size() > 1)) {
            throw invalid(
                    "VIDEO_STORYBOARD_LINEAGE_INVALID",
                    "替换、复制、拆分各有一个来源；合并必须有至少两个有序来源");
        }
        return result;
    }

    private ArrayNode lineage(DSLContext tx, String shotId) {
        ArrayNode result = json.createArrayNode();
        tx.fetch(
                        "SELECT \"sourceShotId\",relation FROM \"VideoShotLineage\" WHERE"
                                + " \"childShotId\"=? ORDER BY ordinal",
                        shotId)
                .forEach(
                        row ->
                                result.add(
                                        object(
                                                "sourceShotId",
                                                row.get("sourceShotId"),
                                                "relation",
                                                row.get("relation"))));
        return result;
    }

    private Map<String, Set<String>> scriptNodes(JsonNode document) {
        Map<String, Set<String>> result = new HashMap<>();
        for (JsonNode scene : document.path("scenes")) {
            String sceneId = requiredText(scene, "id");
            Set<String> lines = new HashSet<>();
            for (JsonNode line : scene.path("lines")) {
                lines.add(requiredText(line, "id"));
            }
            result.put(sceneId, lines);
        }
        return result;
    }

    private void collectShotIds(JsonNode document, Set<String> target) {
        if (document == null || !document.isObject()) {
            return;
        }
        for (JsonNode shot : document.path("shots")) {
            String id = text(shot, "id");
            if (id != null) {
                target.add(id);
            }
        }
    }

    private void requireConfirmable(JsonNode document) {
        if (document.path("shots").isEmpty()) {
            throw invalid("VIDEO_STORYBOARD_EMPTY", "空分镜不能确认为正式版本");
        }
    }

    private Record requireShot(DSLContext tx, Record episode, String shotId) {
        Record row =
                tx.fetchOne(
                        "SELECT * FROM \"VideoEpisodeShot\" WHERE id=? AND \"episodeId\"=?"
                                + " AND \"projectId\"=?",
                        shotId,
                        episode.get("id"),
                        episode.get("projectId"));
        if (row == null) {
            throw invalid("VIDEO_STORYBOARD_SHOT_ID_INVALID", "镜头身份不属于当前分集");
        }
        return row;
    }

    private Record requireScriptVersion(DSLContext tx, String episodeId, String versionId) {
        Record row =
                tx.fetchOne(
                        "SELECT * FROM \"VideoEpisodeScriptVersion\" WHERE id=? AND"
                                + " \"episodeId\"=?",
                        versionId,
                        episodeId);
        if (row == null) {
            throw missing("VIDEO_SCRIPT_VERSION_NOT_FOUND", "正式剧本版本不存在或不属于本集");
        }
        return row;
    }

    private java.util.Optional<Record> requireStoryboardVersion(
            DSLContext tx, String episodeId, String versionId) {
        Record row =
                tx.fetchOne(
                        "SELECT * FROM \"VideoStoryboardVersion\" WHERE id=? AND \"episodeId\"=?",
                        versionId,
                        episodeId);
        if (row == null) {
            throw missing("VIDEO_STORYBOARD_VERSION_NOT_FOUND", "正式分镜版本不存在或不属于本集");
        }
        return java.util.Optional.of(row);
    }

    private Record requireBaseline(DSLContext tx, String episodeId, String baselineId) {
        Record row =
                tx.fetchOne(
                        "SELECT * FROM \"VideoProductionBaseline\" WHERE id=? AND"
                                + " \"episodeId\"=?",
                        baselineId,
                        episodeId);
        if (row == null) {
            throw missing("VIDEO_PRODUCTION_BASELINE_NOT_FOUND", "制作基线不存在或不属于本集");
        }
        return row;
    }

    private Record requireArtifact(DSLContext tx, String episodeId, String artifactId) {
        Record row =
                tx.fetchOne(
                        "SELECT * FROM \"ReviewArtifact\" WHERE id=? AND \"videoEpisodeId\"=?"
                                + " AND kind='video_episode_storyboard'",
                        artifactId,
                        episodeId);
        if (row == null) {
            throw missing("VIDEO_STORYBOARD_ARTIFACT_NOT_FOUND", "分镜审核记录不存在");
        }
        return row;
    }

    private String insertArtifact(DSLContext tx, Record episode, JsonNode payload) {
        String id = ids.next();
        tx.execute(
                "INSERT INTO \"ReviewArtifact\""
                        + " (id,\"novelId\",\"videoEpisodeId\",\"artifactKey\",kind,status,title,\"payloadJson\",revision,\"createdAt\",\"updatedAt\")"
                        + " VALUES (?,?,?,?,'video_episode_storyboard','awaiting_user','作者确认分镜',?,1,?,?)",
                id,
                episode.get("novelId"),
                episode.get("id"),
                "video-storyboard:" + episode.get("id"),
                payload.toString(),
                now(),
                now());
        tx.execute(
                "INSERT INTO \"ReviewArtifactRevision\""
                        + " (id,\"artifactId\",revision,\"payloadJson\",\"createdAt\") VALUES"
                        + " (?,?,1,?,?)",
                ids.next(),
                id,
                payload.toString(),
                now());
        return id;
    }

    private void applyArtifact(DSLContext tx, String artifactId) {
        tx.execute(
                "UPDATE \"ReviewArtifact\" SET status='applied',\"appliedAt\"=?,\"updatedAt\"=?"
                        + " WHERE id=?",
                now(),
                now(),
                artifactId);
    }

    private ObjectNode write(
            String userId,
            String episodeId,
            String operation,
            JsonNode request,
            Work work) {
        String clientRequestId = requiredText(request, "clientRequestId");
        String requestHash =
                hash(
                        object(
                                "operation",
                                operation,
                                "episodeId",
                                episodeId,
                                "request",
                                request));
        return database.transactionResult(
                tx -> {
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
                        if (!requestHash.equals(previous.get("requestHash"))) {
                            throw conflict(
                                    "VIDEO_EPISODE_CLIENT_REQUEST_REUSED",
                                    "clientRequestId 已用于不同请求");
                        }
                        return parse(previous, "resultJson");
                    }
                    ObjectNode result = work.run(tx, episode);
                    tx.execute(
                            "INSERT INTO \"VideoEpisodeCommand\""
                                    + " (id,\"actorUserId\",\"clientRequestId\",\"projectId\",\"novelId\",\"episodeId\",operation,\"requestHash\",\"resultJson\",\"createdAt\")"
                                    + " VALUES (?,?,?,?,?,?,?,?,?,?)",
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
        return database.transactionResult(
                tx -> work.run(tx, owned(tx, userId, episodeId, false)));
    }

    private Record owned(DSLContext tx, String userId, String episodeId, boolean lock) {
        Record scope =
                tx.fetchOne(
                        "SELECT \"projectId\" FROM \"VideoEpisode\" WHERE id=? AND"
                                + " \"archivedAt\" IS NULL",
                        episodeId);
        if (scope == null) {
            throw missing("VIDEO_EPISODE_NOT_FOUND", "分集不存在");
        }
        VideoDatabaseAccess.ownedProject(
                tx, userId, scope.get("projectId", String.class), lock);
        return requireEpisode(tx, episodeId, lock);
    }

    private Record requireEpisode(DSLContext tx, String episodeId, boolean lock) {
        Record row =
                tx.fetchOne(
                        "SELECT * FROM \"VideoEpisode\" WHERE id=? AND \"archivedAt\" IS NULL"
                                + (lock ? " FOR UPDATE" : ""),
                        episodeId);
        if (row == null) {
            throw missing("VIDEO_EPISODE_NOT_FOUND", "分集不存在");
        }
        return row;
    }

    private Record requireDraft(DSLContext tx, String episodeId) {
        Record row =
                tx.fetchOne(
                        "SELECT * FROM \"VideoStoryboardDraft\" WHERE \"episodeId\"=?",
                        episodeId);
        if (row == null) {
            throw conflict("VIDEO_STORYBOARD_DRAFT_MISSING", "分集缺少分镜工作稿");
        }
        return row;
    }

    private int nextVersion(DSLContext tx, String table, String episodeId) {
        return tx.fetchOne(
                        "SELECT COALESCE(MAX(\"versionNo\"),0)+1 n FROM \""
                                + table
                                + "\" WHERE \"episodeId\"=?",
                        episodeId)
                .get("n", Integer.class);
    }

    private int checkedLimit(int limit) {
        if (limit < 1 || limit > 100) {
            throw invalid("VIDEO_PAGE_LIMIT_INVALID", "分页数量须为 1 至 100");
        }
        return limit;
    }

    private void requireTarget(JsonNode payload, String target) {
        if (!target.equals(payload.path("applyTarget").asText())) {
            throw invalid("VIDEO_STORYBOARD_ARTIFACT_TARGET_INVALID", "审核记录不属于此操作");
        }
    }

    private void requireRevision(Record row, int expected, String code) {
        if (row.get("revision", Integer.class) != expected) {
            throw conflict(code, "版本已变化，请保留输入并重新读取");
        }
    }

    private ObjectNode parse(Record row, String column) {
        return (ObjectNode) json.readTree(row.get(column, String.class));
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
        return value.strip();
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

    private record LineageInput(String sourceShotId, String relation) {}
}
