package cn.inkforge.core.writing.application;

import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.references.domain.RagSearchHit;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import tools.jackson.databind.ObjectMapper;

/**
 * 将作品工作区投影为受限、可审计且不截断正文的 Agent 只读工具结果。
 *
 * <p>所有工具先从 Core 权威工作区与规划快照校验 task/novel 绑定，再按白名单投影字段。章节正文和 RAG
 * 命中完整返回，不做静默截断；ReviewArtifact 始终附带草案警告，防止 Agent 把候选当作正式设定。
 */
public final class WritingReadToolService implements WritingReadToolExecutor {

    public static final String DRAFT_WARNING =
            "以下内容是待审核草案，不是正式设定。未经用户确认不得视为已落库事实。";

    private final WritingContextProvider contextProvider;
    private final WritingForeshadowingReader foreshadowings;
    private final WritingReviewArtifactReader reviews;
    private final WritingSemanticReferenceReader semanticReferences;
    private final ObjectMapper json;

    public WritingReadToolService(
            WritingContextProvider contextProvider,
            WritingForeshadowingReader foreshadowings,
            WritingReviewArtifactReader reviews,
            WritingSemanticReferenceReader semanticReferences,
            ObjectMapper json) {
        this.contextProvider = Objects.requireNonNull(contextProvider);
        this.foreshadowings = Objects.requireNonNull(foreshadowings);
        this.reviews = Objects.requireNonNull(reviews);
        this.semanticReferences = semanticReferences;
        this.json = Objects.requireNonNull(json);
    }

    @Override
    public Map<String, Object> execute(WritingToolRequest request) {
        // 每次调用只构建一份工作区快照，避免同一工具结果混入不同时间点的章节、设定与版本 Head。
        Map<String, Object> context = mapping(
                contextProvider.build(request.userId(), request.taskId()), "写作上下文");
        Map<String, Object> workspace = mapping(context.get("workspace"), "作品工作区");
        Map<String, Object> planning = mapping(context.get("planning"), "写作任务上下文");
        if (!Objects.equals(planning.get("novelId"), request.novelId())) {
            throw new ApiException(403, "WRITING_TASK_FORBIDDEN", "写作任务与当前小说不匹配");
        }
        Map<String, Object> arguments = request.arguments();
        return switch (request.toolName()) {
            case "get_novel_info" -> novelInfo(workspace, planning, arguments);
            case "list_available_data" -> availableData(request, workspace);
            case "list_characters_summary" -> object(
                    "characters",
                    items(workspace, "characters").stream()
                            .map(WritingReadToolService::characterSummary)
                            .toList());
            case "get_character_detail" -> object(
                    "character",
                    findNamed(
                            items(workspace, "characters"),
                            "name",
                            arguments.get("character_name"),
                            "角色"));
            case "get_character_list" -> object(
                    "characters",
                    items(workspace, "characters").stream()
                            .map(item -> pick(
                                    item,
                                    "id",
                                    "name",
                                    "aliases",
                                    "gender",
                                    "identity",
                                    "faction",
                                    "currentStatus"))
                            .toList());
            case "list_factions_summary" -> object(
                    "factions",
                    items(workspace, "factions").stream()
                            .map(item -> pick(
                                    item,
                                    "id",
                                    "name",
                                    "aliases",
                                    "type",
                                    "base",
                                    "description"))
                            .toList());
            case "get_faction_detail" -> object(
                    "faction",
                    findNamed(
                            items(workspace, "factions"),
                            "name",
                            arguments.get("faction_name"),
                            "势力"));
            case "list_locations_summary" -> object(
                    "locations",
                    items(workspace, "locations").stream()
                            .map(item -> pick(
                                    item,
                                    "id",
                                    "name",
                                    "aliases",
                                    "type",
                                    "climate",
                                    "description"))
                            .toList());
            case "get_location_detail" -> object(
                    "location",
                    findNamed(
                            items(workspace, "locations"),
                            "name",
                            arguments.get("location_name"),
                            "地点"));
            case "list_items_summary" -> object(
                    "items",
                    items(workspace, "items").stream()
                            .map(item -> pick(
                                    item,
                                    "id",
                                    "name",
                                    "aliases",
                                    "type",
                                    "rarity",
                                    "effect",
                                    "description",
                                    "owner"))
                            .toList());
            case "get_item_detail" -> object(
                    "item",
                    findNamed(
                            items(workspace, "items"),
                            "name",
                            arguments.get("item_name"),
                            "物品"));
            case "list_glossaries_summary" -> object(
                    "glossaries",
                    items(workspace, "glossaries").stream()
                            .map(item -> pick(item, "id", "term", "category", "definition"))
                            .toList());
            case "get_glossary_detail" -> object(
                    "glossary",
                    findNamed(
                            items(workspace, "glossaries"),
                            "term",
                            arguments.get("term"),
                            "术语"));
            case "search_lore" -> searchLore(
                    request, workspace, String.valueOf(arguments.get("keyword")));
            case "find_similar_lore" -> similarLore(workspace, arguments);
            case "semantic_search_references" -> semanticReferences(request, arguments);
            case "get_style_profile" -> styleProfile(workspace);
            case "list_outline_summary" -> outlineSummary(workspace, planning, arguments);
            case "get_outline_node" -> outlineNode(workspace, arguments);
            case "get_plot_progress" -> object("plotProgress", workspace.get("plotProgress"));
            case "list_foreshadowings_summary" -> object(
                    "foreshadowings",
                    foreshadowingValues(request).stream()
                            .map(item -> pick(
                                    item,
                                    "id",
                                    "name",
                                    "status",
                                    "plantedAt",
                                    "plantedContent",
                                    "expectedPayoff",
                                    "payoffAt"))
                            .toList());
            case "get_foreshadowing_detail" -> object(
                    "foreshadowing",
                    findNamed(
                            foreshadowingValues(request),
                            "name",
                            arguments.get("foreshadowing_name"),
                            "伏笔"));
            case "get_recent_chapters" -> recentChapters(workspace, planning, arguments);
            case "list_review_artifacts" -> listArtifacts(request, arguments);
            case "get_review_artifact" -> artifact(
                    request, String.valueOf(arguments.get("artifact_id")));
            case "get_active_review_artifact" -> activeArtifact(request, planning);
            default -> throw new ApiException(404, "TOOL_NOT_FOUND", "读取工具不存在");
        };
    }

