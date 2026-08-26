package cn.inkforge.core.writing.application;

import cn.inkforge.core.platform.http.ApiException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** 与 Python 共享契约一致的 26 个只读工具参数校验和注册表。 */
public final class WritingReadToolArguments {

    public static final Set<String> ALL_AGENT_IDS = Set.of("设定", "剧情", "写作", "校验", "编辑");
    private static final List<String> ORDERED_NAMES = List.of(
            "get_novel_info",
            "list_available_data",
            "list_characters_summary",
            "get_character_detail",
            "get_character_list",
            "list_factions_summary",
            "get_faction_detail",
            "list_locations_summary",
            "get_location_detail",
            "list_items_summary",
            "get_item_detail",
            "list_glossaries_summary",
            "get_glossary_detail",
            "search_lore",
            "find_similar_lore",
            "semantic_search_references",
            "get_style_profile",
            "list_outline_summary",
            "get_outline_node",
            "get_plot_progress",
            "list_foreshadowings_summary",
            "get_foreshadowing_detail",
            "get_recent_chapters",
            "list_review_artifacts",
            "get_review_artifact",
            "get_active_review_artifact");
    private static final Set<String> NAMES = Collections.unmodifiableSet(
            new LinkedHashSet<>(ORDERED_NAMES));
    private static final Set<String> EMPTY = Set.of(
            "list_available_data",
            "list_characters_summary",
            "get_character_list",
            "list_factions_summary",
            "list_locations_summary",
            "list_items_summary",
            "list_glossaries_summary",
            "get_style_profile",
            "get_plot_progress",
            "list_foreshadowings_summary",
            "get_active_review_artifact");

    private WritingReadToolArguments() {}

    public static Set<String> names() {
        return NAMES;
    }

    public static void register(
            WritingToolGateway gateway, WritingReadToolExecutor service) {
        for (String name : ORDERED_NAMES) {
            gateway.register(name, ALL_AGENT_IDS, true, request -> service.execute(
                    new WritingToolRequest(
                            request.userId(),
                            request.novelId(),
                            request.taskId(),
                            request.runId(),
                            null,
                            request.agentId(),
                            request.toolName(),
                            validate(request.toolName(), request.arguments()))));
        }
    }

    public static Map<String, Object> validate(
            String toolName, Map<String, Object> rawArguments) {
        try {
            Map<String, Object> raw = new LinkedHashMap<>(
                    rawArguments == null ? Map.of() : rawArguments);
            Object rawEmbedding = raw.remove("query_embedding");
            Map<String, Object> result = new LinkedHashMap<>();
            if (EMPTY.contains(toolName)) {
                requireOnly(raw, Set.of());
            } else {
                switch (toolName) {
                    case "get_novel_info" -> optionalBoolean(
                            raw, result, "include_full_sections");
                    case "get_character_detail" -> requiredOnlyText(
                            raw, result, "character_name");
                    case "get_faction_detail" -> requiredOnlyText(
                            raw, result, "faction_name");
                    case "get_location_detail" -> requiredOnlyText(
                            raw, result, "location_name");
                    case "get_item_detail" -> requiredOnlyText(raw, result, "item_name");
                    case "get_glossary_detail" -> requiredOnlyText(raw, result, "term");
                    case "search_lore" -> requiredOnlyText(raw, result, "keyword");
                    case "find_similar_lore" -> {
                        requireOnly(raw, Set.of("keyword", "threshold"));
                        requiredText(raw, result, "keyword");
                        optionalDouble(raw, result, "threshold", 0, 1);
                    }
                    case "semantic_search_references" -> {
                        requireOnly(raw, Set.of("query", "topK"));
                        requiredText(raw, result, "query");
                        optionalInteger(raw, result, "topK", 1, 20);
                    }
                    case "list_outline_summary" -> {
                        requireOnly(raw, Set.of("scope", "include_full_summary"));
                        optionalEnum(
                                raw,
                                result,
                                "scope",
                                Set.of("current_chapter", "tree_index"));
                        optionalBoolean(raw, result, "include_full_summary");
                    }
                    case "get_outline_node" -> {
                        requireOnly(raw, Set.of("node_id", "node_title"));
                        optionalText(raw, result, "node_id");
                        optionalText(raw, result, "node_title");
                        if (!result.containsKey("node_id") && !result.containsKey("node_title")) {
                            throw invalid();
                        }
                    }
                    case "get_foreshadowing_detail" -> requiredOnlyText(
                            raw, result, "foreshadowing_name");
                    case "get_recent_chapters" -> {
                        requireOnly(raw, Set.of("count"));
                        optionalInteger(raw, result, "count", 1, 20);
                    }
                    case "list_review_artifacts" -> {
                        requireOnly(raw, Set.of("status", "kind"));
                        optionalEnum(
                                raw,
                                result,
                                "status",
                                Set.of(
                                        "draft",
                                        "under_review",
                                        "awaiting_user",
                                        "applying",
                                        "applied"));
                        optionalText(raw, result, "kind");
                    }
                    case "get_review_artifact" -> requiredOnlyText(
                            raw, result, "artifact_id");
                    default -> throw invalid();
                }
            }
            if (rawEmbedding != null) {
                if (!"semantic_search_references".equals(toolName)) throw invalid();
                result.put("query_embedding", embedding(rawEmbedding));
            }
            return Collections.unmodifiableMap(result);
        } catch (ApiException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw invalid();
        }
    }

