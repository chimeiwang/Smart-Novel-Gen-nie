package cn.inkforge.core.video.domain;

import cn.inkforge.contracts.api.BeatCoverageGoal;
import cn.inkforge.contracts.api.ChapterAdaptationPlanCandidate;
import cn.inkforge.contracts.api.ChapterAdaptationSourceRange;
import cn.inkforge.contracts.api.CinematicReviewFinding;
import cn.inkforge.contracts.api.CinematicSceneCandidate;
import cn.inkforge.contracts.api.CinematicShotCandidate;
import cn.inkforge.contracts.api.DramaticBeatCandidate;
import cn.inkforge.contracts.api.FormalChapterAdaptationPlan;
import cn.inkforge.contracts.api.FormalCinematicScene;
import cn.inkforge.contracts.api.FormalCinematicShot;
import cn.inkforge.contracts.api.FormalDramaticBeat;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.openapitools.jackson.nullable.JsonNullable;
import tools.jackson.databind.ObjectMapper;

/**
 * 章节镜头方案的跨语言规范投影、来源校验和不可变内容哈希。
 *
 * <p>这里集中维护 Java、Python Agent 与持久化版本共同依赖的结构约束：连续 Key、覆盖关系、Unicode
 * code point 来源区间、分集顺序及规范 JSON。审镜 finding 和节奏建议仍是软信息，不在这里替作者决定好坏。
 */
public final class VideoAdaptationPlans {

    private static final List<String> MECHANICAL_CUT_MARKERS = List.of(
            "说话人变化",
            "说话人切换",
            "句子结束",
            "原文换行",
            "段落结束",
            "进入下一句",
            "下一句话");

    private VideoAdaptationPlans() {}

    public static void validateCandidate(ChapterAdaptationPlanCandidate plan) {
        require(plan != null, "镜头方案不能为空");
        require("chapter_adaptation_plan_v3".equals(plan.getSchemaVersion()), "镜头方案版本无效");
        require(plan.getScenes() != null && !plan.getScenes().isEmpty(), "镜头方案至少需要一个场景");
        require(plan.getScenes().size() <= 30, "镜头方案场景数量超过上限");

        List<DramaticBeatCandidate> beats = new ArrayList<>();
        List<CinematicShotCandidate> shots = new ArrayList<>();
        List<BeatCoverageGoal> goals = new ArrayList<>();
        for (int sceneIndex = 0; sceneIndex < plan.getScenes().size(); sceneIndex++) {
            CinematicSceneCandidate scene = plan.getScenes().get(sceneIndex);
            require(key("SC", sceneIndex + 1).equals(scene.getSceneKey()),
                    "场景 Key 必须从 SC01 连续递增");
            require(scene.getBeats() != null && !scene.getBeats().isEmpty(),
                    "每个场景至少需要一个戏剧节拍");
            require(scene.getBeats().size() <= 40, "单个场景戏剧节拍数量超过上限");
            beats.addAll(scene.getBeats());
        }
        for (int beatIndex = 0; beatIndex < beats.size(); beatIndex++) {
            DramaticBeatCandidate beat = beats.get(beatIndex);
            require(key("B", beatIndex + 1).equals(beat.getBeatKey()),
                    "戏剧节拍 Key 必须从 B01 连续递增");
            require(beat.getCoverageGoals() != null && !beat.getCoverageGoals().isEmpty(),
                    "每个戏剧节拍至少需要一个覆盖目标");
            require(beat.getCoverageGoals().size() <= 12, "戏剧节拍覆盖目标数量超过上限");
            require(beat.getSourceRanges() != null && !beat.getSourceRanges().isEmpty(),
                    "每个戏剧节拍至少需要一个原文来源");
            require(beat.getSourceRanges().size() <= 24, "戏剧节拍来源数量超过上限");
            validateOrderedRanges(beat.getSourceRanges(), "节拍来源");
            require(beat.getShots() != null && !beat.getShots().isEmpty(),
                    "每个戏剧节拍至少需要一个镜头");
            require(beat.getShots().size() <= 40, "单个戏剧节拍镜头数量超过上限");
            Set<String> goalKeys = new HashSet<>();
            for (BeatCoverageGoal goal : beat.getCoverageGoals()) {
                require(goalKeys.add(goal.getGoalKey()), "同一戏剧节拍的覆盖目标不能重复");
                goals.add(goal);
            }
            for (CinematicShotCandidate shot : beat.getShots()) {
                validateShot(shot, beat, goalKeys);
                shots.add(shot);
            }
        }
        for (int goalIndex = 0; goalIndex < goals.size(); goalIndex++) {
            require(key("G", goalIndex + 1).equals(goals.get(goalIndex).getGoalKey()),
                    "覆盖目标 Key 必须从 G01 连续递增");
        }
        require(shots.size() <= 120, "单章镜头数量不能超过 120");
        for (int shotIndex = 0; shotIndex < shots.size(); shotIndex++) {
            require(key("S", shotIndex + 1).equals(shots.get(shotIndex).getShotKey()),
                    "镜头 Key 必须从 S01 连续递增");
        }
        validateBoundaries(
                list(plan.getSuggestedEpisodeBreakAfterShotKeys()),
                shots.stream().map(CinematicShotCandidate::getShotKey).toList(),
                "建议分集边界");
        validateFindings(list(plan.getReviewFindings()), plan.getScenes(), beats, shots);
    }

