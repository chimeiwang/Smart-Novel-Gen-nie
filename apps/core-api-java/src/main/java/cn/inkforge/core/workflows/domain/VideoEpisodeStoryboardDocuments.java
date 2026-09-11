package cn.inkforge.core.workflows.domain;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/** Core 重验正式剧本、稳定镜头、选区和参考事实；范围外镜头始终复制冻结稿。 */
public final class VideoEpisodeStoryboardDocuments {
    private static final Set<String> FRAMINGS = Set.of(
            "extreme_wide", "wide", "medium", "close_up", "detail", "over_shoulder", "pov");
    private static final Set<String> CAMERA_MOVEMENTS = Set.of(
            "static", "pan", "tilt", "dolly", "truck", "crane", "handheld", "orbit", "zoom");
    private static final Set<String> LINEAGE_RELATIONS = Set.of(
            "replacement", "copy", "split", "merge");

    private VideoEpisodeStoryboardDocuments() {}

    public static Map<String, Object> merge(
            Map<String, Object> context, Map<String, Object> proposal) {
        Map<String, Object> draft = object(context.get("draft"));
        if (!"video-episode-storyboard/1.0".equals(draft.get("schemaVersion"))) {
            throw invalid("冻结分镜工作稿版本无效");
        }
        List<?> frozenShots = list(draft.get("shots"));
        if (frozenShots.size() > 300) throw invalid("冻结分镜镜头超过上限");

        List<String> stableOrder = strings(context.get("stableShotIds"));
        if (stableOrder.size() != new HashSet<>(stableOrder).size()) {
            throw invalid("冻结稳定镜头身份重复");
        }
        Map<String, Map<String, Object>> frozenById = new LinkedHashMap<>();
        List<String> actualOrder = new ArrayList<>();
        for (Object raw : frozenShots) {
            Map<String, Object> shot = object(raw);
            String id = text(shot.get("id"));
            if (shot.get("tempKey") != null || frozenById.put(id, shot) != null) {
                throw invalid("冻结工作稿必须只包含唯一稳定镜头");
            }
            actualOrder.add(id);
        }
        if (!stableOrder.equals(actualOrder)) {
            throw invalid("冻结稳定镜头清单与工作稿顺序不一致");
        }

        List<String> selected = strings(context.get("selectedShotIds"));
        if (selected.size() != new HashSet<>(selected).size()
                || !frozenById.keySet().containsAll(selected)) {
            throw invalid("局部分镜范围不是冻结稳定镜头的唯一子集");
        }
        String operation = text(context.get("operation"));
        boolean revise = "episode_storyboard_revise".equals(operation);
        if (!(revise || "episode_storyboard_generate".equals(operation))
                || revise == selected.isEmpty()) {
            throw invalid("分镜起草与局部修订范围不匹配");
        }

        List<?> candidateShots = list(proposal.get("shots"));
        if (candidateShots.isEmpty() || candidateShots.size() > 300) {
            throw invalid("分镜候选必须包含 1 至 300 个镜头");
        }
        List<Map<String, Object>> proposals = new ArrayList<>();
        if (revise) {
            Map<String, Map<String, Object>> replacements = new HashMap<>();
            for (Object raw : candidateShots) {
                Map<String, Object> shot = object(raw);
                String id = text(shot.get("id"));
                if (shot.get("tempKey") != null || replacements.put(id, shot) != null) {
                    throw invalid("局部分镜修订只能返回唯一稳定镜头");
                }
            }
            if (!replacements.keySet().equals(new HashSet<>(selected))) {
                throw invalid("局部分镜候选必须恰好包含全部选中镜头");
            }
            for (String id : stableOrder) {
                proposals.add(replacements.getOrDefault(id, proposalFromFrozen(frozenById.get(id))));
            }
        } else {
            for (Object raw : candidateShots) proposals.add(object(raw));
        }

        Map<String, Set<String>> script = scriptNodes(object(context.get("script")));
        Map<String, Map<String, Object>> references = new HashMap<>();
        for (Object raw : list(context.get("availableReferences"))) {
            Map<String, Object> reference = object(raw);
            String id = text(reference.get("canonVersionId"));
            if (references.put(id, reference) != null) {
                throw invalid("冻结视觉参考版本重复");
            }
        }
        if (references.isEmpty()) throw invalid("分镜候选缺少冻结视觉参考");
        Map<String, Object> defaults = object(context.get("productionDefaults"));

        Set<String> identities = new HashSet<>();
        List<Map<String, Object>> normalized = new ArrayList<>();
        for (Map<String, Object> shot : proposals) {
            String id = nullableText(shot.get("id"));
            String temporary = nullableText(shot.get("tempKey"));
            if ((id == null) == (temporary == null)) {
                throw invalid("镜头必须且只能提供稳定 id 或 tempKey");
            }
            String identity = id == null ? temporary : id;
            if (!identities.add(identity)) throw invalid("候选镜头身份重复");
            List<Map<String, Object>> lineage = lineage(shot.get("lineage"), frozenById.keySet());
            if (id != null) {
                Map<String, Object> frozen = frozenById.get(id);
                if (frozen == null) throw invalid("模型不能分配新的稳定镜头身份");
                if (!Objects.equals(list(frozen.get("lineage")), lineage)) {
                    throw invalid("模型不能修改稳定镜头的沿袭事实");
                }
            } else if (revise) {
                throw invalid("局部分镜修订不能创建临时镜头");
            }

            String sceneId = text(shot.get("scriptSceneId"));
            Set<String> lines = script.get(sceneId);
            List<String> lineIds = strings(shot.get("scriptLineIds"));
            if (lines == null || lineIds.size() != new HashSet<>(lineIds).size()
                    || !lines.containsAll(lineIds)) {
                throw invalid("镜头必须绑定正式剧本中的确切场次和台词");
            }
            String framing = text(shot.get("framing"));
            String camera = text(shot.get("cameraMovement"));
            if (!FRAMINGS.contains(framing) || !CAMERA_MOVEMENTS.contains(camera)) {
                throw invalid("镜头景别或机位运动无效");
            }
            long durationMs = number(shot.get("durationMs"));
            Map<String, Object> intent = object(shot.get("productionIntent"));
            Map<String, Object> normalizedIntent = productionIntent(
                    intent, defaults, references, durationMs);

            Map<String, Object> result = new LinkedHashMap<>();
            result.put("id", id);
            result.put("tempKey", temporary);
            result.put("lineage", lineage);
            result.put("scriptSceneId", sceneId);
            result.put("scriptLineIds", lineIds);
            result.put("title", text(shot.get("title")));
            result.put("action", text(shot.get("action")));
            result.put("framing", framing);
            result.put("cameraMovement", camera);
            result.put("durationMs", durationMs);
            result.put("productionIntent", normalizedIntent);
            normalized.add(java.util.Collections.unmodifiableMap(result));
        }
        Map<String, Object> document = new LinkedHashMap<>();
        document.put("schemaVersion", "video-episode-storyboard/1.0");
        document.put("shots", List.copyOf(normalized));
        return java.util.Collections.unmodifiableMap(document);
    }

