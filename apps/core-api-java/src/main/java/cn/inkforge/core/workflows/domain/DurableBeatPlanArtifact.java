package cn.inkforge.core.workflows.domain;

import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** 章节规划只保存一次完整语义计划；来源、身份与详情由 Core 确定性重建。 */
public final class DurableBeatPlanArtifact {
    public static final String SCHEMA = "durable.beat-plan-artifact.v1";
    private static final Set<String> PLAN_FIELDS = Set.of("title", "summary", "chapterGoal",
            "sceneBeats", "mainPlotConnection", "chapterAcceptanceCriteria", "totalEstimatedWords", "beatCount");
    private static final Set<String> SCENE_FIELDS = Set.of("order", "goal", "conflict", "characters",
            "foreshadowingRefs", "estimatedWords", "acceptanceCriteria");

    private DurableBeatPlanArtifact() {}

    public static Stored create(String bundleId, String manifestHash, String chapterId,
            Map<String, Object> output, String stepId, String resultHash) {
        Map<String, Object> plan = validateOutput(output);
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("schema", SCHEMA);
        payload.put("kind", "beat_plan");
        payload.put("operation", "plan_chapter");
        payload.put("evidenceBundleId", text(bundleId, 512));
        payload.put("evidenceManifestSha256", hash(manifestHash));
        payload.put("chapterId", text(chapterId, 512));
        payload.put("plan", plan);
        payload.put("contentSha256", hash(output.get("contentSha256")));
        payload.put("generationStepId", text(stepId, 512));
        payload.put("generationResultHash", hash(resultHash));
        return new Stored(Collections.unmodifiableMap(payload), Map.of("schema", SCHEMA, "type", "beat_plan"));
    }

    /** Agent 可派生顺序和摘要哈希，但 Core 必须独立重算并拒绝任何差异。 */
    /** 校验模型章节计划的严格字段、顺序和数量边界并返回冻结副本。 */
    public static Map<String, Object> validateOutput(Map<String, Object> output) {
        Map<String, Object> plan = new LinkedHashMap<>(output);
        String expected = hash(plan.remove("contentSha256"));
        if (!PLAN_FIELDS.containsAll(plan.keySet())) throw invalid();
        text(plan.get("title"), 200);
        text(plan.get("summary"), 2000);
        text(plan.get("chapterGoal"), 1000);
        optionalText(plan, "mainPlotConnection", 1000, false);
        optionalText(plan, "chapterAcceptanceCriteria", 1000, false);
        optionalInteger(plan, "totalEstimatedWords");
        if (!(plan.get("sceneBeats") instanceof List<?> scenes) || scenes.isEmpty() || scenes.size() > 50) throw invalid();
        if (integer(plan.get("beatCount")) != scenes.size()) throw invalid();
        List<Map<String, Object>> validated = new ArrayList<>();
        for (int index = 0; index < scenes.size(); index++) {
            Map<String, Object> scene = object(scenes.get(index));
            if (!SCENE_FIELDS.containsAll(scene.keySet()) || integer(scene.get("order")) != index + 1) throw invalid();
            text(scene.get("goal"), 1000);
            optionalText(scene, "conflict", 1000, false);
            optionalText(scene, "acceptanceCriteria", 1000, true);
            optionalInteger(scene, "estimatedWords");
            if (scene.containsKey("characters") && scene.get("characters") == null) throw invalid();
            strings(scene, "characters", 100);
            strings(scene, "foreshadowingRefs", 200);
            validated.add(Collections.unmodifiableMap(scene));
        }
        plan.put("sceneBeats", List.copyOf(validated));
        if (!expected.equals(ExecutionCanonicalJson.sha256(plan))) throw invalid();
        return Collections.unmodifiableMap(plan);
    }

    public static Map<String, Object> output(Map<String, Object> stored) {
        Map<String, Object> output = object(stored.get("plan"));
        output.put("contentSha256", stored.get("contentSha256"));
        validateOutput(output);
        return Collections.unmodifiableMap(output);
    }