    private static Map<String, Object> novelInfo(
            Map<String, Object> workspace,
            Map<String, Object> planning,
            Map<String, Object> arguments) {
        Map<String, Object> novel = mapping(workspace.get("novel"), "小说信息");
        Object chapterId = planning.get("chapterId");
        Map<String, Object> chapter = items(workspace, "chapters").stream()
                .filter(item -> Objects.equals(item.get("id"), chapterId))
                .findFirst()
                .orElse(null);
        boolean included = Boolean.TRUE.equals(arguments.get("include_full_sections"));
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("novel", new LinkedHashMap<>(novel));
        result.put("chapterTitle", chapter == null ? null : chapter.get("title"));
        result.put("writingBible", workspace.get("writingBible"));
        result.put("sectionsIncluded", included);
        Map<String, Object> sections = new LinkedHashMap<>();
        sections.put("outlineSummary", content(workspace.get("outline")));
        sections.put("storyBackground", content(workspace.get("storyBackground")));
        sections.put("worldSetting", content(workspace.get("worldSetting")));
        sections.put("storyProgress", novel.get("storyProgress"));
        if (included) {
            result.putAll(sections);
        } else {
            Map<String, Object> available = new LinkedHashMap<>();
            sections.forEach((key, value) -> available.put(key, truthy(value)));
            result.put("availableSections", available);
        }
        return result;
    }