    /** 审片问题只能引用合并后真实镜头或正式剧本场次，不能制造不存在的定位。 */
    public static void validateReview(
            Map<String, Object> context,
            Map<String, Object> document,
            Map<String, Object> review) {
        Set<String> shots = new HashSet<>();
        for (Object raw : list(document.get("shots"))) {
            Map<String, Object> shot = object(raw);
            shots.add(text(shot.get("id") == null ? shot.get("tempKey") : shot.get("id")));
        }
        Set<String> scenes = scriptNodes(object(context.get("script"))).keySet();
        for (Object raw : list(review.get("findings"))) {
            Map<String, Object> finding = object(raw);
            String shotId = nullableText(finding.get("shotId"));
            String sceneId = nullableText(finding.get("scriptSceneId"));
            if ((shotId != null && !shots.contains(shotId))
                    || (sceneId != null && !scenes.contains(sceneId))) {
                throw invalid("审片问题引用不存在的镜头或正式剧本场次");
            }
        }
    }

    private static Map<String, Object> productionIntent(
            Map<String, Object> intent,
            Map<String, Object> defaults,
            Map<String, Map<String, Object>> available,
            long durationMs) {
        for (String key : List.of(
                "provider", "model", "generationMode", "executionMode", "feeConfirmed",
                "ratio", "resolution", "generateAudio", "watermark", "outputFormat")) {
            if (!Objects.equals(intent.get(key), defaults.get(key))) {
                throw invalid("模型不能改变 Core 冻结的供应商执行参数或费用语义");
            }
        }
        if (!"simulated".equals(intent.get("executionMode"))
                || !Boolean.FALSE.equals(intent.get("feeConfirmed"))) {
            throw invalid("AI 分镜候选不能声明 live 或确认供应商费用");
        }
        long duration = number(intent.get("durationSeconds"));
        if (duration < 4 || duration > 12 || durationMs != duration * 1_000) {
            throw invalid("镜头时长必须为 4 至 12 秒且与毫秒值一致");
        }
        List<?> choices = list(intent.get("references"));
        if (choices.isEmpty() || choices.size() > 20) {
            throw invalid("镜头必须选择 1 至 20 份冻结视觉参考");
        }
        Set<String> selected = new LinkedHashSet<>();
        List<Map<String, Object>> references = new ArrayList<>();
        int ordinal = 0;
        for (Object raw : choices) {
            Map<String, Object> choice = object(raw);
            String canonVersionId = text(choice.get("canonVersionId"));
            Map<String, Object> evidence = available.get(canonVersionId);
            if (evidence == null || !selected.add(canonVersionId)) {
                throw invalid("镜头引用了未冻结或重复的视觉版本");
            }
            long strength = choice.get("strength") == null
                    ? number(evidence.get("defaultStrength"))
                    : number(choice.get("strength"));
            if (strength < 1 || strength > 100) throw invalid("视觉参考强度无效");
            Map<String, Object> snapshot = new LinkedHashMap<>();
            snapshot.put("ordinal", ++ordinal);
            snapshot.put("canonVersionId", canonVersionId);
            snapshot.put("canonContentHash", text(evidence.get("canonContentHash")));
            snapshot.put("assetId", text(evidence.get("assetId")));
            snapshot.put("sha256", text(evidence.get("sha256")));
            snapshot.put("mimeType", text(evidence.get("mimeType")));
            snapshot.put("duty", text(evidence.get("duty")));
            snapshot.put("strength", strength);
            references.add(java.util.Collections.unmodifiableMap(snapshot));
        }
        Map<String, Object> result = new LinkedHashMap<>(defaults);
        result.put("prompt", text(intent.get("prompt")));
        result.put("durationSeconds", duration);
        result.put("references", List.copyOf(references));
        return java.util.Collections.unmodifiableMap(result);
    }

