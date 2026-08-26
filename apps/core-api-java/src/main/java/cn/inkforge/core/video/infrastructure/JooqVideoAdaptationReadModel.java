package cn.inkforge.core.video.infrastructure;

import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACT;
import static cn.inkforge.core.db.generated.Tables.VIDEOADAPTATIONTASK;
import static cn.inkforge.core.db.generated.Tables.VIDEOCHAPTERADAPTATION;
import static cn.inkforge.core.db.generated.Tables.VIDEOCHAPTERADAPTATIONHEAD;
import static cn.inkforge.core.db.generated.Tables.VIDEOCINEMATICSCENE;
import static cn.inkforge.core.db.generated.Tables.VIDEODRAMATICBEAT;
import static cn.inkforge.core.db.generated.Tables.VIDEODRAMATICBEATSOURCEANCHOR;
import static cn.inkforge.core.db.generated.Tables.VIDEOEPISODEBOUNDARY;
import static cn.inkforge.core.db.generated.Tables.VIDEOEPISODEPLANVERSION;
import static cn.inkforge.core.db.generated.Tables.VIDEOPROJECT;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOT;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTPLANVERSION;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTPROMPTHEAD;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTPROMPTVERSION;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTSOURCEANCHOR;

import cn.inkforge.contracts.api.BeatCoverageGoal;
import cn.inkforge.contracts.api.ChapterAdaptationPlanCandidate;
import cn.inkforge.contracts.api.ChapterAdaptationResponse;
import cn.inkforge.contracts.api.ChapterAdaptationReviewSummary;
import cn.inkforge.contracts.api.ChapterAdaptationSourceRange;
import cn.inkforge.contracts.api.ChapterAdaptationTaskResponse;
import cn.inkforge.contracts.api.EpisodePlanResponse;
import cn.inkforge.contracts.api.FormalChapterAdaptationPlan;
import cn.inkforge.contracts.api.FormalCinematicScene;
import cn.inkforge.contracts.api.FormalCinematicShot;
import cn.inkforge.contracts.api.FormalDramaticBeat;
import cn.inkforge.contracts.api.ShotPromptCandidateResponse;
import cn.inkforge.contracts.api.ShotPromptSpecBatch;
import cn.inkforge.contracts.api.ShotPromptVersionResponse;
import cn.inkforge.contracts.api.ShotVisualReferenceSetResponse;
import cn.inkforge.contracts.api.ShotVisualReferenceSnapshot;
import cn.inkforge.core.db.generated.enums.Reviewartifactstatus;
import cn.inkforge.core.db.generated.tables.records.ReviewartifactRecord;
import cn.inkforge.core.db.generated.tables.records.VideoadaptationtaskRecord;
import cn.inkforge.core.db.generated.tables.records.VideochapteradaptationRecord;
import cn.inkforge.core.db.generated.tables.records.VideochapteradaptationheadRecord;
import cn.inkforge.core.db.generated.tables.records.VideocinematicsceneRecord;
import cn.inkforge.core.db.generated.tables.records.VideodramaticbeatRecord;
import cn.inkforge.core.db.generated.tables.records.VideoepisodeplanversionRecord;
import cn.inkforge.core.db.generated.tables.records.VideoprojectRecord;
import cn.inkforge.core.db.generated.tables.records.VideoshotRecord;
import cn.inkforge.core.db.generated.tables.records.VideoshotplanversionRecord;
import cn.inkforge.core.db.generated.tables.records.VideoshotpromptheadRecord;
import cn.inkforge.core.db.generated.tables.records.VideoshotpromptversionRecord;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.video.domain.SeedancePromptCompiler;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.jooq.DSLContext;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/** 从关系事实重建章节改编工作台；不把嵌套 JSON 当作正式镜头权威。 */
final class JooqVideoAdaptationReadModel {

    private static final Set<String> SOURCE_RELATIONS =
            Set.of("direct", "derived", "supplemental");
    private static final Set<String> VISUALIZED_ADAPTATION_TYPES =
            Set.of("visualized", "voiceover");
    private static final Set<String> SPEECH_MODES =
            Set.of("none", "sync", "offscreen", "voiceover");
    private static final Set<String> ACTIVE_TASK_STATUSES =
            Set.of("pending", "submitted", "processing");

