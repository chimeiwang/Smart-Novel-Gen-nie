package cn.inkforge.core.video.infrastructure;

import static cn.inkforge.core.db.generated.Tables.VIDEOASSET;
import static cn.inkforge.core.db.generated.Tables.VIDEOEPISODEEDITVERSION;
import static cn.inkforge.core.db.generated.Tables.VIDEOEPISODEEXPORTTASK;
import static cn.inkforge.core.db.generated.Tables.VIDEOEPISODEMIXVERSION;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTKEYFRAMEHEAD;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTKEYFRAMEVERSION;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTPROMPTHEAD;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTPROMPTVISUALREFERENCE;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTTAKE;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTTAKEHEAD;
import static cn.inkforge.core.db.generated.Tables.VIDEOVISUALCANON;
import static cn.inkforge.core.db.generated.Tables.VIDEOVISUALCANONVERSION;

import cn.inkforge.contracts.api.ChapterPostProductionWorkspaceResponse;
import cn.inkforge.contracts.api.ContinuityIssueResponse;
import cn.inkforge.contracts.api.EpisodeEditClipResponse;
import cn.inkforge.contracts.api.EpisodeEditHeadResponse;
import cn.inkforge.contracts.api.EpisodeEditVersionSummaryResponse;
import cn.inkforge.contracts.api.EpisodeMixHeadResponse;
import cn.inkforge.contracts.api.EpisodeMixVersionSummaryResponse;
import cn.inkforge.contracts.api.EpisodePostProductionResponse;
import cn.inkforge.contracts.api.EpisodeShotResponse;
import cn.inkforge.contracts.api.EpisodeSubtitleCueInput;
import cn.inkforge.contracts.api.PostProductionAssetResponse;
import cn.inkforge.contracts.api.PostProductionReadinessResponse;
import cn.inkforge.contracts.api.PostProductionTakeResponse;
import cn.inkforge.contracts.api.ShotKeyframeHeadResponse;
import cn.inkforge.contracts.api.ShotKeyframeVersionResponse;
import cn.inkforge.contracts.api.ShotPostProductionResponse;
import cn.inkforge.core.db.generated.tables.records.VideoassetRecord;
import cn.inkforge.core.db.generated.tables.records.VideoepisodeeditversionRecord;
import cn.inkforge.core.db.generated.tables.records.VideoepisodeexporttaskRecord;
import cn.inkforge.core.db.generated.tables.records.VideoepisodemixversionRecord;
import cn.inkforge.core.db.generated.tables.records.VideoshotRecord;
import cn.inkforge.core.db.generated.tables.records.VideoshotkeyframeheadRecord;
import cn.inkforge.core.db.generated.tables.records.VideoshotkeyframeversionRecord;
import cn.inkforge.core.db.generated.tables.records.VideoshottakeRecord;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.jooq.DSLContext;
import org.jooq.Record;

/**
 * P1–P3 工作台的关系型读模型。
 *
 * <p>这里把当前 Head、不可变历史、素材权利、连续性提示和 worker 就绪状态投影成一个只读工作区，避免浏览器
 * 自行拼接关系或把最新版本误当当前版本。连续性项分级展示，其中 warning/info 是创作建议，不是硬门禁。
 */
final class JooqVideoPostProductionReadModel {

    private static final List<String> KEYFRAME_ROLES =
            List.of("initial_state", "transition_anchor", "end_state");

    private final CoreDatabase database;
    private final JooqVideoTimelineRepository timelines;
    private final JooqVideoExportRepository exports;

    JooqVideoPostProductionReadModel(
            CoreDatabase database,
            JooqVideoTimelineRepository timelines,
            JooqVideoExportRepository exports) {
        this.database = Objects.requireNonNull(database);
        this.timelines = Objects.requireNonNull(timelines);
        this.exports = Objects.requireNonNull(exports);
    }

