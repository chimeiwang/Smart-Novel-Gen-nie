package cn.inkforge.core.video.infrastructure;

import static cn.inkforge.core.db.generated.Tables.VIDEOCINEMATICSCENE;
import static cn.inkforge.core.db.generated.Tables.VIDEODRAMATICBEAT;
import static cn.inkforge.core.db.generated.Tables.VIDEODRAMATICBEATSOURCEANCHOR;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOT;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTPLANVERSION;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTPROMPTHEAD;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTSOURCEANCHOR;

import cn.inkforge.contracts.api.BeatCoverageGoal;
import cn.inkforge.contracts.api.ChapterAdaptationPlanCandidate;
import cn.inkforge.contracts.api.CinematicSceneCandidate;
import cn.inkforge.contracts.api.CinematicShotCandidate;
import cn.inkforge.contracts.api.DramaticBeatCandidate;
import cn.inkforge.core.db.generated.tables.records.ReviewartifactRecord;
import cn.inkforge.core.db.generated.tables.records.VideoadaptationtaskRecord;
import cn.inkforge.core.db.generated.tables.records.VideochapteradaptationRecord;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.video.domain.VideoAdaptationPlans;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.jooq.DSLContext;
import tools.jackson.databind.ObjectMapper;

/** 把已复核候选一次性物化为不可变 Scene → Beat → Shot 关系事实。 */
final class JooqVideoPlanMaterializer {

    private final CuidV1Generator ids;
    private final Clock clock;
    private final ObjectMapper json;

    JooqVideoPlanMaterializer(CuidV1Generator ids, Clock clock, ObjectMapper json) {
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
    }