    private final ObjectMapper json;
    private final JooqVideoVisualCanonRepository visualCanons;

    JooqVideoAdaptationReadModel(
            ObjectMapper json, JooqVideoVisualCanonRepository visualCanons) {
        this.json = Objects.requireNonNull(json);
        this.visualCanons = Objects.requireNonNull(visualCanons);
    }

    ChapterAdaptationResponse load(
            DSLContext context, String userId, String adaptationId) {
        VideochapteradaptationRecord adaptation = context
                .select(VIDEOCHAPTERADAPTATION.fields())
                .from(VIDEOCHAPTERADAPTATION)
                .join(VIDEOPROJECT)
                .on(VIDEOPROJECT.ID.eq(VIDEOCHAPTERADAPTATION.PROJECTID))
                .join(NOVEL)
                .on(NOVEL.ID.eq(VIDEOPROJECT.NOVELID))
                .where(
                        VIDEOCHAPTERADAPTATION.ID.eq(adaptationId),
                        NOVEL.USERID.eq(userId))
                .fetchOneInto(VideochapteradaptationRecord.class);
        if (adaptation == null) {
            throw new ApiException(
                    404,
                    "VIDEO_ADAPTATION_NOT_FOUND",
                    "章节影视化改编不存在");
        }
        VideochapteradaptationheadRecord head = context
                .selectFrom(VIDEOCHAPTERADAPTATIONHEAD)
                .where(VIDEOCHAPTERADAPTATIONHEAD.ADAPTATIONID.eq(adaptationId))
                .fetchOne();
        if (head == null) {
            throw new ApiException(
                    409,
                    "VIDEO_ADAPTATION_HEAD_MISSING",
                    "章节影视化改编缺少正式版本指针");
        }
        VideoprojectRecord project = context.selectFrom(VIDEOPROJECT)
                .where(VIDEOPROJECT.ID.eq(adaptation.getProjectid()))
                .fetchOne();
        if (project == null) {
            throw new ApiException(
                    409,
                    "VIDEO_ADAPTATION_PROJECT_MISSING",
                    "章节影视化项目不存在");
        }
        List<VideoadaptationtaskRecord> tasks = context.selectFrom(VIDEOADAPTATIONTASK)
                .where(VIDEOADAPTATIONTASK.ADAPTATIONID.eq(adaptationId))
                .orderBy(VIDEOADAPTATIONTASK.CREATEDAT.desc(), VIDEOADAPTATIONTASK.ID.desc())
                .fetch();
        VideoadaptationtaskRecord latestTask = tasks.isEmpty() ? null : tasks.getFirst();
        ReviewartifactRecord artifact = context.selectFrom(REVIEWARTIFACT)
                .where(REVIEWARTIFACT.VIDEOADAPTATIONID.eq(adaptationId))
                .orderBy(REVIEWARTIFACT.CREATEDAT.desc(), REVIEWARTIFACT.ID.desc())
                .limit(1)
                .fetchOne();
        FormalProjection formal = formalPlan(context, adaptation, head);
        ChapterAdaptationPlanCandidate candidate = candidate(artifact, adaptationId);
        ChapterAdaptationResponse.StateEnum state = state(
                latestTask, artifact, formal.plan() != null);
        return new ChapterAdaptationResponse(
                candidate,
                adaptation.getChapterid(),
                adaptation.getChaptertitle(),
                DatabaseTimestamp.api(adaptation.getChapterupdatedat()),
                DatabaseTimestamp.api(adaptation.getCreatedat()),
                formal.plan(),
                formal.episodePlan(),
                head.getRevision(),
                adaptation.getId(),
                latestTask == null ? null : task(latestTask),
                adaptation.getLifecyclestatus(),
                adaptation.getNovelid(),
                adaptation.getProjectid(),
                promptCandidates(
                        tasks,
                        formal.plan(),
                        formal.promptVersions(),
                        project.getTargetaspectratio()),
                formal.promptVersions(),
                artifact == null
                        ? null
                        : new ChapterAdaptationReviewSummary(
                                artifact.getId(),
                                artifact.getRevision(),
                                artifact.getStatus().getLiteral(),
                                artifact.getSummary(),
                                artifact.getTitle()),
                adaptation.getSourcehash(),
                adaptation.getSourcetext(),
                state,
                formal.visualReferenceSets());
    }

