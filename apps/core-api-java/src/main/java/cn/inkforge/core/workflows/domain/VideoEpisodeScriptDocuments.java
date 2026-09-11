package cn.inkforge.core.workflows.domain;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/** 在 Core 重验模型的身份、来源和修订权限；范围外场次始终复制冻结稿。 */
public final class VideoEpisodeScriptDocuments {
    private VideoEpisodeScriptDocuments() {}

    public static Map<String, Object> merge(Map<String, Object> context, Map<String, Object> proposal) {
        Map<String, Object> draft = object(context.get("draft"));
        List<?> selected = list(context.get("selectedSceneIds"));
        if (("episode_script_revise".equals(context.get("operation"))) == selected.isEmpty()) {
            throw invalid("修订必须限定场次，起草不能携带局部范围");
        }
        List<?> proposedScenes = list(proposal.get("scenes"));
        if (proposedScenes.isEmpty()) throw invalid("剧本候选不能没有场次");
        Map<String, Object> document = new LinkedHashMap<>();
        if (!selected.isEmpty()) {
            if (proposal.get("overview") != null || proposal.get("endingStates") != null || proposal.get("dependencies") != null) {
                throw invalid("局部修订不能改变概览、结尾状态或承接关系");
            }
            Map<String, Object> replacements = new LinkedHashMap<>();
            for (Object raw : proposedScenes) {
                Map<String, Object> scene = object(raw);
                if (!(scene.get("id") instanceof String id) || replacements.put(id, scene) != null) {
                    throw invalid("局部修订必须保留每个选中场次身份");
                }
            }
            if (!replacements.keySet().equals(new HashSet<>(selected))) throw invalid("局部修订范围不匹配");
            document.putAll(draft);
            List<Object> scenes = new ArrayList<>();
            for (Object raw : list(draft.get("scenes"))) {
                var scene = object(raw);
                scenes.add(replacements.getOrDefault(scene.get("id"), raw));
            }
            document.put("scenes", scenes);
        } else {
            if (proposal.get("overview") == null || proposal.get("endingStates") == null || proposal.get("dependencies") == null) {
                throw invalid("完整剧本缺少概览、结尾状态或承接关系");
            }
            document.put("schemaVersion", "video-episode-script/1.0");
            document.putAll(proposal);
        }
        Set<String> oldScenes = new HashSet<>();
        Map<String, String> oldLineParents = new HashMap<>();
        for (Object raw : list(draft.get("scenes"))) {
            var scene = object(raw);
            String id = text(scene.get("id"));
            oldScenes.add(id);
            for (Object line : list(scene.get("lines"))) oldLineParents.put(text(object(line).get("id")), id);
        }
        Set<String> characters = new HashSet<>();
        for (Object character : list(context.get("characters"))) characters.add(text(object(character).get("id")));
        Map<String, List<?>> sourceRanges = new HashMap<>();
        for (Object source : list(context.get("sources"))) {
            var item = object(source);
            sourceRanges.put(text(item.get("sourceSnapshotId")), list(item.get("selectedRanges")));
        }
        Set<String> identities = new HashSet<>();
        Map<String, Set<String>> sceneLines = new HashMap<>();
        for (Object raw : list(document.get("scenes"))) {
            Map<String, Object> scene = object(raw);
            String sceneIdentity = identity(scene, identities);
            if (scene.get("id") != null && !oldScenes.contains(scene.get("id"))) throw invalid("模型不能创建稳定场次身份");
            if (!characters.containsAll(list(scene.get("characterIds")))) throw invalid("未知角色引用");
            Set<String> lines = new HashSet<>();
            sceneLines.put(sceneIdentity, lines);
            for (Object lineRaw : list(scene.get("lines"))) {
                var line = object(lineRaw);
                lines.add(identity(line, identities));
                if (line.get("id") != null && (!oldLineParents.containsKey(line.get("id"))
                        || !Objects.equals(scene.get("id"), oldLineParents.get(line.get("id"))))) {
                    throw invalid("模型不能创建或跨场挪用稳定台词身份");
                }
                String kind = text(line.get("kind"));
                Object speaker = line.get("speakerId");
                if (("dialogue".equals(kind) && speaker == null) || ("action".equals(kind) && speaker != null)
                        || (speaker != null && !characters.contains(speaker))) throw invalid("说话人绑定无效");
                for (Object refRaw : list(line.get("sourceRefs"))) {
                    var ref = object(refRaw);
                    long start = number(ref.get("start"));
                    long end = number(ref.get("end"));
                    List<?> ranges = sourceRanges.get(text(ref.get("sourceSnapshotId")));
                    if (start < 0 || start >= end || ranges == null || ranges.stream().noneMatch(range -> {
                        var part = object(range);
                        return number(part.get("start")) <= start && number(part.get("end")) >= end;
                    })) throw invalid("来源锚点超出已选择片段");
                }
            }
        }
        Set<String> stateKeys = new HashSet<>();
        for (Object state : list(document.get("endingStates"))) {
            if (!stateKeys.add(text(object(state).get("key")))) throw invalid("结尾状态身份重复");
        }
        Set<List<String>> allowedDependencies = new HashSet<>();
        for (Object stateRaw : list(context.get("inheritedStates"))) {
            var state = object(stateRaw);
            allowedDependencies.add(List.of(text(state.get("episodeId")), text(state.get("scriptVersionId")),
                    text(object(state.get("state")).get("key"))));
        }
        for (Object dependencyRaw : list(document.get("dependencies"))) {
            var dependency = object(dependencyRaw);
            Set<String> lines = sceneLines.get(text(dependency.get("consumerSceneId")));
            if (lines == null || (dependency.get("consumerLineId") != null && !lines.contains(dependency.get("consumerLineId")))
                    || !allowedDependencies.contains(List.of(text(dependency.get("producerEpisodeId")),
                    text(dependency.get("producerScriptVersionId")), text(dependency.get("producerStateKey"))))) {
                throw invalid("跨集承接未绑定冻结正式状态或当前剧本节点");
            }
        }
        return java.util.Collections.unmodifiableMap(document);
    }

