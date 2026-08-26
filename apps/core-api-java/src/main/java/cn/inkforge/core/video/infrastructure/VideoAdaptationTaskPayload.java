package cn.inkforge.core.video.infrastructure;

import cn.inkforge.contracts.api.ChapterAdaptationPlanCandidate;
import cn.inkforge.contracts.api.ShotVisualReferenceSnapshot;
import cn.inkforge.core.video.domain.VideoAdaptationPlans;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/** 章节改编耐久任务的严格判别载荷；同时兼容 Python 已落库的同版本 JSON。 */
final class VideoAdaptationTaskPayload {

    static final String PLAN_WORKFLOW = "chapter_cinematic_adaptation_v2";
    static final String PROMPT_WORKFLOW = "chapter_shot_prompt_v2";
    private static final String ROUTE = "responses_json_schema_v1";
    private static final String MODEL = "deepseek-v4-flash";

    private final ObjectMapper json;
    private final JsonNode root;
    private final String workflow;

    private VideoAdaptationTaskPayload(ObjectMapper json, JsonNode root, String workflow) {
        this.json = json;
        this.root = root;
        this.workflow = workflow;
    }

    static VideoAdaptationTaskPayload parse(ObjectMapper json, String serialized) {
        Objects.requireNonNull(json);
        try {
            JsonNode root = json.readTree(serialized);
            require(root != null && root.isObject(), "章节改编任务载荷必须是对象");
            String workflow = text(root, "workflow");
            require(PLAN_WORKFLOW.equals(workflow) || PROMPT_WORKFLOW.equals(workflow),
                    "章节改编任务工作流无效");
            var payload = new VideoAdaptationTaskPayload(json, root, workflow);
            payload.validate();
            return payload;
        } catch (IllegalArgumentException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw new IllegalArgumentException("章节改编任务载荷不是合法 JSON", exception);
        }
    }

    static String plan(
            ObjectMapper json,
            String adaptationId,
            String projectId,
            String chapterId,
            String chapterTitle,
            String sourceText,
            String sourceHash,
            String ratio,
            String targetLanguage,
            String pacingPreset,
            int targetEpisodeSeconds,
            String baseShotPlanVersionId,
            ChapterAdaptationPlanCandidate baseShotPlan,
            String revisionBrief) {
        LinkedHashMap<String, Object> value = new LinkedHashMap<>();
        value.put("workflow", PLAN_WORKFLOW);
        value.put("adaptationId", adaptationId);
        value.put("projectId", projectId);
        value.put("chapterId", chapterId);
        value.put("chapterTitle", chapterTitle);
        value.put("sourceText", sourceText);
        value.put("sourceHash", sourceHash);
        value.put("ratio", ratio);
        value.put("targetLanguage", targetLanguage);
        value.put("pacingPreset", pacingPreset);
        value.put("targetEpisodeSeconds", targetEpisodeSeconds);
        value.put("baseShotPlanVersionId", baseShotPlanVersionId);
        value.put(
                "baseShotPlan",
                baseShotPlan == null ? null : VideoAdaptationPlans.candidateMap(baseShotPlan));
        value.put("revisionBrief", revisionBrief);
        value.put("planningRoute", ROUTE);
        value.put("planningModel", MODEL);
        String serialized = json.writeValueAsString(value);
        parse(json, serialized);
        return serialized;
    }

    static String prompt(
            ObjectMapper json,
            String adaptationId,
            String projectId,
            String shotPlanVersionId,
            String sourceText,
            String sourceHash,
            ChapterAdaptationPlanCandidate shotPlan,
            List<String> episodeBreakAfterShotKeys,
            List<String> targetShotKeys,
            String ratio,
            String targetLanguage,
            Map<String, Object> settingSnapshot,
            List<VisualReferenceBundle> visualReferenceBundles) {
        LinkedHashMap<String, Object> value = new LinkedHashMap<>();
        value.put("workflow", PROMPT_WORKFLOW);
        value.put("adaptationId", adaptationId);
        value.put("projectId", projectId);
        value.put("shotPlanVersionId", shotPlanVersionId);
        value.put("sourceText", sourceText);
        value.put("sourceHash", sourceHash);
        value.put("shotPlan", VideoAdaptationPlans.candidateMap(shotPlan));
        value.put("episodeBreakAfterShotKeys", List.copyOf(episodeBreakAfterShotKeys));
        value.put("targetShotKeys", List.copyOf(targetShotKeys));
        value.put("ratio", ratio);
        value.put("targetLanguage", targetLanguage);
        value.put("settingSnapshot", settingSnapshot);
        value.put("visualReferenceBundles", visualReferenceBundles.stream()
                .map(VideoAdaptationTaskPayload::bundleMap)
                .toList());
        value.put("planningRoute", ROUTE);
        value.put("planningModel", MODEL);
        String serialized = json.writeValueAsString(value);
        parse(json, serialized);
        return serialized;
    }