    private FormalProjection formalPlan(
            DSLContext context,
            VideochapteradaptationRecord adaptation,
            VideochapteradaptationheadRecord head) {
        if (head.getCurrentshotplanversionid() == null) {
            return FormalProjection.empty();
        }
        VideoshotplanversionRecord version = context.selectFrom(VIDEOSHOTPLANVERSION)
                .where(VIDEOSHOTPLANVERSION.ID.eq(head.getCurrentshotplanversionid()))
                .fetchOne();
        if (version == null || !adaptation.getId().equals(version.getAdaptationid())) {
            throw planInvalid("章节影视化当前镜头方案指针无效");
        }
        List<VideocinematicsceneRecord> scenes = context.selectFrom(VIDEOCINEMATICSCENE)
                .where(VIDEOCINEMATICSCENE.PLANVERSIONID.eq(version.getId()))
                .orderBy(VIDEOCINEMATICSCENE.ORDINAL)
                .fetch();
        List<VideodramaticbeatRecord> beats = context.selectFrom(VIDEODRAMATICBEAT)
                .where(VIDEODRAMATICBEAT.PLANVERSIONID.eq(version.getId()))
                .orderBy(VIDEODRAMATICBEAT.ORDINAL)
                .fetch();
        List<VideoshotRecord> shots = context.selectFrom(VIDEOSHOT)
                .where(VIDEOSHOT.PLANVERSIONID.eq(version.getId()))
                .orderBy(VIDEOSHOT.ORDINAL)
                .fetch();

        Map<String, List<ChapterAdaptationSourceRange>> beatRanges = new HashMap<>();
        context.selectFrom(VIDEODRAMATICBEATSOURCEANCHOR)
                .where(VIDEODRAMATICBEATSOURCEANCHOR.PLANVERSIONID.eq(version.getId()))
                .orderBy(
                        VIDEODRAMATICBEATSOURCEANCHOR.BEATID,
                        VIDEODRAMATICBEATSOURCEANCHOR.ORDINAL)
                .fetch()
                .forEach(anchor -> beatRanges
                        .computeIfAbsent(anchor.getBeatid(), ignored -> new ArrayList<>())
                        .add(sourceRange(
                                adaptation.getSourcetext(),
                                anchor.getStartcodepoint(),
                                anchor.getEndcodepoint())));
        Map<String, List<ChapterAdaptationSourceRange>> shotRanges = new HashMap<>();
        context.selectFrom(VIDEOSHOTSOURCEANCHOR)
                .where(VIDEOSHOTSOURCEANCHOR.PLANVERSIONID.eq(version.getId()))
                .orderBy(VIDEOSHOTSOURCEANCHOR.SHOTID, VIDEOSHOTSOURCEANCHOR.ORDINAL)
                .fetch()
                .forEach(anchor -> shotRanges
                        .computeIfAbsent(anchor.getShotid(), ignored -> new ArrayList<>())
                        .add(sourceRange(
                                adaptation.getSourcetext(),
                                anchor.getStartcodepoint(),
                                anchor.getEndcodepoint())));

        Map<String, List<BeatCoverageGoal>> goalsByBeat = new HashMap<>();
        int goalNumber = 0;
        for (VideodramaticbeatRecord beat : beats) {
            if (beat.getCoveragegoalsjson() == null) {
                goalNumber++;
                goalsByBeat.put(beat.getId(), List.of(new BeatCoverageGoal(
                        beat.getDramaticturn(),
                        "G%02d".formatted(goalNumber),
                        BeatCoverageGoal.KindEnum.STORY_INFORMATION,
                        BeatCoverageGoal.PriorityEnum.ESSENTIAL)));
            } else {
                List<BeatCoverageGoal> goals = goals(beat.getCoveragegoalsjson());
                goalsByBeat.put(beat.getId(), goals);
                goalNumber += goals.size();
            }
        }

        Map<String, List<FormalCinematicShot>> shotsByBeat = new HashMap<>();
        for (VideoshotRecord shot : shots) {
            List<String> fallback = goalsByBeat.getOrDefault(shot.getBeatid(), List.of()).stream()
                    .map(BeatCoverageGoal::getGoalKey)
                    .limit(1)
                    .toList();
            String speechMode = speechMode(shot);
            FormalCinematicShot formal = new FormalCinematicShot(
                    valueOr(shot.getAudiencegain(), shot.getVisualintent()),
                    FormalCinematicShot.CameraAngleEnum.fromValue(shot.getCameraangle()),
                    FormalCinematicShot.CameraMovementEnum.fromValue(shot.getCameramovement()),
                    shot.getCutreason(),
                    shot.getId(),
                    FormalCinematicShot.NarrativePurposeEnum.fromValue(
                            shot.getNarrativepurpose()),
                    shot.getShotkey(),
                    FormalCinematicShot.ShotScaleEnum.fromValue(shot.getShotscale()),
                    shot.getAudiointent(),
                    shotRanges.getOrDefault(shot.getId(), List.of()),
                    FormalCinematicShot.SourceRelationEnum.fromValue(sourceRelation(shot)),
                    FormalCinematicShot.SpeechModeEnum.fromValue(speechMode),
                    valueOr(shot.getStoryfunction(), shot.getCutreason()),
                    shot.getTimelinedurationms(),
                    shot.getTitle(),
                    shot.getVisualintent());
            formal.setCoveredGoalKeys(
                    stringList(shot.getCoveredgoalkeysjson(), fallback, "正式镜头方案的目标绑定数据损坏"));
            formal.setSpokenText(shot.getSpokentext() != null
                    ? shot.getSpokentext()
                    : !"none".equals(speechMode) ? shot.getAudiointent() : null);
            shotsByBeat.computeIfAbsent(shot.getBeatid(), ignored -> new ArrayList<>())
                    .add(formal);
        }
        Map<String, List<FormalDramaticBeat>> beatsByScene = new HashMap<>();
        for (VideodramaticbeatRecord beat : beats) {
            beatsByScene.computeIfAbsent(beat.getSceneid(), ignored -> new ArrayList<>())
                    .add(new FormalDramaticBeat(
                            beat.getBeatkey(),
                            goalsByBeat.get(beat.getId()),
                            beat.getDramaticturn(),
                            beat.getId(),
                            shotsByBeat.getOrDefault(beat.getId(), List.of()),
                            beatRanges.getOrDefault(beat.getId(), List.of()),
                            beat.getTitle(),
                            beat.getVisualstrategy()));
        }
        List<FormalCinematicScene> formalScenes = scenes.stream()
                .map(scene -> new FormalCinematicScene(
                        beatsByScene.getOrDefault(scene.getId(), List.of()),
                        scene.getChangesummary(),
                        scene.getId(),
                        scene.getLocationlabel(),
                        scene.getObjective(),
                        scene.getScenekey(),
                        scene.getTimelabel(),
                        scene.getTitle()))
                .toList();
        EpisodePlanResponse episode = episodePlan(context, head, shots);
        Map<String, String> shotKeyById = new HashMap<>();
        shots.forEach(shot -> shotKeyById.put(shot.getId(), shot.getShotkey()));
        List<String> episodeBreakKeys = episode == null
                ? List.of()
                : episode.getBreakAfterShotIds().stream().map(shotKeyById::get).toList();
        if (episodeBreakKeys.stream().anyMatch(Objects::isNull)) {
            throw new ApiException(
                    409, "VIDEO_EPISODE_PLAN_INVALID", "当前分集版本引用了其他镜头方案");
        }
        FormalChapterAdaptationPlan plan = new FormalChapterAdaptationPlan(
                adaptation.getId(),
                version.getId(),
                formalScenes,
                "chapter_adaptation_plan_v3",
                adaptation.getSourcehash(),
                version.getVersionno());
        plan.setBasedOnVersionId(version.getBasedonversionid());
        plan.setEpisodeBreakAfterShotKeys(episodeBreakKeys);
        return new FormalProjection(
                plan,
                episode,
                promptVersions(context, shots),
                visualCanons.shotReferences(context, shots));
    }