    /** 问题定位只能引用合并后的真实节点，模型不能制造不存在的场次警告。 */
    public static void validateReview(Map<String, Object> document, Map<String, Object> review) {
        Map<String, Set<String>> sceneLines = new HashMap<>();
        for (Object raw : list(document.get("scenes"))) {
            var scene = object(raw);
            String sceneId = text(scene.get("id") == null ? scene.get("tempKey") : scene.get("id"));
            Set<String> lines = new HashSet<>();
            for (Object value : list(scene.get("lines"))) {
                var line = object(value);
                lines.add(text(line.get("id") == null ? line.get("tempKey") : line.get("id")));
            }
            sceneLines.put(sceneId, lines);
        }
        for (Object value : list(review.get("findings"))) {
            var finding = object(value);
            Object scene = finding.get("sceneId");
            Object line = finding.get("lineId");
            if (scene == null ? line != null : !sceneLines.containsKey(scene)
                    || (line != null && !sceneLines.get(scene).contains(line))) {
                throw invalid("审阅问题引用不存在的剧本节点");
            }
        }
    }

    private static String identity(Map<String, Object> node, Set<String> seen) {
        Object id = node.get("id");
        Object temporary = node.get("tempKey");
        if ((id == null) == (temporary == null)) throw invalid("稳定身份与临时身份必须二选一");
        String identity = text(id == null ? temporary : id);
        if (!seen.add(identity)) throw invalid("剧本节点身份重复");
        return identity;
    }

    @SuppressWarnings("unchecked")
    static Map<String, Object> object(Object value) {
        if (!(value instanceof Map<?, ?> map) || map.keySet().stream().anyMatch(key -> !(key instanceof String))) {
            throw invalid("剧本对象形状无效");
        }
        return (Map<String, Object>) map;
    }

    static List<?> list(Object value) {
        if (!(value instanceof List<?> list)) throw invalid("剧本列表形状无效");
        return list;
    }

    static String text(Object value) {
        if (!(value instanceof String text) || text.isBlank()) throw invalid("剧本身份缺失");
        return text;
    }

    static long number(Object value) {
        if (!(value instanceof Number number)) throw invalid("剧本数值缺失");
        return number.longValue();
    }

    static IllegalArgumentException invalid(String message) { return new IllegalArgumentException(message); }
}