    String workflow() {
        return workflow;
    }

    boolean isPlan() {
        return PLAN_WORKFLOW.equals(workflow);
    }

    boolean isPrompt() {
        return PROMPT_WORKFLOW.equals(workflow);
    }

    String adaptationId() {
        return text(root, "adaptationId");
    }

    String projectId() {
        return text(root, "projectId");
    }

    String sourceHash() {
        return text(root, "sourceHash");
    }

    String baseShotPlanVersionId() {
        return nullableText(root, isPlan() ? "baseShotPlanVersionId" : "shotPlanVersionId");
    }

    String pacingPreset() {
        return isPlan() ? text(root, "pacingPreset") : null;
    }

    int targetEpisodeSeconds() {
        return isPlan() ? integer(root, "targetEpisodeSeconds") : 0;
    }

    String revisionBrief() {
        return isPlan() ? nullableText(root, "revisionBrief") : null;
    }

    List<String> targetShotKeys() {
        return isPrompt() ? strings(root.get("targetShotKeys"), "逐镜提示词目标无效") : List.of();
    }

    String ratio() {
        return text(root, "ratio");
    }

    ChapterAdaptationPlanCandidate shotPlan() {
        JsonNode value = root.get(isPlan() ? "baseShotPlan" : "shotPlan");
        if (value == null || value.isNull()) return null;
        try {
            ChapterAdaptationPlanCandidate plan =
                    json.convertValue(value, ChapterAdaptationPlanCandidate.class);
            VideoAdaptationPlans.validateCandidate(plan);
            return plan;
        } catch (RuntimeException exception) {
            throw new IllegalArgumentException("章节改编任务中的镜头方案无效", exception);
        }
    }

    Map<String, List<ShotVisualReferenceSnapshot>> visualReferencesByShot() {
        if (!isPrompt()) return Map.of();
        JsonNode bundles = root.get("visualReferenceBundles");
        if (bundles == null || bundles.isNull()) return Map.of();
        require(bundles.isArray(), "逐镜视觉参考集合无效");
        LinkedHashMap<String, List<ShotVisualReferenceSnapshot>> result = new LinkedHashMap<>();
        for (JsonNode bundle : bundles) {
            String shotKey = text(bundle, "shotKey");
            JsonNode references = bundle.get("references");
            require(references != null && references.isArray(), "逐镜视觉参考集合无效");
            List<ShotVisualReferenceSnapshot> snapshots = new ArrayList<>();
            for (JsonNode reference : references) {
                snapshots.add(json.convertValue(reference, ShotVisualReferenceSnapshot.class));
            }
            require(result.putIfAbsent(shotKey, List.copyOf(snapshots)) == null,
                    "逐镜视觉参考不能重复镜头");
        }
        return result;
    }

    Map<String, Object> agentPayload() {
        return json.convertValue(root, new tools.jackson.core.type.TypeReference<Map<String, Object>>() {});
    }