    private Map<String, Object> availableData(
            WritingToolRequest request, Map<String, Object> workspace) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("characters", items(workspace, "characters").size());
        result.put("factions", items(workspace, "factions").size());
        result.put("locations", items(workspace, "locations").size());
        result.put("items", items(workspace, "items").size());
        result.put("glossaries", items(workspace, "glossaries").size());
        result.put("outlineNodes", items(workspace, "outlineNodes").size());
        result.put("foreshadowings", foreshadowingValues(request).size());
        result.put("references", items(workspace, "references").size());
        result.put("hasStyleProfile", appliedStyle(workspace) != null);
        return result;
    }

    private Map<String, Object> searchLore(
            WritingToolRequest request, Map<String, Object> workspace, String keyword) {
        Map<String, List<Map<String, Object>>> domains = new LinkedHashMap<>();
        domains.put("characters", items(workspace, "characters"));
        domains.put("factions", items(workspace, "factions"));
        domains.put("locations", items(workspace, "locations"));
        domains.put("items", items(workspace, "items"));
        domains.put("glossaries", items(workspace, "glossaries"));
        domains.put("foreshadowings", foreshadowingValues(request));
        String lowered = keyword.toLowerCase(Locale.ROOT);
        Map<String, Object> found = new LinkedHashMap<>();
        domains.forEach((domain, values) -> found.put(
                domain,
                values.stream()
                        .filter(item -> json.writeValueAsString(item)
                                .toLowerCase(Locale.ROOT)
                                .contains(lowered))
                        .toList()));
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("keyword", keyword);
        result.put("results", found);
        return result;
    }

    private static Map<String, Object> similarLore(
            Map<String, Object> workspace, Map<String, Object> arguments) {
        String keyword = String.valueOf(arguments.get("keyword"));
        double threshold = arguments.get("threshold") instanceof Number number
                ? number.doubleValue()
                : 0.3;
        List<Map<String, Object>> results = new ArrayList<>();
        for (Map.Entry<String, String> domain : Map.of(
                        "characters", "name",
                        "factions", "name",
                        "locations", "name",
                        "items", "name",
                        "glossaries", "term")
                .entrySet()) {
            for (Map<String, Object> item : items(workspace, domain.getKey())) {
                Object rawName = item.get(domain.getValue());
                if (!(rawName instanceof String name)) continue;
                double similarity = sequenceRatio(
                        name.toLowerCase(Locale.ROOT), keyword.toLowerCase(Locale.ROOT));
                if (similarity < threshold) continue;
                Map<String, Object> found = new LinkedHashMap<>();
                found.put("domain", domain.getKey());
                found.put("name", name);
                found.put(
                        "similarity",
                        BigDecimal.valueOf(similarity)
                                .setScale(4, RoundingMode.HALF_EVEN)
                                .doubleValue());
                results.add(found);
            }
        }
        results.sort(Comparator.comparingDouble(
                        (Map<String, Object> item) ->
                                ((Number) item.get("similarity")).doubleValue())
                .reversed());
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("keyword", keyword);
        result.put("threshold", threshold);
        result.put("results", results);
        return result;
    }

    private Map<String, Object> semanticReferences(
            WritingToolRequest request, Map<String, Object> arguments) {
        Object rawEmbedding = arguments.get("query_embedding");
        if (semanticReferences == null || !(rawEmbedding instanceof List<?> values)) {
            return disabledSemanticSearch();
        }
        List<Double> embedding = values.stream()
                .map(value -> ((Number) value).doubleValue())
                .toList();
        int topK = arguments.get("topK") instanceof Number number ? number.intValue() : 5;
        List<Map<String, Object>> results = semanticReferences
                .search(request.userId(), request.novelId(), embedding, topK)
                .stream()
                .map(WritingReadToolService::ragHit)
                .toList();
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("enabled", true);
        result.put("count", results.size());
        result.put("results", results);
        return result;
    }

    private static Map<String, Object> disabledSemanticSearch() {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("enabled", false);
        result.put("message", "RAG embedding 未配置，参考资料语义召回未启用。");
        result.put("results", List.of());
        return result;
    }

    private static Map<String, Object> ragHit(RagSearchHit hit) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("title", hit.title());
        result.put("sourceId", hit.sourceId());
        result.put("chunkIndex", hit.chunkIndex());
        result.put("score", hit.score().doubleValue());
        result.put("text", hit.text());
        return result;
    }

    private static Map<String, Object> styleProfile(Map<String, Object> workspace) {
        Map<String, Object> style = appliedStyle(workspace);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("available", style != null);
        result.put("style", style);
        return result;
    }

    private static Map<String, Object> appliedStyle(Map<String, Object> workspace) {
        Map<String, Object> novel = mapping(workspace.get("novel"), "小说信息");
        Object appliedId = novel.get("appliedStyleId");
        return items(workspace, "styles").stream()
                .filter(item -> Objects.equals(item.get("id"), appliedId)
                        && truthy(item.get("portraitMarkdown")))
                .findFirst()
                .orElse(null);
    }

    private static Map<String, Object> outlineSummary(
            Map<String, Object> workspace,
            Map<String, Object> planning,
            Map<String, Object> arguments) {
        String scope = arguments.get("scope") instanceof String value
                ? value
                : "current_chapter";
        if ("current_chapter".equals(scope)) {
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("scope", scope);
            result.put("outlinePath", planning.getOrDefault("outlinePath", List.of()));
            result.put("chapterGroup", planning.get("chapterGroup"));
            return result;
        }
        boolean include = Boolean.TRUE.equals(arguments.get("include_full_summary"));
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("scope", "tree_index");
        result.put(
                "nodes",
                items(workspace, "outlineNodes").stream()
                        .map(item -> pick(
                                item,
                                "id",
                                "title",
                                "kind",
                                "status",
                                "order",
                                "parentId",
                                "chapterStartOrder",
                                "chapterEndOrder"))
                        .toList());
        result.put("summaryIncluded", include);
        if (include) result.put("summary", content(workspace.get("outline")));
        return result;
    }

    private static Map<String, Object> outlineNode(
            Map<String, Object> workspace, Map<String, Object> arguments) {
        Object nodeId = arguments.get("node_id");
        Object nodeTitle = arguments.get("node_title");
        List<Map<String, Object>> nodes = items(workspace, "outlineNodes");
        List<Map<String, Object>> matches = nodes.stream()
                .filter(item -> (truthy(nodeId) && Objects.equals(item.get("id"), nodeId))
                        || (truthy(nodeTitle)
                                && item.get("title") instanceof String title
                                && title.contains(String.valueOf(nodeTitle))))
                .toList();
        if (matches.size() > 1) {
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("error", "OUTLINE_NODE_AMBIGUOUS");
            result.put(
                    "candidates",
                    matches.stream().map(item -> pick(item, "id", "title", "kind")).toList());
            return result;
        }
        if (matches.isEmpty()) throw notFound("大纲节点", String.valueOf(
                truthy(nodeId) ? nodeId : nodeTitle));
        Map<String, Object> node = matches.getFirst();
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("node", node);
        result.put(
                "parent",
                nodes.stream()
                        .filter(item -> Objects.equals(item.get("id"), node.get("parentId")))
                        .findFirst()
                        .orElse(null));
        result.put(
                "children",
                nodes.stream()
                        .filter(item -> Objects.equals(item.get("parentId"), node.get("id")))
                        .toList());
        return result;
    }

    private static Map<String, Object> recentChapters(
            Map<String, Object> workspace,
            Map<String, Object> planning,
            Map<String, Object> arguments) {
        int count = arguments.get("count") instanceof Number number ? number.intValue() : 3;
        Object boundary = planning.get("chapterOrder");
        List<Map<String, Object>> chapters = new ArrayList<>(items(workspace, "chapters"));
        chapters.sort(Comparator.comparingInt(item -> integer(item.get("order"))));
        List<Map<String, Object>> eligible = chapters.stream()
                .filter(item -> !(boundary instanceof Number number)
                        || integer(item.get("order")) < number.intValue())
                .toList();
        int start = Math.max(0, eligible.size() - count);
        List<Map<String, Object>> selected = eligible.subList(start, eligible.size());
        // count 限制章节数量而非单章长度；选中的正文必须原样完整返回。
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("count", selected.size());
        result.put(
                "chapters",
                selected.stream()
                        .map(item -> pick(item, "id", "title", "order", "content"))
                        .toList());
        result.put("note", "只按目标章节位置选择最近章节，正文完整返回。");
        return result;
    }

    private List<Map<String, Object>> foreshadowingValues(WritingToolRequest request) {
        return foreshadowings.list(request.novelId(), request.userId()).stream()
                .map(value -> mapping(jsonSafe(value), "伏笔"))
                .toList();
    }

    private Map<String, Object> listArtifacts(
            WritingToolRequest request, Map<String, Object> arguments) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("warning", DRAFT_WARNING);
        result.put(
                "artifacts",
                reviews.listTaskArtifacts(
                        request.userId(),
                        request.novelId(),
                        request.taskId(),
                        optionalText(arguments.get("status")),
                        optionalText(arguments.get("kind"))));
        return result;
    }

    private Map<String, Object> activeArtifact(
            WritingToolRequest request, Map<String, Object> planning) {
        Object active = planning.get("activeArtifact");
        Object activeId = active instanceof Map<?, ?> map ? map.get("id") : null;
        if (!(activeId instanceof String id) || id.isEmpty()) {
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("warning", DRAFT_WARNING);
            result.put("artifact", null);
            return result;
        }
        return artifact(request, id);
    }

    private Map<String, Object> artifact(WritingToolRequest request, String artifactId) {
        Map<String, Object> artifact = reviews.get(request.userId(), artifactId);
        // 用户归属校验仍不足够：Agent 只能读取当前 task 内的草案，不能跨任务吸收未确认内容。
        if (!Objects.equals(artifact.get("novelId"), request.novelId())
                || !Objects.equals(artifact.get("taskId"), request.taskId())) {
            throw new ApiException(403, "ARTIFACT_TASK_MISMATCH", "待审核草案不属于当前任务");
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("warning", DRAFT_WARNING);
        result.put("artifact", artifact);
        return result;
    }

    private Object jsonSafe(Object value) {
        if (value instanceof OffsetDateTime timestamp) {
            return timestamp.withOffsetSameInstant(ZoneOffset.UTC).toInstant().toString();
        }
        if (value instanceof LocalDateTime timestamp) {
            return timestamp.toInstant(ZoneOffset.UTC).toString();
        }
        if (value instanceof Instant timestamp) return timestamp.toString();
        if (value instanceof Map<?, ?> map) {
            Map<String, Object> result = new LinkedHashMap<>();
            map.forEach((key, item) -> {
                if (!(key instanceof String text)) throw new IllegalArgumentException("JSON key 无效");
                result.put(text, jsonSafe(item));
            });
            return result;
        }
        if (value instanceof List<?> list) return list.stream().map(this::jsonSafe).toList();
        return value;
    }

    private static Map<String, Object> characterSummary(Map<String, Object> item) {
        Map<String, Object> result = pick(
                item,
                "id",
                "name",
                "aliases",
                "identity",
                "faction",
                "personality",
                "coreDesire",
                "behaviorBoundaries",
                "shortTermGoal",
                "currentStatus",
                "statusNote");
        result.put(
                "experienceCount",
                item.get("experiences") instanceof List<?> values ? values.size() : 0);
        return result;
    }

    private static Map<String, Object> findNamed(
            List<Map<String, Object>> values,
            String key,
            Object query,
            String label) {
        String text = String.valueOf(query).toLowerCase(Locale.ROOT);
        for (Map<String, Object> item : values) {
            Object rawName = item.get(key);
            Object rawAliases = item.get("aliases");
            if (rawName instanceof String name) {
                String lowered = name.toLowerCase(Locale.ROOT);
                if (lowered.contains(text) || text.contains(lowered)) return item;
            }
            if (rawAliases instanceof String aliases
                    && aliases.toLowerCase(Locale.ROOT).contains(text)) {
                return item;
            }
        }
        throw notFound(label, String.valueOf(query));
    }

    private static ApiException notFound(String label, String query) {
        return new ApiException(404, "TOOL_RESOURCE_NOT_FOUND", "未找到" + label + "：" + query);
    }

    private static List<Map<String, Object>> items(
            Map<String, Object> workspace, String key) {
        Object raw = workspace.getOrDefault(key, List.of());
        if (!(raw instanceof List<?> values)) {
            throw new IllegalStateException("作品工作区字段 " + key + " 格式无效");
        }
        List<Map<String, Object>> result = new ArrayList<>(values.size());
        for (Object value : values) result.add(mapping(value, "作品工作区字段 " + key));
        return result;
    }

    private static Map<String, Object> mapping(Object value, String label) {
        if (!(value instanceof Map<?, ?> map)) throw new IllegalStateException(label + "格式无效");
        Map<String, Object> result = new LinkedHashMap<>();
        map.forEach((key, item) -> {
            if (!(key instanceof String text)) throw new IllegalStateException(label + "格式无效");
            result.put(text, item);
        });
        return result;
    }

    private static String content(Object value) {
        if (!(value instanceof Map<?, ?> map)) return "";
        return String.valueOf(map.containsKey("content") ? map.get("content") : "");
    }

    private static Map<String, Object> pick(Map<String, Object> item, String... keys) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (String key : keys) result.put(key, item.get(key));
        return result;
    }

    private static Map<String, Object> object(String key, Object value) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put(key, value);
        return result;
    }

    private static boolean truthy(Object value) {
        if (value == null || Boolean.FALSE.equals(value)) return false;
        if (value instanceof String text) return !text.isEmpty();
        if (value instanceof List<?> list) return !list.isEmpty();
        if (value instanceof Map<?, ?> map) return !map.isEmpty();
        if (value instanceof Number number) return number.doubleValue() != 0;
        return true;
    }

    private static int integer(Object value) {
        return value instanceof Number number ? number.intValue() : 0;
    }

    private static String optionalText(Object value) {
        return value instanceof String text && !text.isEmpty() ? text : null;
    }

    /** Python difflib.SequenceMatcher(None, a, b).ratio() 的无 junk 等价实现。 */
    private static double sequenceRatio(String first, String second) {
        int[] a = first.codePoints().toArray();
        int[] b = second.codePoints().toArray();
        if (a.length + b.length == 0) return 1;
        Map<Integer, List<Integer>> positions = new HashMap<>();
        for (int index = 0; index < b.length; index++) {
            positions.computeIfAbsent(b[index], ignored -> new ArrayList<>()).add(index);
        }
        if (b.length >= 200) {
            int popular = b.length / 100 + 1;
            positions.entrySet().removeIf(entry -> entry.getValue().size() > popular);
        }
        int matched = 0;
        ArrayDeque<Range> pending = new ArrayDeque<>();
        pending.push(new Range(0, a.length, 0, b.length));
        while (!pending.isEmpty()) {
            Range range = pending.pop();
            Block block = longest(a, b, positions, range);
            if (block.size() == 0) continue;
            matched += block.size();
            if (range.aLow() < block.a() && range.bLow() < block.b()) {
                pending.push(new Range(range.aLow(), block.a(), range.bLow(), block.b()));
            }
            int aAfter = block.a() + block.size();
            int bAfter = block.b() + block.size();
            if (aAfter < range.aHigh() && bAfter < range.bHigh()) {
                pending.push(new Range(aAfter, range.aHigh(), bAfter, range.bHigh()));
            }
        }
        return 2.0 * matched / (a.length + b.length);
    }

    private static Block longest(
            int[] a,
            int[] b,
            Map<Integer, List<Integer>> positions,
            Range range) {
        int bestA = range.aLow();
        int bestB = range.bLow();
        int bestSize = 0;
        Map<Integer, Integer> previous = Map.of();
        for (int aIndex = range.aLow(); aIndex < range.aHigh(); aIndex++) {
            Map<Integer, Integer> current = new HashMap<>();
            for (int bIndex : positions.getOrDefault(a[aIndex], List.of())) {
                if (bIndex < range.bLow()) continue;
                if (bIndex >= range.bHigh()) break;
                int size = previous.getOrDefault(bIndex - 1, 0) + 1;
                current.put(bIndex, size);
                if (size > bestSize) {
                    bestA = aIndex - size + 1;
                    bestB = bIndex - size + 1;
                    bestSize = size;
                }
            }
            previous = current;
        }
        while (bestA > range.aLow()
                && bestB > range.bLow()
                && a[bestA - 1] == b[bestB - 1]) {
            bestA--;
            bestB--;
            bestSize++;
        }
        while (bestA + bestSize < range.aHigh()
                && bestB + bestSize < range.bHigh()
                && a[bestA + bestSize] == b[bestB + bestSize]) {
            bestSize++;
        }
        return new Block(bestA, bestB, bestSize);
    }

    private record Range(int aLow, int aHigh, int bLow, int bHigh) {}

    private record Block(int a, int b, int size) {}
}