    public static void validateAgainstSource(
            ChapterAdaptationPlanCandidate plan,
            String adaptationId,
            String sourceText,
            String sourceHash) {
        validateCandidate(plan);
        if (!Objects.equals(plan.getAdaptationId(), adaptationId)
                || !Objects.equals(plan.getSourceHash(), sourceHash)) {
            throw sourceInvalid();
        }
        // 索引按 Unicode code point 解释，并逐段核对冻结原文，避免 Java UTF-16 下标与 Python 偏移不一致。
        for (CinematicSceneCandidate scene : plan.getScenes()) {
            for (DramaticBeatCandidate beat : scene.getBeats()) {
                List<ChapterAdaptationSourceRange> ranges = new ArrayList<>(beat.getSourceRanges());
                beat.getShots().forEach(shot -> ranges.addAll(shot.getSourceRanges()));
                for (ChapterAdaptationSourceRange range : ranges) {
                    if (!Objects.equals(
                            range.getSourceText(),
                            codePointSlice(sourceText, range.getStart(), range.getEnd()))) {
                        throw sourceInvalid();
                    }
                }
            }
        }
    }

    public static void validateEpisodeBoundaries(
            List<String> boundaries, List<String> orderedShotIds) {
        validateBoundaries(boundaries, orderedShotIds, "分集边界");
    }

    public static ChapterAdaptationPlanCandidate candidateFromFormal(
            FormalChapterAdaptationPlan plan) {
        List<CinematicSceneCandidate> scenes = plan.getScenes().stream()
                .map(VideoAdaptationPlans::candidateScene)
                .toList();
        var candidate = new ChapterAdaptationPlanCandidate(
                plan.getAdaptationId(), scenes, "chapter_adaptation_plan_v3", plan.getSourceHash());
        candidate.setSuggestedEpisodeBreakAfterShotKeys(
                list(plan.getEpisodeBreakAfterShotKeys()));
        candidate.setReviewFindings(List.of());
        return candidate;
    }

    public static Map<String, Object> candidateMap(ChapterAdaptationPlanCandidate plan) {
        LinkedHashMap<String, Object> value = new LinkedHashMap<>();
        value.put("schemaVersion", plan.getSchemaVersion());
        value.put("adaptationId", plan.getAdaptationId());
        value.put("sourceHash", plan.getSourceHash());
        value.put("scenes", plan.getScenes().stream()
                .map(VideoAdaptationPlans::sceneMap)
                .toList());
        value.put(
                "suggestedEpisodeBreakAfterShotKeys",
                list(plan.getSuggestedEpisodeBreakAfterShotKeys()));
        value.put("reviewSummary", nullable(plan.getReviewSummary()));
        value.put("reviewFindings", list(plan.getReviewFindings()).stream()
                .map(VideoAdaptationPlans::findingMap)
                .toList());
        return value;
    }