    private EpisodePlanResponse episodePlan(
            DSLContext context,
            VideochapteradaptationheadRecord head,
            List<VideoshotRecord> shots) {
        if (head.getCurrentepisodeplanversionid() == null) return null;
        VideoepisodeplanversionRecord version = context.selectFrom(VIDEOEPISODEPLANVERSION)
                .where(VIDEOEPISODEPLANVERSION.ID.eq(head.getCurrentepisodeplanversionid()))
                .fetchOne();
        if (version == null) {
            throw new ApiException(
                    409, "VIDEO_EPISODE_PLAN_INVALID", "当前分集版本指针无效");
        }
        List<String> boundaries = context.select(VIDEOEPISODEBOUNDARY.AFTERSHOTID)
                .from(VIDEOEPISODEBOUNDARY)
                .where(VIDEOEPISODEBOUNDARY.EPISODEPLANVERSIONID.eq(version.getId()))
                .orderBy(VIDEOEPISODEBOUNDARY.ORDINAL)
                .fetch(VIDEOEPISODEBOUNDARY.AFTERSHOTID);
        var shotIds = shots.stream().map(VideoshotRecord::getId)
                .collect(java.util.stream.Collectors.toSet());
        if (!shotIds.containsAll(boundaries)) {
            throw new ApiException(
                    409, "VIDEO_EPISODE_PLAN_INVALID", "当前分集版本引用了其他镜头方案");
        }
        return new EpisodePlanResponse(
                boundaries, version.getId(), version.getShotplanversionid(), version.getVersionno());
    }