    /** 从冻结章节来源重新生成可采用计划及其审核差异。 */
    public static Materialized reconstruct(Map<String, Object> stored, Map<String, Object> storedDiff,
            String bundleId, String manifestHash, String chapterId) {
        try {
            if (!stored.keySet().equals(Set.of("schema", "kind", "operation", "evidenceBundleId", "evidenceManifestSha256",
                    "chapterId", "plan", "contentSha256", "generationStepId", "generationResultHash"))
                    || !SCHEMA.equals(stored.get("schema")) || !"beat_plan".equals(stored.get("kind"))
                    || !"plan_chapter".equals(stored.get("operation"))
                    || !bundleId.equals(stored.get("evidenceBundleId"))
                    || !manifestHash.equals(stored.get("evidenceManifestSha256"))
                    || !chapterId.equals(stored.get("chapterId"))
                    || !Map.of("schema", SCHEMA, "type", "beat_plan").equals(storedDiff)) throw invalid();
            text(stored.get("generationStepId"), 512);
            hash(stored.get("generationResultHash"));
            hash(manifestHash);
            Map<String, Object> plan = validateOutput(output(stored));
            Map<String, Object> payload = Map.of("kind", "beat_plan", "operation", "plan_chapter",
                    "chapterId", chapterId, "beatPlan", plan, "contentSha256", stored.get("contentSha256"));
            return new Materialized(payload, Map.of("type", "beat_plan", "after", plan));
        } catch (IllegalArgumentException | NullPointerException exception) {
            throw new ApiException(409, "ARTIFACT_REVISION_INTEGRITY_ERROR",
                    "待审核章节计划的不可变修订或 Evidence 无法通过完整性校验");
        }
    }

    public static boolean isStored(Map<String, Object> payload) { return SCHEMA.equals(payload.get("schema")); }

    private static Map<String, Object> object(Object value) {
        if (!(value instanceof Map<?, ?> map)) throw invalid();
        Map<String, Object> result = new LinkedHashMap<>();
        map.forEach((key, item) -> {
            if (!(key instanceof String text)) throw invalid();
            result.put(text, item);
        });
        return result;
    }

    private static String text(Object value, int maximum) {
        if (!(value instanceof String text) || text.isEmpty()
                || text.codePointCount(0, text.length()) > maximum
                || text.codePoints().allMatch(c -> Character.isWhitespace(c) || Character.isSpaceChar(c) || c == 0x85 || c == 0xFEFF)) throw invalid();
        return text;
    }

    private static String hash(Object value) {
        if (!(value instanceof String text) || !text.matches("[0-9a-f]{64}")) throw invalid();
        return text;
    }

    private static void optionalText(Map<String, Object> map, String key, int max, boolean nonBlank) {
        Object value = map.get(key);
        if (value == null) return;
        if (!(value instanceof String text) || text.codePointCount(0, text.length()) > max) throw invalid();
        if (nonBlank) text(text, max);
    }

    private static int integer(Object value) {
        if (!(value instanceof Integer || value instanceof Long || value instanceof Short
                || value instanceof Byte || value instanceof BigInteger)) throw invalid();
        BigInteger number = new BigInteger(value.toString());
        if (number.signum() < 0 || number.compareTo(BigInteger.valueOf(Integer.MAX_VALUE)) > 0) throw invalid();
        return number.intValue();
    }

    private static void optionalInteger(Map<String, Object> map, String key) {
        if (map.get(key) != null) integer(map.get(key));
    }

    private static void strings(Map<String, Object> map, String key, int maximum) {
        Object value = map.get(key);
        if (value == null) return;
        if (!(value instanceof List<?> list) || list.size() > 50) throw invalid();
        list.forEach(item -> text(item, maximum));
        map.put(key, List.copyOf(list));
    }

    private static IllegalArgumentException invalid() { return new IllegalArgumentException("章节计划不符合严格语义与完整性契约"); }
    public record Stored(Map<String, Object> payload, Map<String, Object> diff) {}
    public record Materialized(Map<String, Object> payload, Map<String, Object> diff) {}
}