    public static String contentHash(
            ChapterAdaptationPlanCandidate plan, ObjectMapper json) {
        // 只对显式规范投影做哈希，避免 DTO 序列化器默认值或字段顺序变化破坏跨语言幂等。
        return CommandIdempotency.sha256(
                CommandIdempotency.canonicalJsonBytes(candidateMap(plan), json));
    }

    public static String sourceHash(String sourceText) {
        return CommandIdempotency.sha256(sourceText.getBytes(StandardCharsets.UTF_8));
    }

    private static void validateShot(
            CinematicShotCandidate shot,
            DramaticBeatCandidate beat,
            Set<String> goalKeys) {
        int duration = shot.getTimelineDurationMs() == null ? 0 : shot.getTimelineDurationMs();
        require(duration >= 500 && duration <= 15_000 && duration % 500 == 0,
                "镜头时间线时长只允许 500ms 到 15000ms 的 500ms 粒度");
        List<ChapterAdaptationSourceRange> ranges = list(shot.getSourceRanges());
        if (shot.getSourceRelation() == CinematicShotCandidate.SourceRelationEnum.DIRECT
                || shot.getSourceRelation() == CinematicShotCandidate.SourceRelationEnum.DERIVED) {
            require(!ranges.isEmpty(), "原文直呈或合理推导镜头至少需要一个原文来源");
        }
        validateOrderedRanges(ranges, "镜头来源");
        Set<String> covered = new HashSet<>();
        for (String goalKey : list(shot.getCoveredGoalKeys())) {
            require(covered.add(goalKey), "镜头承担的覆盖目标不能重复");
            require(goalKeys.contains(goalKey),
                    "镜头 " + shot.getShotKey() + " 引用了所属节拍之外的覆盖目标");
        }
        String spokenText = nullable(shot.getSpokenText());
        if (shot.getSpeechMode() == CinematicShotCandidate.SpeechModeEnum.NONE) {
            require(spokenText == null, "无对白镜头不能携带 spokenText");
        } else {
            require(spokenText != null && !spokenText.strip().isEmpty(),
                    "存在对白或旁白时必须提供 spokenText");
        }
        String cutReason = shot.getCutReason() == null ? "" : shot.getCutReason();
        // 这是反机械拆镜的契约防线；对话、句号或换行本身不能成为镜头存在的唯一理由。
        require(MECHANICAL_CUT_MARKERS.stream().noneMatch(cutReason::contains),
                "镜头不能使用说话人、句子或换行作为机械切镜理由");
        for (ChapterAdaptationSourceRange range : ranges) {
            boolean contained = beat.getSourceRanges().stream().anyMatch(beatRange ->
                    beatRange.getStart() <= range.getStart()
                            && beatRange.getEnd() >= range.getEnd()
                            && Objects.equals(
                                    range.getSourceText(),
                                    codePointSlice(
                                            beatRange.getSourceText(),
                                            range.getStart() - beatRange.getStart(),
                                            range.getEnd() - beatRange.getStart())));
            require(contained,
                    "镜头 " + shot.getShotKey() + " 的来源必须属于所属戏剧节拍");
        }
    }

    private static void validateOrderedRanges(
            List<ChapterAdaptationSourceRange> ranges, String label) {
        int previousEnd = -1;
        for (ChapterAdaptationSourceRange range : ranges) {
            require(range != null
                            && range.getStart() != null
                            && range.getEnd() != null
                            && range.getStart() >= 0
                            && range.getEnd() > range.getStart(),
                    label + "范围无效");
            require(range.getSourceText() != null
                            && range.getSourceText().codePointCount(0, range.getSourceText().length())
                                    == range.getEnd() - range.getStart(),
                    "来源范围长度与 sourceText 不一致");
            require(range.getStart() >= previousEnd, label + "必须按原文顺序排列且不能重叠");
            previousEnd = range.getEnd();
        }
    }

    private static void validateBoundaries(
            List<String> boundaries, List<String> orderedKeys, String label) {
        require(new HashSet<>(boundaries).size() == boundaries.size(), label + "不能重复");
        Set<String> allowed = orderedKeys.isEmpty()
                ? Set.of()
                : new HashSet<>(orderedKeys.subList(0, orderedKeys.size() - 1));
        require(allowed.containsAll(boundaries), label + "只能引用非末尾镜头");
        int previous = -1;
        for (String boundary : boundaries) {
            int position = orderedKeys.indexOf(boundary);
            require(position > previous, label + "必须按镜头顺序排列");
            previous = position;
        }
    }