    private List<ShotPromptVersionResponse> promptVersions(
            DSLContext context, List<VideoshotRecord> shots) {
        if (shots.isEmpty()) return List.of();
        Map<String, VideoshotRecord> shotById = new HashMap<>();
        shots.forEach(shot -> shotById.put(shot.getId(), shot));
        List<VideoshotpromptheadRecord> heads = context.selectFrom(VIDEOSHOTPROMPTHEAD)
                .where(VIDEOSHOTPROMPTHEAD.SHOTID.in(shotById.keySet()))
                .fetch();
        Map<String, VideoshotpromptheadRecord> headByShot = new HashMap<>();
        heads.forEach(head -> headByShot.put(head.getShotid(), head));
        List<String> versionIds = heads.stream()
                .map(VideoshotpromptheadRecord::getCurrentversionid)
                .filter(Objects::nonNull)
                .toList();
        if (versionIds.isEmpty()) return List.of();
        List<VideoshotpromptversionRecord> versions = context.selectFrom(VIDEOSHOTPROMPTVERSION)
                .where(VIDEOSHOTPROMPTVERSION.ID.in(versionIds))
                .fetch();
        versions.sort(Comparator.comparingInt(value -> shotById.get(value.getShotid()).getOrdinal()));
        Map<String, List<ShotVisualReferenceSnapshot>> references =
                visualCanons.promptReferences(context, versionIds);
        return versions.stream()
                .map(version -> new ShotPromptVersionResponse(
                        DatabaseTimestamp.api(version.getCreatedat()),
                        version.getCurrenttext(),
                        version.getGeneratedtext(),
                        headByShot.get(version.getShotid()).getRevision(),
                        version.getId(),
                        version.getGeneratedtext() == null
                                || !version.getGeneratedtext().equals(version.getCurrenttext()),
                        version.getShotid(),
                        shotById.get(version.getShotid()).getShotkey(),
                        version.getVersionno(),
                        references.getOrDefault(version.getId(), List.of())))
                .toList();
    }