    private static void requiredOnlyText(
            Map<String, Object> raw, Map<String, Object> result, String key) {
        requireOnly(raw, Set.of(key));
        requiredText(raw, result, key);
    }

    private static void requiredText(
            Map<String, Object> raw, Map<String, Object> result, String key) {
        Object value = raw.get(key);
        if (!(value instanceof String text) || text.isEmpty()) throw invalid();
        result.put(key, text);
    }

    private static void optionalText(
            Map<String, Object> raw, Map<String, Object> result, String key) {
        Object value = raw.get(key);
        if (value == null) return;
        if (!(value instanceof String text) || text.isEmpty()) throw invalid();
        result.put(key, text);
    }

    private static void optionalBoolean(
            Map<String, Object> raw, Map<String, Object> result, String key) {
        requireOnly(raw, Set.of(key));
        Object value = raw.get(key);
        if (value == null) return;
        if (!(value instanceof Boolean flag)) throw invalid();
        result.put(key, flag);
    }

    private static void optionalInteger(
            Map<String, Object> raw,
            Map<String, Object> result,
            String key,
            int minimum,
            int maximum) {
        Object value = raw.get(key);
        if (value == null) return;
        if (!(value instanceof Number number)
                || value instanceof Float
                || value instanceof Double
                || value instanceof Boolean) {
            throw invalid();
        }
        long candidate = number.longValue();
        if (candidate < minimum || candidate > maximum || candidate != number.doubleValue()) {
            throw invalid();
        }
        result.put(key, (int) candidate);
    }

    private static void optionalDouble(
            Map<String, Object> raw,
            Map<String, Object> result,
            String key,
            double minimum,
            double maximum) {
        Object value = raw.get(key);
        if (value == null) return;
        if (!(value instanceof Number number) || value instanceof Boolean) throw invalid();
        double candidate = number.doubleValue();
        if (!Double.isFinite(candidate) || candidate < minimum || candidate > maximum) {
            throw invalid();
        }
        result.put(key, candidate);
    }

    private static void optionalEnum(
            Map<String, Object> raw,
            Map<String, Object> result,
            String key,
            Set<String> values) {
        Object value = raw.get(key);
        if (value == null) return;
        if (!(value instanceof String text) || !values.contains(text)) throw invalid();
        result.put(key, text);
    }

    private static List<Double> embedding(Object value) {
        if (!(value instanceof List<?> values) || values.isEmpty() || values.size() > 4096) {
            throw invalid();
        }
        List<Double> result = new ArrayList<>(values.size());
        for (Object item : values) {
            if (!(item instanceof Number number) || item instanceof Boolean) throw invalid();
            double candidate = number.doubleValue();
            if (!Double.isFinite(candidate)) throw invalid();
            result.add(candidate);
        }
        return List.copyOf(result);
    }

    private static void requireOnly(Map<String, Object> raw, Set<String> allowed) {
        if (!allowed.containsAll(raw.keySet())) throw invalid();
    }

    private static ApiException invalid() {
        return new ApiException(422, "TOOL_ARGUMENTS_INVALID", "智能体工具参数无效");
    }
}