    String materialize(
            DSLContext context,
            VideochapteradaptationRecord adaptation,
            ReviewartifactRecord artifact,
            VideoadaptationtaskRecord task,
            String userId,
            ChapterAdaptationPlanCandidate plan) {
        Integer maximum = context.select(org.jooq.impl.DSL.coalesce(
                        org.jooq.impl.DSL.max(VIDEOSHOTPLANVERSION.VERSIONNO), 0))
                .from(VIDEOSHOTPLANVERSION)
                .where(VIDEOSHOTPLANVERSION.ADAPTATIONID.eq(adaptation.getId()))
                .fetchOne(0, Integer.class);
        int versionNo = (maximum == null ? 0 : maximum) + 1;
        String versionId = ids.next();
        LocalDateTime now = DatabaseTimestamp.now(clock);
        context.insertInto(VIDEOSHOTPLANVERSION)
                .set(VIDEOSHOTPLANVERSION.ID, versionId)
                .set(VIDEOSHOTPLANVERSION.ADAPTATIONID, adaptation.getId())
                .set(VIDEOSHOTPLANVERSION.VERSIONNO, versionNo)
                .set(VIDEOSHOTPLANVERSION.BASEDONVERSIONID, task.getBaseshotplanversionid())
                .set(VIDEOSHOTPLANVERSION.SOURCETASKID, task.getId())
                .set(VIDEOSHOTPLANVERSION.REVIEWARTIFACTID, artifact.getId())
                .set(VIDEOSHOTPLANVERSION.CREATEDBYUSERID, userId)
                .set(VIDEOSHOTPLANVERSION.CONTENTHASH, VideoAdaptationPlans.contentHash(plan, json))
                .set(VIDEOSHOTPLANVERSION.CREATEDAT, now)
                .execute();

        int beatOrdinal = 0;
        int shotOrdinal = 0;
        for (int sceneIndex = 0; sceneIndex < plan.getScenes().size(); sceneIndex++) {
            CinematicSceneCandidate scene = plan.getScenes().get(sceneIndex);
            String sceneId = ids.next();
            context.insertInto(VIDEOCINEMATICSCENE)
                    .set(VIDEOCINEMATICSCENE.ID, sceneId)
                    .set(VIDEOCINEMATICSCENE.PLANVERSIONID, versionId)
                    .set(VIDEOCINEMATICSCENE.ADAPTATIONID, adaptation.getId())
                    .set(VIDEOCINEMATICSCENE.SCENEKEY, scene.getSceneKey())
                    .set(VIDEOCINEMATICSCENE.ORDINAL, sceneIndex + 1)
                    .set(VIDEOCINEMATICSCENE.TITLE, scene.getTitle())
                    .set(VIDEOCINEMATICSCENE.LOCATIONLABEL, scene.getLocationLabel())
                    .set(VIDEOCINEMATICSCENE.TIMELABEL, scene.getTimeLabel())
                    .set(VIDEOCINEMATICSCENE.OBJECTIVE, scene.getObjective())
                    .set(VIDEOCINEMATICSCENE.CHANGESUMMARY, scene.getChangeSummary())
                    .execute();
            for (DramaticBeatCandidate beat : scene.getBeats()) {
                beatOrdinal++;
                String beatId = ids.next();
                context.insertInto(VIDEODRAMATICBEAT)
                        .set(VIDEODRAMATICBEAT.ID, beatId)
                        .set(VIDEODRAMATICBEAT.PLANVERSIONID, versionId)
                        .set(VIDEODRAMATICBEAT.SCENEID, sceneId)
                        .set(VIDEODRAMATICBEAT.BEATKEY, beat.getBeatKey())
                        .set(VIDEODRAMATICBEAT.ORDINAL, beatOrdinal)
                        .set(VIDEODRAMATICBEAT.TITLE, beat.getTitle())
                        .set(VIDEODRAMATICBEAT.DRAMATICTURN, beat.getDramaticTurn())
                        .set(VIDEODRAMATICBEAT.VISUALSTRATEGY, beat.getVisualStrategy())
                        .set(
                                VIDEODRAMATICBEAT.COVERAGEGOALSJSON,
                                json.writeValueAsString(beat.getCoverageGoals().stream()
                                        .map(JooqVideoPlanMaterializer::goalMap)
                                        .toList()))
                        .execute();
                for (int rangeIndex = 0; rangeIndex < beat.getSourceRanges().size(); rangeIndex++) {
                    var range = beat.getSourceRanges().get(rangeIndex);
                    context.insertInto(VIDEODRAMATICBEATSOURCEANCHOR)
                            .set(VIDEODRAMATICBEATSOURCEANCHOR.BEATID, beatId)
                            .set(VIDEODRAMATICBEATSOURCEANCHOR.PLANVERSIONID, versionId)
                            .set(VIDEODRAMATICBEATSOURCEANCHOR.ORDINAL, rangeIndex + 1)
                            .set(VIDEODRAMATICBEATSOURCEANCHOR.STARTCODEPOINT, range.getStart())
                            .set(VIDEODRAMATICBEATSOURCEANCHOR.ENDCODEPOINT, range.getEnd())
                            .execute();
                }
                for (CinematicShotCandidate shot : beat.getShots()) {
                    shotOrdinal++;
                    String shotId = ids.next();
                    context.insertInto(VIDEOSHOT)
                            .set(VIDEOSHOT.ID, shotId)
                            .set(VIDEOSHOT.PLANVERSIONID, versionId)
                            .set(VIDEOSHOT.SCENEID, sceneId)
                            .set(VIDEOSHOT.BEATID, beatId)
                            .set(VIDEOSHOT.SHOTKEY, shot.getShotKey())
                            .set(VIDEOSHOT.ORDINAL, shotOrdinal)
                            .set(VIDEOSHOT.TITLE, shot.getTitle())
                            .set(
                                    VIDEOSHOT.NARRATIVEPURPOSE,
                                    shot.getNarrativePurpose().getValue())
                            .set(
                                    VIDEOSHOT.ADAPTATIONTYPE,
                                    legacyAdaptationType(shot.getSourceRelation().getValue()))
                            .set(VIDEOSHOT.SOURCERELATION, shot.getSourceRelation().getValue())
                            .set(VIDEOSHOT.STORYFUNCTION, shot.getStoryFunction())
                            .set(VIDEOSHOT.AUDIENCEGAIN, shot.getAudienceGain())
                            .set(
                                    VIDEOSHOT.COVEREDGOALKEYSJSON,
                                    json.writeValueAsString(list(shot.getCoveredGoalKeys())))
                            .set(VIDEOSHOT.SHOTSCALE, shot.getShotScale().getValue())
                            .set(VIDEOSHOT.CAMERAANGLE, shot.getCameraAngle().getValue())
                            .set(
                                    VIDEOSHOT.CAMERAMOVEMENT,
                                    shot.getCameraMovement().getValue())
                            .set(VIDEOSHOT.VISUALINTENT, shot.getVisualIntent())
                            .set(
                                    VIDEOSHOT.AUDIOMODE,
                                    legacyAudioMode(shot.getSpeechMode().getValue()))
                            .set(VIDEOSHOT.AUDIOINTENT, shot.getSoundDesign())
                            .set(VIDEOSHOT.SPEECHMODE, shot.getSpeechMode().getValue())
                            .set(VIDEOSHOT.SPOKENTEXT, nullable(shot.getSpokenText()))
                            .set(VIDEOSHOT.CUTREASON, shot.getCutReason())
                            .set(VIDEOSHOT.TIMELINEDURATIONMS, shot.getTimelineDurationMs())
                            .execute();
                    context.insertInto(VIDEOSHOTPROMPTHEAD)
                            .set(VIDEOSHOTPROMPTHEAD.SHOTID, shotId)
                            .set(VIDEOSHOTPROMPTHEAD.SHOTPLANVERSIONID, versionId)
                            .set(VIDEOSHOTPROMPTHEAD.REVISION, 1)
                            .set(VIDEOSHOTPROMPTHEAD.UPDATEDAT, now)
                            .execute();
                    for (int rangeIndex = 0;
                            rangeIndex < shot.getSourceRanges().size();
                            rangeIndex++) {
                        var range = shot.getSourceRanges().get(rangeIndex);
                        context.insertInto(VIDEOSHOTSOURCEANCHOR)
                                .set(VIDEOSHOTSOURCEANCHOR.SHOTID, shotId)
                                .set(VIDEOSHOTSOURCEANCHOR.PLANVERSIONID, versionId)
                                .set(VIDEOSHOTSOURCEANCHOR.ORDINAL, rangeIndex + 1)
                                .set(VIDEOSHOTSOURCEANCHOR.STARTCODEPOINT, range.getStart())
                                .set(VIDEOSHOTSOURCEANCHOR.ENDCODEPOINT, range.getEnd())
                                .execute();
                    }
                }
            }
        }
        return versionId;
    }

    private static Map<String, Object> goalMap(BeatCoverageGoal goal) {
        LinkedHashMap<String, Object> value = new LinkedHashMap<>();
        value.put("goalKey", goal.getGoalKey());
        value.put("kind", goal.getKind().getValue());
        value.put("priority", goal.getPriority().getValue());
        value.put("description", goal.getDescription());
        return value;
    }

    private static String legacyAdaptationType(String sourceRelation) {
        return "derived".equals(sourceRelation) ? "visualized" : sourceRelation;
    }

    private static String legacyAudioMode(String speechMode) {
        return switch (speechMode) {
            case "sync" -> "sync_dialogue";
            case "offscreen" -> "offscreen_dialogue";
            case "voiceover" -> "voiceover";
            case "none" -> "ambient";
            default -> throw new IllegalArgumentException("镜头对白模式无效");
        };
    }

    private static String nullable(
            org.openapitools.jackson.nullable.JsonNullable<String> value) {
        return value != null && value.isPresent() ? value.get() : null;
    }

    private static <T> List<T> list(List<T> value) {
        return value == null ? List.of() : value;
    }
}