    private List<ShotPromptCandidateResponse> promptCandidates(
            List<VideoadaptationtaskRecord> tasks,
            FormalChapterAdaptationPlan currentPlan,
            List<ShotPromptVersionResponse> promptVersions,
            String ratio) {
        if (currentPlan == null) return List.of();
        Map<String, FormalCinematicShot> shotByKey = new java.util.LinkedHashMap<>();
        currentPlan.getScenes().forEach(scene -> scene.getBeats().forEach(beat ->
                beat.getShots().forEach(shot -> shotByKey.put(shot.getShotKey(), shot))));
        Map<String, String> savedGenerated = new HashMap<>();
        promptVersions.forEach(value -> savedGenerated.put(
                value.getShotId(), value.getGeneratedText()));
        Set<String> seenShotIds = new java.util.HashSet<>();
        List<ShotPromptCandidateResponse> candidates = new ArrayList<>();
        for (VideoadaptationtaskRecord task : tasks) {
            if (!"shot_prompt".equals(task.getKind())
                    || !"completed".equals(task.getStatus())
                    || !Objects.equals(
                            task.getBaseshotplanversionid(), currentPlan.getPlanVersionId())
                    || task.getResultjson() == null) {
                continue;
            }
            try {
                JsonNode result = json.readTree(task.getResultjson());
                ShotPromptSpecBatch batch =
                        json.convertValue(result.get("promptBatch"), ShotPromptSpecBatch.class);
                if (batch.getPrompts() == null || batch.getPrompts().isEmpty()) continue;
                VideoAdaptationTaskPayload payload =
                        VideoAdaptationTaskPayload.parse(json, task.getRequestjson());
                Map<String, List<ShotVisualReferenceSnapshot>> references =
                        payload.visualReferencesByShot();
                for (var item : batch.getPrompts()) {
                    FormalCinematicShot shot = shotByKey.get(item.getShotKey());
                    if (shot == null || seenShotIds.contains(shot.getId())) continue;
                    // 最新任务已经声明该镜头后就不再回退到更旧候选，即使新候选损坏或已保存。
                    seenShotIds.add(shot.getId());
                    String compiled = SeedancePromptCompiler.compile(
                            item.getSpec(), ratio, shot.getTimelineDurationMs());
                    if (Objects.equals(savedGenerated.get(shot.getId()), compiled)) continue;
                    var candidate = new ShotPromptCandidateResponse(
                            compiled,
                            shot.getId(),
                            shot.getShotKey(),
                            item.getSpec(),
                            task.getId(),
                            references.getOrDefault(shot.getShotKey(), List.of()));
                    candidate.setQualityWarnings(list(item.getQualityWarnings()));
                    candidates.add(candidate);
                }
            } catch (RuntimeException ignored) {
                // 损坏的历史候选不妨碍正式方案和已保存提示词读取。
            }
        }
        Map<String, Integer> positions = new HashMap<>();
        int position = 0;
        for (FormalCinematicShot shot : shotByKey.values()) {
            positions.put(shot.getId(), position++);
        }
        candidates.sort(Comparator.comparingInt(value -> positions.get(value.getShotId())));
        return List.copyOf(candidates);
    }

    private ChapterAdaptationPlanCandidate candidate(
            ReviewartifactRecord artifact, String adaptationId) {
        if (artifact == null || artifact.getStatus() != Reviewartifactstatus.awaiting_user) {
            return null;
        }
        try {
            JsonNode payload = json.readTree(artifact.getPayloadjson());
            JsonNode target = payload.path("applyTarget");
            if (!"video_adaptation_plan".equals(target.path("type").asString())
                    || !adaptationId.equals(target.path("adaptationId").asString())) {
                return null;
            }
            JsonNode value = payload.get("candidate");
            if (value == null
                    || !"chapter_adaptation_plan_v3"
                            .equals(value.path("schemaVersion").asString())) {
                return null;
            }
            return json.convertValue(value, ChapterAdaptationPlanCandidate.class);
        } catch (RuntimeException exception) {
            return null;
        }
    }

    private List<BeatCoverageGoal> goals(String serialized) {
        try {
            Object value = json.readValue(serialized, new TypeReference<Object>() {});
            if (!(value instanceof List<?> list) || list.isEmpty()) throw new IllegalArgumentException();
            return list.stream()
                    .map(item -> json.convertValue(item, BeatCoverageGoal.class))
                    .toList();
        } catch (RuntimeException exception) {
            throw planInvalid("正式镜头方案的覆盖目标数据损坏");
        }
    }