    ChapterPostProductionWorkspaceResponse getWorkspace(
            String userId,
            String adaptationId,
            PostProductionReadinessResponse readiness) {
        DSLContext context = database.dsl();
        VideoPostProductionContext production =
                VideoPostProductionDatabaseAccess.context(
                        context, userId, adaptationId, false);
        List<VideoassetRecord> assets = context.selectFrom(VIDEOASSET)
                .where(
                        VIDEOASSET.PROJECTID.eq(production.project().getId()),
                        VIDEOASSET.RIGHTSSTATUS.eq("confirmed"),
                        VIDEOASSET.LOCKEDAT.isNotNull())
                .orderBy(VIDEOASSET.CREATEDAT, VIDEOASSET.ID)
                .fetch();
        List<PostProductionAssetResponse> keyframeAssets = assets.stream()
                .filter(asset -> "image".equals(asset.getModality())
                        && Set.of("keyframe", "storyboard").contains(asset.getDuty()))
                .map(JooqVideoPostProductionRepository::assetResponse)
                .toList();
        List<PostProductionAssetResponse> audioAssets = assets.stream()
                .filter(asset -> "audio".equals(asset.getModality())
                        && Set.of("voice", "ambience", "sfx", "music")
                                .contains(asset.getDuty()))
                .map(JooqVideoPostProductionRepository::assetResponse)
                .toList();
        // 连续性必须基于当前 Head 与冻结 Prompt 引用计算，不能拿“每条链最新 versionNo”代替当前选择。
        List<ShotPostProductionResponse> shots = loadKeyframes(context, production);
        List<ContinuityIssueResponse> continuity =
                continuity(context, production, shots);
        List<EpisodePostProductionResponse> episodes = new ArrayList<>();
        for (int index = 0; index < production.episodes().size(); index++) {
            episodes.add(episode(
                    context,
                    production,
                    index + 1,
                    production.episodes().get(index)));
        }
        return new ChapterPostProductionWorkspaceResponse(
                adaptationId,
                audioAssets,
                continuity,
                production.episodePlan().getId(),
                episodes,
                keyframeAssets,
                production.adaptation().getNovelid(),
                production.project().getId(),
                readiness,
                production.planId(),
                shots);
    }

    private static List<ShotPostProductionResponse> loadKeyframes(
            DSLContext context, VideoPostProductionContext production) {
        List<String> shotIds = production.shots().stream().map(VideoshotRecord::getId).toList();
        List<VideoshotkeyframeheadRecord> heads = context
                .selectFrom(VIDEOSHOTKEYFRAMEHEAD)
                .where(VIDEOSHOTKEYFRAMEHEAD.SHOTID.in(shotIds))
                .fetch();
        List<VideoshotkeyframeversionRecord> versions = context
                .selectFrom(VIDEOSHOTKEYFRAMEVERSION)
                .where(VIDEOSHOTKEYFRAMEVERSION.SHOTID.in(shotIds))
                .orderBy(
                        VIDEOSHOTKEYFRAMEVERSION.SHOTID,
                        VIDEOSHOTKEYFRAMEVERSION.ROLE,
                        VIDEOSHOTKEYFRAMEVERSION.VERSIONNO.desc())
                .fetch();
        List<String> assetIds = versions.stream()
                .map(VideoshotkeyframeversionRecord::getAssetid)
                .filter(Objects::nonNull)
                .distinct()
                .toList();
        Map<String, VideoassetRecord> assets = new HashMap<>();
        if (!assetIds.isEmpty()) {
            context.selectFrom(VIDEOASSET)
                    .where(VIDEOASSET.ID.in(assetIds))
                    .fetch()
                    .forEach(asset -> assets.put(asset.getId(), asset));
        }
        Map<KeyframeKey, VideoshotkeyframeheadRecord> headMap = new HashMap<>();
        heads.forEach(head -> headMap.put(
                new KeyframeKey(head.getShotid(), head.getRole()), head));
        Map<KeyframeKey, List<VideoshotkeyframeversionRecord>> versionMap = new HashMap<>();
        versions.forEach(version -> versionMap
                .computeIfAbsent(
                        new KeyframeKey(version.getShotid(), version.getRole()),
                        ignored -> new ArrayList<>())
                .add(version));
        return production.shots().stream()
                .map(shot -> new ShotPostProductionResponse(
                        KEYFRAME_ROLES.stream()
                                .map(role -> keyframeHead(
                                        shot.getId(),
                                        role,
                                        headMap.get(new KeyframeKey(shot.getId(), role)),
                                        versionMap.getOrDefault(
                                                new KeyframeKey(shot.getId(), role),
                                                List.of()),
                                        assets))
                                .toList(),
                        shot.getId(),
                        shot.getShotkey(),
                        shot.getTitle()))
                .toList();
    }