    private static List<Map<String, Object>> lineage(Object raw, Set<String> stable) {
        List<?> values = list(raw);
        if (values.size() > 20) throw invalid("镜头沿袭超过上限");
        List<Map<String, Object>> result = new ArrayList<>();
        Set<String> sources = new HashSet<>();
        Set<String> relations = new HashSet<>();
        for (Object value : values) {
            Map<String, Object> item = object(value);
            String source = text(item.get("sourceShotId"));
            String relation = text(item.get("relation"));
            if (!stable.contains(source) || !sources.add(source)
                    || !LINEAGE_RELATIONS.contains(relation)) {
                throw invalid("镜头沿袭必须唯一引用冻结稳定镜头且关系有效");
            }
            relations.add(relation);
            result.add(Map.of("sourceShotId", source, "relation", relation));
        }
        if (relations.size() > 1
                || (relations.contains("merge") && result.size() < 2)
                || (!relations.contains("merge") && result.size() > 1)) {
            throw invalid("替换、复制和拆分各有一个来源，合并至少有两个来源");
        }
        return List.copyOf(result);
    }

    private static Map<String, Set<String>> scriptNodes(Map<String, Object> document) {
        if (!"video-episode-script/1.0".equals(document.get("schemaVersion"))) {
            throw invalid("正式剧本版本无效");
        }
        Map<String, Set<String>> result = new LinkedHashMap<>();
        for (Object raw : list(document.get("scenes"))) {
            Map<String, Object> scene = object(raw);
            String id = text(scene.get("id"));
            if (scene.get("tempKey") != null || result.containsKey(id)) {
                throw invalid("正式剧本场次身份无效");
            }
            Set<String> lines = new HashSet<>();
            for (Object lineRaw : list(scene.get("lines"))) {
                Map<String, Object> line = object(lineRaw);
                String lineId = text(line.get("id"));
                if (line.get("tempKey") != null || !lines.add(lineId)) {
                    throw invalid("正式剧本台词身份无效");
                }
            }
            result.put(id, Set.copyOf(lines));
        }
        if (result.isEmpty()) throw invalid("正式剧本不能没有场次");
        return java.util.Collections.unmodifiableMap(result);
    }

    private static Map<String, Object> proposalFromFrozen(Map<String, Object> frozen) {
        Map<String, Object> result = new LinkedHashMap<>(frozen);
        Map<String, Object> intent = new LinkedHashMap<>(object(frozen.get("productionIntent")));
        List<Map<String, Object>> choices = new ArrayList<>();
        for (Object raw : list(intent.get("references"))) {
            Map<String, Object> reference = object(raw);
            choices.add(Map.of(
                    "canonVersionId", text(reference.get("canonVersionId")),
                    "strength", number(reference.get("strength"))));
        }
        intent.put("references", List.copyOf(choices));
        result.put("productionIntent", java.util.Collections.unmodifiableMap(intent));
        return java.util.Collections.unmodifiableMap(result);
    }

    @SuppressWarnings("unchecked")
    static Map<String, Object> object(Object value) {
        if (!(value instanceof Map<?, ?> map)
                || map.keySet().stream().anyMatch(key -> !(key instanceof String))) {
            throw invalid("分镜对象形状无效");
        }
        return (Map<String, Object>) map;
    }

    static List<?> list(Object value) {
        if (!(value instanceof List<?> list)) throw invalid("分镜列表形状无效");
        return list;
    }

    static List<String> strings(Object value) {
        List<String> result = new ArrayList<>();
        for (Object item : list(value)) result.add(text(item));
        return List.copyOf(result);
    }

    static String text(Object value) {
        if (!(value instanceof String text) || text.isBlank()) {
            throw invalid("分镜文本或身份缺失");
        }
        return text;
    }

    static String nullableText(Object value) {
        return value == null ? null : text(value);
    }

    static long number(Object value) {
        if (!(value instanceof Number number)) throw invalid("分镜数值缺失");
        return number.longValue();
    }

    static IllegalArgumentException invalid(String message) {
        return new IllegalArgumentException(message);
    }
}