    private List<String> stringList(
            String serialized, List<String> fallback, String message) {
        if (serialized == null) return fallback;
        try {
            Object value = json.readValue(serialized, new TypeReference<Object>() {});
            if (!(value instanceof List<?> list)
                    || list.stream().anyMatch(item -> !(item instanceof String))) {
                throw new IllegalArgumentException();
            }
            return list.stream().map(String.class::cast).toList();
        } catch (RuntimeException exception) {
            throw planInvalid(message);
        }
    }

    private static ChapterAdaptationSourceRange sourceRange(
            String source, int startCodePoint, int endCodePoint) {
        try {
            int count = source.codePointCount(0, source.length());
            if (startCodePoint < 0 || endCodePoint <= startCodePoint || endCodePoint > count) {
                throw new IllegalArgumentException();
            }
            int start = source.offsetByCodePoints(0, startCodePoint);
            int end = source.offsetByCodePoints(0, endCodePoint);
            return new ChapterAdaptationSourceRange(
                    endCodePoint, source.substring(start, end), startCodePoint);
        } catch (RuntimeException exception) {
            throw planInvalid("正式镜头方案的来源范围无效");
        }
    }

    private static String sourceRelation(VideoshotRecord shot) {
        if (shot.getSourcerelation() != null
                && SOURCE_RELATIONS.contains(shot.getSourcerelation())) {
            return shot.getSourcerelation();
        }
        if ("supplemental".equals(shot.getAdaptationtype())) return "supplemental";
        if (VISUALIZED_ADAPTATION_TYPES.contains(shot.getAdaptationtype())) {
            return "derived";
        }
        return "direct";
    }

    private static String speechMode(VideoshotRecord shot) {
        if (shot.getSpeechmode() != null && SPEECH_MODES.contains(shot.getSpeechmode())) {
            return shot.getSpeechmode();
        }
        return switch (shot.getAudiomode()) {
            case "sync_dialogue" -> "sync";
            case "offscreen_dialogue" -> "offscreen";
            case "voiceover" -> "voiceover";
            default -> "none";
        };
    }

    private static String valueOr(String value, String fallback) {
        return value == null ? fallback : value;
    }

    private static ChapterAdaptationTaskResponse task(VideoadaptationtaskRecord value) {
        return new ChapterAdaptationTaskResponse(
                value.getBaseshotplanversionid(),
                value.getCheckpointstage(),
                DatabaseTimestamp.api(value.getCreatedat()),
                value.getId(),
                value.getJobid(),
                ChapterAdaptationTaskResponse.KindEnum.fromValue(value.getKind()),
                value.getLasterrorcode(),
                value.getLasterrormessage(),
                value.getStatus(),
                DatabaseTimestamp.api(value.getUpdatedat()),
                value.getWorkflow());
    }

    private static ChapterAdaptationResponse.StateEnum state(
            VideoadaptationtaskRecord latest,
            ReviewartifactRecord artifact,
            boolean hasPlan) {
        if (latest != null
                && ACTIVE_TASK_STATUSES.contains(latest.getStatus())) {
            return ChapterAdaptationResponse.StateEnum.GENERATING;
        }
        if (artifact != null && artifact.getStatus() == Reviewartifactstatus.awaiting_user) {
            return ChapterAdaptationResponse.StateEnum.AWAITING_REVIEW;
        }
        if (hasPlan) return ChapterAdaptationResponse.StateEnum.APPROVED;
        if (latest != null && "failed".equals(latest.getStatus())) {
            return ChapterAdaptationResponse.StateEnum.FAILED;
        }
        return ChapterAdaptationResponse.StateEnum.EMPTY;
    }

    private static ApiException planInvalid(String message) {
        return new ApiException(409, "VIDEO_ADAPTATION_PLAN_INVALID", message);
    }

    private static <T> List<T> list(List<T> value) {
        return value == null ? List.of() : List.copyOf(value);
    }

    private record FormalProjection(
            FormalChapterAdaptationPlan plan,
            EpisodePlanResponse episodePlan,
            List<ShotPromptVersionResponse> promptVersions,
            List<ShotVisualReferenceSetResponse> visualReferenceSets) {

        private static FormalProjection empty() {
            return new FormalProjection(null, null, List.of(), List.of());
        }
    }
}
