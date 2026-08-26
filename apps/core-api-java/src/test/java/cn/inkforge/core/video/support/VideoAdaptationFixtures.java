package cn.inkforge.core.video.support;

import cn.inkforge.contracts.api.BeatCoverageGoal;
import cn.inkforge.contracts.api.ChapterAdaptationPlanCandidate;
import cn.inkforge.contracts.api.ChapterAdaptationSourceRange;
import cn.inkforge.contracts.api.CinematicSceneCandidate;
import cn.inkforge.contracts.api.CinematicShotCandidate;
import cn.inkforge.contracts.api.DramaticBeatCandidate;
import cn.inkforge.core.video.domain.VideoAdaptationPlans;
import java.util.List;
import org.openapitools.jackson.nullable.JsonNullable;

/** 视频应用、仓储和 HTTP 测试共用的最小有效电影化方案。 */
public final class VideoAdaptationFixtures {

    private VideoAdaptationFixtures() {}

    public static ChapterAdaptationPlanCandidate candidate(String adaptationId, String source) {
        var beatRange = new ChapterAdaptationSourceRange(
                source.codePointCount(0, source.length()), source, 0);
        int shotEnd = Math.min(2, source.codePointCount(0, source.length()));
        int shotEndOffset = source.offsetByCodePoints(0, shotEnd);
        var shotRange = new ChapterAdaptationSourceRange(
                shotEnd, source.substring(0, shotEndOffset), 0);
        var shot = new CinematicShotCandidate(
                "确认危险逼近",
                CinematicShotCandidate.CameraAngleEnum.EYE_LEVEL,
                CinematicShotCandidate.CameraMovementEnum.PUSH_IN,
                "门缝光线突然熄灭",
                CinematicShotCandidate.NarrativePurposeEnum.REVEAL,
                "S01",
                CinematicShotCandidate.ShotScaleEnum.CLOSE,
                "风声与木门轻响",
                List.of(shotRange),
                CinematicShotCandidate.SourceRelationEnum.DIRECT,
                CinematicShotCandidate.SpeechModeEnum.NONE,
                "揭示门后异常",
                5_000,
                "门缝微光",
                "镜头缓慢靠近门缝");
        shot.setCoveredGoalKeys(List.of("G01"));
        shot.setSpokenText(JsonNullable.of(null));
        var beat = new DramaticBeatCandidate(
                "B01",
                List.of(new BeatCoverageGoal(
                        "门后有人",
                        "G01",
                        BeatCoverageGoal.KindEnum.STORY_INFORMATION,
                        BeatCoverageGoal.PriorityEnum.ESSENTIAL)),
                "疑虑转为确信",
                List.of(shot),
                List.of(beatRange),
                "发现",
                "从环境空镜切到人物反应");
        var scene = new CinematicSceneCandidate(
                List.of(beat),
                "人物发现异常",
                "室内",
                "揭示真相",
                "SC01",
                "夜晚",
                "场景");
        var plan = new ChapterAdaptationPlanCandidate(
                adaptationId,
                List.of(scene),
                "chapter_adaptation_plan_v3",
                VideoAdaptationPlans.sourceHash(source));
        plan.setSuggestedEpisodeBreakAfterShotKeys(List.of());
        plan.setReviewFindings(List.of());
        plan.setReviewSummary(JsonNullable.of(null));
        return plan;
    }
}