    private static void validateFindings(
            List<CinematicReviewFinding> findings,
            List<CinematicSceneCandidate> scenes,
            List<DramaticBeatCandidate> beats,
            List<CinematicShotCandidate> shots) {
        Set<String> sceneKeys = scenes.stream()
                .map(CinematicSceneCandidate::getSceneKey)
                .collect(java.util.stream.Collectors.toSet());
        Set<String> beatKeys = beats.stream()
                .map(DramaticBeatCandidate::getBeatKey)
                .collect(java.util.stream.Collectors.toSet());
        Set<String> shotKeys = shots.stream()
                .map(CinematicShotCandidate::getShotKey)
                .collect(java.util.stream.Collectors.toSet());
        for (CinematicReviewFinding finding : findings) {
            String scopeKey = nullable(finding.getScopeKey());
            if (finding.getScope() == CinematicReviewFinding.ScopeEnum.PLAN) {
                require(scopeKey == null, "方案级审镜发现不能携带局部 Key");
                continue;
            }
            require(scopeKey != null, "局部审镜发现必须携带作用域 Key");
            Set<String> valid = switch (finding.getScope()) {
                case SCENE -> sceneKeys;
                case BEAT -> beatKeys;
                case SHOT -> shotKeys;
                case PLAN -> Set.of();
            };
            require(valid.contains(scopeKey), "审镜发现引用了方案之外的作用域 Key");
        }
    }

    private static CinematicSceneCandidate candidateScene(FormalCinematicScene scene) {
        return new CinematicSceneCandidate(
                scene.getBeats().stream().map(VideoAdaptationPlans::candidateBeat).toList(),
                scene.getChangeSummary(),
                scene.getLocationLabel(),
                scene.getObjective(),
                scene.getSceneKey(),
                scene.getTimeLabel(),
                scene.getTitle());
    }

    private static DramaticBeatCandidate candidateBeat(FormalDramaticBeat beat) {
        return new DramaticBeatCandidate(
                beat.getBeatKey(),
                beat.getCoverageGoals(),
                beat.getDramaticTurn(),
                beat.getShots().stream().map(VideoAdaptationPlans::candidateShot).toList(),
                beat.getSourceRanges(),
                beat.getTitle(),
                beat.getVisualStrategy());
    }

    private static CinematicShotCandidate candidateShot(FormalCinematicShot shot) {
        var result = new CinematicShotCandidate(
                shot.getAudienceGain(),
                CinematicShotCandidate.CameraAngleEnum.fromValue(shot.getCameraAngle().getValue()),
                CinematicShotCandidate.CameraMovementEnum.fromValue(
                        shot.getCameraMovement().getValue()),
                shot.getCutReason(),
                CinematicShotCandidate.NarrativePurposeEnum.fromValue(
                        shot.getNarrativePurpose().getValue()),
                shot.getShotKey(),
                CinematicShotCandidate.ShotScaleEnum.fromValue(shot.getShotScale().getValue()),
                shot.getSoundDesign(),
                shot.getSourceRanges(),
                CinematicShotCandidate.SourceRelationEnum.fromValue(
                        shot.getSourceRelation().getValue()),
                CinematicShotCandidate.SpeechModeEnum.fromValue(shot.getSpeechMode().getValue()),
                shot.getStoryFunction(),
                shot.getTimelineDurationMs(),
                shot.getTitle(),
                shot.getVisualIntent());
        result.setCoveredGoalKeys(list(shot.getCoveredGoalKeys()));
        String spoken = shot.getSpokenText();
        result.setSpokenText(spoken == null ? JsonNullable.of(null) : JsonNullable.of(spoken));
        return result;
    }

    private static Map<String, Object> sceneMap(CinematicSceneCandidate scene) {
        LinkedHashMap<String, Object> value = new LinkedHashMap<>();
        value.put("sceneKey", scene.getSceneKey());
        value.put("title", scene.getTitle());
        value.put("locationLabel", scene.getLocationLabel());
        value.put("timeLabel", scene.getTimeLabel());
        value.put("objective", scene.getObjective());
        value.put("changeSummary", scene.getChangeSummary());
        value.put("beats", scene.getBeats().stream().map(VideoAdaptationPlans::beatMap).toList());
        return value;
    }