    private void validate() {
        String sourceText = text(root, "sourceText");
        require(VideoAdaptationPlans.sourceHash(sourceText).equals(text(root, "sourceHash")),
                isPlan() ? "章节改编来源哈希不一致" : "逐镜提示词来源哈希不一致");
        text(root, "adaptationId");
        text(root, "projectId");
        text(root, "ratio");
        text(root, "targetLanguage");
        if (isPlan()) {
            text(root, "chapterId");
            text(root, "chapterTitle");
            String pacing = text(root, "pacingPreset");
            require(Set.of("short_drama", "cinematic", "dialogue_driven").contains(pacing),
                    "章节改编节奏预设无效");
            require(Set.of(60, 90, 120).contains(integer(root, "targetEpisodeSeconds")),
                    "章节改编目标分集时长无效");
            String baseId = nullableText(root, "baseShotPlanVersionId");
            ChapterAdaptationPlanCandidate basePlan = shotPlan();
            require((baseId == null) == (basePlan == null),
                    "正式方案基线 ID 与内容必须同时提供");
            String brief = nullableText(root, "revisionBrief");
            require(brief == null || basePlan != null, "没有正式方案基线时不能提交修订重点");
            if (basePlan != null) {
                require(basePlan.getAdaptationId().equals(adaptationId())
                                && basePlan.getSourceHash().equals(sourceHash()),
                        "正式方案基线与章节改编来源不一致");
            }
            return;
        }
        text(root, "shotPlanVersionId");
        ChapterAdaptationPlanCandidate plan = shotPlan();
        require(plan != null && plan.getSourceHash().equals(sourceHash()),
                "逐镜提示词方案与来源不一致");
        List<String> targets = targetShotKeys();
        require(!targets.isEmpty() && targets.size() <= 120, "逐镜提示词目标数量无效");
        require(new HashSet<>(targets).size() == targets.size(), "逐镜提示词目标不能重复");
        Set<String> planKeys = new HashSet<>();
        plan.getScenes().forEach(scene -> scene.getBeats().forEach(beat ->
                beat.getShots().forEach(shot -> planKeys.add(shot.getShotKey()))));
        require(planKeys.containsAll(targets), "逐镜提示词引用了方案之外的镜头");
        Map<String, List<ShotVisualReferenceSnapshot>> bundles = visualReferencesByShot();
        require(bundles.isEmpty() || new ArrayList<>(bundles.keySet()).equals(targets),
                "视觉参考集合必须按目标镜头顺序完整冻结");
    }

    private static Map<String, Object> bundleMap(VisualReferenceBundle bundle) {
        return Map.of(
                "shotKey", bundle.shotKey(),
                "references", bundle.references().stream()
                        .map(VideoAdaptationTaskPayload::referenceMap)
                        .toList());
    }

    private static Map<String, Object> referenceMap(ShotVisualReferenceSnapshot reference) {
        LinkedHashMap<String, Object> value = new LinkedHashMap<>();
        value.put("canonVersionId", reference.getCanonVersionId());
        value.put("assetId", reference.getAssetId());
        value.put("assetSha256", reference.getAssetSha256());
        value.put("settingKind", reference.getSettingKind().getValue());
        value.put("settingId", reference.getSettingId());
        value.put("settingName", reference.getSettingName());
        value.put("duty", reference.getDuty().getValue());
        value.put("variantKey", reference.getVariantKey());
        value.put("label", reference.getLabel());
        value.put("includeFeatures", list(reference.getIncludeFeatures()));
        value.put("excludeFeatures", list(reference.getExcludeFeatures()));
        value.put("strength", reference.getStrength());
        return value;
    }

    private static String text(JsonNode node, String field) {
        JsonNode value = node == null ? null : node.get(field);
        require(value != null && value.isString() && !value.asString().isEmpty(),
                "章节改编任务字段无效：" + field);
        return value.asString();
    }

    private static String nullableText(JsonNode node, String field) {
        JsonNode value = node == null ? null : node.get(field);
        if (value == null || value.isNull()) return null;
        require(value.isString() && !value.asString().isEmpty(),
                "章节改编任务字段无效：" + field);
        return value.asString();
    }

    private static int integer(JsonNode node, String field) {
        JsonNode value = node == null ? null : node.get(field);
        require(value != null && value.isInt(), "章节改编任务字段无效：" + field);
        return value.asInt();
    }

    private static List<String> strings(JsonNode value, String message) {
        require(value != null && value.isArray(), message);
        List<String> result = new ArrayList<>();
        for (JsonNode item : value) {
            require(item.isString(), message);
            result.add(item.asString());
        }
        return List.copyOf(result);
    }

    private static <T> List<T> list(List<T> value) {
        return value == null ? List.of() : value;
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new IllegalArgumentException(message);
    }

    record VisualReferenceBundle(
            String shotKey, List<ShotVisualReferenceSnapshot> references) {

        VisualReferenceBundle {
            if (shotKey == null || shotKey.isEmpty()) {
                throw new IllegalArgumentException("视觉参考镜头 Key 不能为空");
            }
            references = List.copyOf(references);
        }
    }
}