    private static ShotKeyframeHeadResponse keyframeHead(
            String shotId,
            String role,
            VideoshotkeyframeheadRecord head,
            List<VideoshotkeyframeversionRecord> versions,
            Map<String, VideoassetRecord> assets) {
        List<ShotKeyframeVersionResponse> history = versions.stream()
                .map(version -> keyframeVersion(
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
                    .orElseThrow(() -> new ApiException(
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

    private static ShotKeyframeVersionResponse keyframeVersion(
            VideoshotkeyframeversionRecord version, VideoassetRecord asset) {
        return new ShotKeyframeVersionResponse(
                asset == null
                        ? null
                        : JooqVideoPostProductionRepository.assetResponse(asset),
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

    private static List<ContinuityIssueResponse> continuity(
            DSLContext context,
            VideoPostProductionContext production,
            List<ShotPostProductionResponse> workspaces) {
        // blocking 仅表示素材事实已不可安全消费；创作性 warning/info 始终留给作者判断。
        List<ContinuityIssueResponse> issues = new ArrayList<>();
        Map<String, ShotPostProductionResponse> byShot = new HashMap<>();
        workspaces.forEach(workspace -> byShot.put(workspace.getShotId(), workspace));
        Set<String> activeAssetIds = new LinkedHashSet<>();
        for (ShotPostProductionResponse workspace : workspaces) {
            for (ShotKeyframeHeadResponse head : workspace.getHeads()) {
                if (head.getCurrentVersion() != null
                        && head.getCurrentVersion().getAsset() != null) {
                    activeAssetIds.add(head.getCurrentVersion().getAsset().getId());
                }
            }
        }
        Map<String, VideoassetRecord> currentAssets = new HashMap<>();
        if (!activeAssetIds.isEmpty()) {
            context.selectFrom(VIDEOASSET)
                    .where(VIDEOASSET.ID.in(activeAssetIds))
                    .fetch()
                    .forEach(asset -> currentAssets.put(asset.getId(), asset));
        }
        for (VideoshotRecord shot : production.shots()) {
            Map<String, PostProductionAssetResponse> active = new HashMap<>();
            for (ShotKeyframeHeadResponse head : byShot.get(shot.getId()).getHeads()) {
                ShotKeyframeVersionResponse version = head.getCurrentVersion();
                if (version == null || version.getAsset() == null) continue;
                active.put(head.getRole().getValue(), version.getAsset());
                if (version.getAsset().getModality()
                        != PostProductionAssetResponse.ModalityEnum.IMAGE) {
                    issues.add(issue(
                            "VIDEO_CONTINUITY_KEYFRAME_MODALITY_INVALID",
                            "blocking",
                            "已确认关键帧不再是图片素材",
                            List.of(shot.getId()),
                            "keyframe"));
                }
                VideoassetRecord current = currentAssets.get(version.getAsset().getId());
                if (current == null
                        || !"confirmed".equals(current.getRightsstatus())
                        || current.getLockedat() == null) {
                    issues.add(issue(
                            "VIDEO_CONTINUITY_KEYFRAME_RIGHTS_INVALID",
                            "blocking",
                            "已确认关键帧的素材授权或锁定状态已失效，请重新选择素材",
                            List.of(shot.getId()),
                            "keyframe"));
                }
            }
            PostProductionAssetResponse initial = active.get("initial_state");
            PostProductionAssetResponse ending = active.get("end_state");
            if (initial != null && ending != null && initial.getSha256().equals(ending.getSha256())) {
                issues.add(issue(
                        "VIDEO_CONTINUITY_IDENTICAL_ENDPOINTS",
                        "warning",
                        "首帧与尾帧使用同一图片，请确认镜头是否确实没有状态变化",
                        List.of(shot.getId()),
                        "keyframe"));
            }
            boolean highRisk = "action".equals(shot.getNarrativepurpose())
                    || List.of("动作", "冲突", "揭示", "转折").stream()
                            .anyMatch(marker -> shot.getStoryfunction() != null
                                    && shot.getStoryfunction().contains(marker));
            if (highRisk && active.isEmpty()) {
                issues.add(issue(
                        "VIDEO_CONTINUITY_HIGH_RISK_WITHOUT_KEYFRAME",
                        "info",
                        "动作或转折镜头尚未设置关键帧，可先生成候选，也可继续纯提示词生成",
                        List.of(shot.getId()),
                        "keyframe"));
            }
        }

        List<String> shotIds = production.shots().stream().map(VideoshotRecord::getId).toList();
        var promptRows = context
                .select(
                        VIDEOSHOTPROMPTHEAD.SHOTID,
                        VIDEOVISUALCANONVERSION.CANONID,
                        VIDEOVISUALCANONVERSION.ASSETID,
                        VIDEOVISUALCANON.DUTY,
                        VIDEOASSET.MODALITY,
                        VIDEOASSET.RIGHTSSTATUS,
                        VIDEOASSET.LOCKEDAT)
                .from(VIDEOSHOTPROMPTHEAD)
                .join(VIDEOSHOTPROMPTVISUALREFERENCE)
                .on(VIDEOSHOTPROMPTVISUALREFERENCE.PROMPTVERSIONID.eq(
                        VIDEOSHOTPROMPTHEAD.CURRENTVERSIONID))
                .join(VIDEOVISUALCANONVERSION)
                .on(VIDEOVISUALCANONVERSION.ID.eq(
                        VIDEOSHOTPROMPTVISUALREFERENCE.CANONVERSIONID))
                .join(VIDEOVISUALCANON)
                .on(VIDEOVISUALCANON.ID.eq(VIDEOVISUALCANONVERSION.CANONID))
                .leftJoin(VIDEOASSET)
                .on(VIDEOASSET.ID.eq(VIDEOVISUALCANONVERSION.ASSETID))
                .where(VIDEOSHOTPROMPTHEAD.SHOTID.in(shotIds))
                .fetch();
        Map<String, Map<String, CanonReference>> references = new HashMap<>();
        for (var row : promptRows) {
            String shotId = row.get(VIDEOSHOTPROMPTHEAD.SHOTID);
            String canonId = row.get(VIDEOVISUALCANONVERSION.CANONID);
            String assetId = row.get(VIDEOVISUALCANONVERSION.ASSETID);
            String duty = row.get(VIDEOVISUALCANON.DUTY);
            references.computeIfAbsent(shotId, ignored -> new HashMap<>())
                    .put(canonId, new CanonReference(assetId, duty));
            if (!"image".equals(row.get(VIDEOASSET.MODALITY))
                    || !"confirmed".equals(row.get(VIDEOASSET.RIGHTSSTATUS))
                    || row.get(VIDEOASSET.LOCKEDAT) == null) {
                issues.add(issue(
                        "VIDEO_CONTINUITY_PROMPT_REFERENCE_NOT_READY",
                        "blocking",
                        "正式提示词冻结的视觉参考已丢失、授权失效或不再是图片",
                        List.of(shotId),
                        duty));
            }
        }
        for (int index = 0; index + 1 < production.shots().size(); index++) {
            VideoshotRecord left = production.shots().get(index);
            VideoshotRecord right = production.shots().get(index + 1);
            Map<String, CanonReference> leftReferences =
                    references.getOrDefault(left.getId(), Map.of());
            Map<String, CanonReference> rightReferences =
                    references.getOrDefault(right.getId(), Map.of());
            Set<String> common = new java.util.TreeSet<>(leftReferences.keySet());
            common.retainAll(rightReferences.keySet());
            for (String canonId : common) {
                CanonReference first = leftReferences.get(canonId);
                CanonReference second = rightReferences.get(canonId);
                if (!Objects.equals(first.assetId(), second.assetId())) {
                    issues.add(issue(
                            "VIDEO_CONTINUITY_ADJACENT_CANON_VERSION_CHANGED",
                            "warning",
                            "相邻镜头的同一视觉设定采用了不同素材版本，请确认这是有意变化",
                            List.of(left.getId(), right.getId()),
                            first.duty()));
                }
            }
        }
        return List.copyOf(issues);
    }

    private EpisodePostProductionResponse episode(
            DSLContext context,
            VideoPostProductionContext production,
            int episodeNo,
            List<VideoshotRecord> episodeShots) {
        List<String> shotIds = episodeShots.stream().map(VideoshotRecord::getId).toList();
        List<Record> takeRows = context.select(VIDEOSHOTTAKE.fields())
                .select(VIDEOASSET.fields())
                .from(VIDEOSHOTTAKE)
                .join(VIDEOASSET)
                .on(VIDEOASSET.ID.eq(VIDEOSHOTTAKE.ASSETID))
                .where(VIDEOSHOTTAKE.SHOTID.in(shotIds))
                .orderBy(VIDEOSHOTTAKE.SHOTID, VIDEOSHOTTAKE.TAKENO)
                .fetch();
        Map<String, List<PostProductionTakeResponse>> takes = new HashMap<>();
        Map<String, VideoassetRecord> takeAssets = new HashMap<>();
        shotIds.forEach(shotId -> takes.put(shotId, new ArrayList<>()));
        for (Record row : takeRows) {
            VideoshottakeRecord take = row.into(VIDEOSHOTTAKE);
            VideoassetRecord asset = row.into(VIDEOASSET);
            takeAssets.put(take.getId(), asset);
            takes.get(take.getShotid()).add(takeResponse(take, asset));
        }
        Map<String, String> takeHeads = new HashMap<>();
        context.selectFrom(VIDEOSHOTTAKEHEAD)
                .where(VIDEOSHOTTAKEHEAD.SHOTID.in(shotIds))
                .fetch()
                .forEach(head -> takeHeads.put(head.getShotid(), head.getCurrenttakeid()));
        List<EpisodeShotResponse> shotResponses = episodeShots.stream()
                .map(shot -> new EpisodeShotResponse(
                        takeHeads.get(shot.getId()),
                        shot.getOrdinal(),
                        shot.getId(),
                        shot.getShotkey(),
                        EpisodeShotResponse.SpeechModeEnum.fromValue(speechMode(shot)),
                        shot.getSpokentext(),
                        takes.get(shot.getId()),
                        shot.getTimelinedurationms(),
                        shot.getTitle()))
                .toList();
        List<EpisodeEditClipResponse> defaultClips = new ArrayList<>();
        int timelineStart = 0;
        for (int index = 0; index < episodeShots.size(); index++) {
            VideoshotRecord shot = episodeShots.get(index);
            String takeId = takeHeads.get(shot.getId());
            VideoassetRecord asset = takeId == null ? null : takeAssets.get(takeId);
            int duration;
            Integer sourceIn;
            Integer sourceOut;
            if (asset != null && asset.getDurationms() != null && asset.getDurationms() >= 500) {
                duration = Math.min(shot.getTimelinedurationms(), asset.getDurationms());
                sourceIn = 0;
                sourceOut = duration;
            } else {
                takeId = null;
                duration = shot.getTimelinedurationms();
                sourceIn = null;
                sourceOut = null;
            }
            defaultClips.add(new EpisodeEditClipResponse(
                            index + 1,
                            duration,
                            shot.getId(),
                            timelineStart)
                    .takeId(takeId)
                    .sourceInMs(sourceIn)
                    .sourceOutMs(sourceOut)
                    .transitionAfter(EpisodeEditClipResponse.TransitionAfterEnum.CUT)
                    .transitionDurationMs(0));
            timelineStart += duration;
        }
        EpisodeEditHeadResponse editHead = timelines.editHeadResponse(
                context, production.episodePlan().getId(), episodeNo);
        List<EpisodeEditVersionSummaryResponse> editHistory = context
                .selectFrom(VIDEOEPISODEEDITVERSION)
                .where(
                        VIDEOEPISODEEDITVERSION.EPISODEPLANVERSIONID.eq(
                                production.episodePlan().getId()),
                        VIDEOEPISODEEDITVERSION.EPISODENO.eq(episodeNo))
                .orderBy(VIDEOEPISODEEDITVERSION.VERSIONNO.desc())
                .fetch()
                .stream()
                .map(JooqVideoPostProductionReadModel::editSummary)
                .toList();
        String currentEditId = editHead.getCurrentVersion() == null
                ? null
                : editHead.getCurrentVersion().getId();
        EpisodeMixHeadResponse mixHead = timelines.mixHeadResponse(
                context, production.episodePlan().getId(), episodeNo, currentEditId);
        List<EpisodeMixVersionSummaryResponse> mixHistory = context
                .selectFrom(VIDEOEPISODEMIXVERSION)
                .where(
                        VIDEOEPISODEMIXVERSION.EPISODEPLANVERSIONID.eq(
                                production.episodePlan().getId()),
                        VIDEOEPISODEMIXVERSION.EPISODENO.eq(episodeNo))
                .orderBy(VIDEOEPISODEMIXVERSION.VERSIONNO.desc())
                .fetch()
                .stream()
                .map(JooqVideoPostProductionReadModel::mixSummary)
                .toList();
        List<VideoepisodeexporttaskRecord> exportRows = context
                .selectFrom(VIDEOEPISODEEXPORTTASK)
                .where(
                        VIDEOEPISODEEXPORTTASK.EPISODEPLANVERSIONID.eq(
                                production.episodePlan().getId()),
                        VIDEOEPISODEEXPORTTASK.EPISODENO.eq(episodeNo))
                .orderBy(VIDEOEPISODEEXPORTTASK.CREATEDAT.desc())
                .fetch();
        List<EpisodeEditClipResponse> subtitleBase = editHead.getCurrentVersion() == null
                ? defaultClips
                : editHead.getCurrentVersion().getClips();
        return new EpisodePostProductionResponse(
                defaultClips,
                editHead,
                editHistory,
                episodeNo,
                exportRows.stream().map(task -> exports.response(context, task)).toList(),
                mixHead,
                mixHistory,
                shotResponses,
                subtitleSuggestions(episodeShots, subtitleBase));
    }

    private static List<EpisodeSubtitleCueInput> subtitleSuggestions(
            List<VideoshotRecord> shots, List<EpisodeEditClipResponse> clips) {
        Map<String, VideoshotRecord> shotMap = new HashMap<>();
        shots.forEach(shot -> shotMap.put(shot.getId(), shot));
        List<EpisodeSubtitleCueInput> result = new ArrayList<>();
        for (EpisodeEditClipResponse clip : clips) {
            VideoshotRecord shot = shotMap.get(clip.getShotId());
            if (shot == null
                    || "none".equals(speechMode(shot))
                    || shot.getSpokentext() == null
                    || shot.getSpokentext().isEmpty()) {
                continue;
            }
            int textLength = shot.getSpokentext()
                    .codePointCount(0, shot.getSpokentext().length());
            int duration = Math.min(
                    clip.getOutputDurationMs(), Math.max(800, textLength * 180));
            result.add(new EpisodeSubtitleCueInput(
                            clip.getTimelineStartMs() + duration,
                            clip.getTimelineStartMs(),
                            shot.getSpokentext())
                    .shotId(shot.getId())
                    .speaker(null));
        }
        return List.copyOf(result);
    }

    private static PostProductionTakeResponse takeResponse(
            VideoshottakeRecord take, VideoassetRecord asset) {
        PostProductionAssetResponse assetResponse =
                JooqVideoPostProductionRepository.assetResponse(asset)
                        .contentUrl("/api/v1/video/takes/" + take.getId() + "/content");
        return new PostProductionTakeResponse(
                assetResponse,
                DatabaseTimestamp.api(take.getCreatedat()),
                asset.getDurationms(),
                take.getId(),
                take.getShotid(),
                take.getTakeno());
    }

    private static String speechMode(VideoshotRecord shot) {
        if (shot.getSpeechmode() != null
                && Set.of("none", "sync", "offscreen", "voiceover")
                        .contains(shot.getSpeechmode())) {
            return shot.getSpeechmode();
        }
        if (shot.getAudiomode() == null) return "none";
        return switch (shot.getAudiomode()) {
            case "sync_dialogue" -> "sync";
            case "offscreen_dialogue" -> "offscreen";
            case "voiceover" -> "voiceover";
            default -> "none";
        };
    }

    private static ContinuityIssueResponse issue(
            String code,
            String severity,
            String message,
            List<String> shotIds,
            String duty) {
        return new ContinuityIssueResponse(
                        code,
                        message,
                        ContinuityIssueResponse.SeverityEnum.fromValue(severity),
                        shotIds)
                .duty(duty);
    }

    private static EpisodeEditVersionSummaryResponse editSummary(
            VideoepisodeeditversionRecord version) {
        return new EpisodeEditVersionSummaryResponse(
                version.getBasedonversionid(),
                version.getContenthash(),
                DatabaseTimestamp.api(version.getCreatedat()),
                version.getEpisodeno(),
                version.getId(),
                version.getTotaldurationms(),
                version.getVersionno());
    }

    private static EpisodeMixVersionSummaryResponse mixSummary(
            VideoepisodemixversionRecord version) {
        return new EpisodeMixVersionSummaryResponse(
                version.getBasedonversionid(),
                version.getContenthash(),
                DatabaseTimestamp.api(version.getCreatedat()),
                version.getEditversionid(),
                version.getEpisodeno(),
                version.getId(),
                version.getVersionno());
    }

    private record KeyframeKey(String shotId, String role) {}

    private record CanonReference(String assetId, String duty) {}
}