    private static Map<String, Object> beatMap(DramaticBeatCandidate beat) {
        LinkedHashMap<String, Object> value = new LinkedHashMap<>();
        value.put("beatKey", beat.getBeatKey());
        value.put("title", beat.getTitle());
        value.put("dramaticTurn", beat.getDramaticTurn());
        value.put("visualStrategy", beat.getVisualStrategy());
        value.put("coverageGoals", beat.getCoverageGoals().stream()
                .map(goal -> Map.<String, Object>of(
                        "goalKey", goal.getGoalKey(),
                        "kind", goal.getKind().getValue(),
                        "priority", goal.getPriority().getValue(),
                        "description", goal.getDescription()))
                .toList());
        value.put("sourceRanges", beat.getSourceRanges().stream()
                .map(VideoAdaptationPlans::rangeMap)
                .toList());
        value.put("shots", beat.getShots().stream().map(VideoAdaptationPlans::shotMap).toList());
        return value;
    }

    private static Map<String, Object> shotMap(CinematicShotCandidate shot) {
        LinkedHashMap<String, Object> value = new LinkedHashMap<>();
        value.put("shotKey", shot.getShotKey());
        value.put("title", shot.getTitle());
        value.put("narrativePurpose", shot.getNarrativePurpose().getValue());
        value.put("storyFunction", shot.getStoryFunction());
        value.put("audienceGain", shot.getAudienceGain());
        value.put("coveredGoalKeys", list(shot.getCoveredGoalKeys()));
        value.put("sourceRelation", shot.getSourceRelation().getValue());
        value.put("shotScale", shot.getShotScale().getValue());
        value.put("cameraAngle", shot.getCameraAngle().getValue());
        value.put("cameraMovement", shot.getCameraMovement().getValue());
        value.put("visualIntent", shot.getVisualIntent());
        value.put("speechMode", shot.getSpeechMode().getValue());
        value.put("spokenText", nullable(shot.getSpokenText()));
        value.put("soundDesign", shot.getSoundDesign());
        value.put("cutReason", shot.getCutReason());
        value.put("timelineDurationMs", shot.getTimelineDurationMs());
        value.put("sourceRanges", list(shot.getSourceRanges()).stream()
                .map(VideoAdaptationPlans::rangeMap)
                .toList());
        return value;
    }

    private static Map<String, Object> rangeMap(ChapterAdaptationSourceRange range) {
        return Map.of(
                "start", range.getStart(),
                "end", range.getEnd(),
                "sourceText", range.getSourceText());
    }

    private static Map<String, Object> findingMap(CinematicReviewFinding finding) {
        LinkedHashMap<String, Object> value = new LinkedHashMap<>();
        value.put("severity", finding.getSeverity().getValue());
        value.put("scope", finding.getScope().getValue());
        value.put("scopeKey", nullable(finding.getScopeKey()));
        value.put("message", finding.getMessage());
        value.put("evidence", finding.getEvidence());
        value.put("suggestion", finding.getSuggestion());
        return value;
    }

    private static String codePointSlice(String source, int start, int end) {
        try {
            int count = source.codePointCount(0, source.length());
            if (start < 0 || end <= start || end > count) return null;
            int from = source.offsetByCodePoints(0, start);
            int to = source.offsetByCodePoints(0, end);
            return source.substring(from, to);
        } catch (RuntimeException exception) {
            return null;
        }
    }

    private static String key(String prefix, int number) {
        return prefix + "%02d".formatted(number);
    }

    private static <T> List<T> list(List<T> value) {
        return value == null ? List.of() : value;
    }

    private static String nullable(JsonNullable<String> value) {
        return value != null && value.isPresent() ? value.get() : null;
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new IllegalArgumentException(message);
    }

    private static ApiException sourceInvalid() {
        return new ApiException(
                409,
                "VIDEO_ADAPTATION_SOURCE_INVALID",
                "镜头方案包含与冻结章节不一致的来源范围");
    }
}
