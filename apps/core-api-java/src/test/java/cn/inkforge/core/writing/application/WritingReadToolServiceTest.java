package cn.inkforge.core.writing.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.references.domain.RagSearchHit;
import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class WritingReadToolServiceTest {

    @Test
    void 所有共享读取工具都有可执行行为() {
        WritingReadToolService service = service(false);
        Map<String, Map<String, Object>> arguments = Map.ofEntries(
                Map.entry("get_novel_info", Map.of("include_full_sections", true)),
                Map.entry("get_character_detail", Map.of("character_name", "沈墨")),
                Map.entry("get_faction_detail", Map.of("faction_name", "墨门")),
                Map.entry("get_location_detail", Map.of("location_name", "藏书楼")),
                Map.entry("get_item_detail", Map.of("item_name", "墨印")),
                Map.entry("get_glossary_detail", Map.of("term", "铸字")),
                Map.entry("search_lore", Map.of("keyword", "文字")),
                Map.entry("find_similar_lore", Map.of("keyword", "墨门")),
                Map.entry(
                        "semantic_search_references",
                        Map.of(
                                "query", "文字",
                                "topK", 5,
                                "query_embedding", List.of(0.1, 0.2))),
                Map.entry(
                        "list_outline_summary",
                        Map.of("scope", "tree_index", "include_full_summary", true)),
                Map.entry("get_outline_node", Map.of("node_id", "stage-1")),
                Map.entry(
                        "get_foreshadowing_detail",
                        Map.of("foreshadowing_name", "断裂的墨印")),
                Map.entry("get_recent_chapters", Map.of("count", 2)),
                Map.entry("get_review_artifact", Map.of("artifact_id", "artifact-1")));

        Map<String, Map<String, Object>> results = new LinkedHashMap<>();
        for (String name : WritingReadToolArguments.names()) {
            results.put(name, service.execute(request(name, arguments.getOrDefault(name, Map.of()))));
        }

        assertThat(results.keySet()).containsExactlyInAnyOrderElementsOf(WritingReadToolArguments.names());
        assertThat(results.get("get_novel_info")).containsEntry("worldSetting", "世界设定全文");
        assertThat(map(results.get("get_character_detail").get("character")))
                .containsEntry("name", "沈墨");
        assertThat(list(results.get("semantic_search_references").get("results")))
                .first()
                .satisfies(value -> assertThat(map(value)).containsEntry("text", "语义命中全文"));
    }

    @Test
    void 最近章节支持二十章并保持顺序和完整正文() {
        Map<String, Object> result = service(false).execute(request(
                "get_recent_chapters", Map.of("count", 20)));

        assertThat(result.get("count")).isEqualTo(20);
        List<?> chapters = list(result.get("chapters"));
        assertThat(chapters)
                .extracting(value -> map(value).get("id"))
                .containsExactly(java.util.stream.IntStream.rangeClosed(3, 22)
                        .mapToObj(order -> "chapter-" + order)
                        .toArray());
        assertThat(map(chapters.getLast()).get("content"))
                .isEqualTo("第22章完整正文".repeat(1_000));
    }

    @Test
    void 最近章节未指定数量时默认三章() {
        Map<String, Object> result = service(false).execute(request(
                "get_recent_chapters", Map.of()));

        assertThat(list(result.get("chapters")))
                .extracting(value -> map(value).get("id"))
                .containsExactly("chapter-20", "chapter-21", "chapter-22");
    }

    @Test
    void 草案必须属于当前任务且显式标记为待审核内容() {
        WritingReadToolService service = service(true);

        assertThatThrownBy(() -> service.execute(request(
                        "get_review_artifact", Map.of("artifact_id", "artifact-2"))))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(403);
                    assertThat(error.code()).isEqualTo("ARTIFACT_TASK_MISMATCH");
                });
        Map<String, Object> active = service(false).execute(request(
                "get_active_review_artifact", Map.of()));
        assertThat(active).containsEntry(
                "warning", WritingReadToolService.DRAFT_WARNING);
    }

    @Test
    void 写作任务必须绑定到请求中的小说() {
        WritingContextProvider wrong = (userId, taskId) -> {
            Map<String, Object> context = context();
            map(context.get("planning")).put("novelId", "novel-2");
            return context;
        };
        WritingReadToolService service = new WritingReadToolService(
                wrong,
                (novelId, userId) -> List.of(),
                new FakeReviews(false),
                (userId, novelId, embedding, topK) -> List.of(),
                new ObjectMapper());

        assertThatThrownBy(() -> service.execute(request("get_novel_info", Map.of())))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(403);
                    assertThat(error.code()).isEqualTo("WRITING_TASK_FORBIDDEN");
                });
    }

    private static WritingReadToolService service(boolean wrongArtifact) {
        return new WritingReadToolService(
                (userId, taskId) -> context(),
                (novelId, userId) -> List.of(Map.ofEntries(
                        Map.entry("id", "foreshadowing-1"),
                        Map.entry("name", "断裂的墨印"),
                        Map.entry("status", "planted"),
                        Map.entry("plantedContent", "第一章埋下"),
                        Map.entry("expectedPayoff", "终局回收"),
                        Map.entry("createdAt", OffsetDateTime.parse("2026-07-12T00:00:00Z")))),
                new FakeReviews(wrongArtifact),
                (userId, novelId, embedding, topK) -> List.of(new RagSearchHit(
                        "文字史", "reference-1", 0, new BigDecimal("0.9"), "语义命中全文")),
                new ObjectMapper());
    }

    private static Map<String, Object> context() {
        Map<String, Object> planning = new LinkedHashMap<>();
        planning.put("novelId", "novel-1");
        planning.put("chapterId", "chapter-23");
        planning.put("chapterOrder", 23);
        planning.put("chapterGroup", Map.of(
                "id", "group-1", "title", "第一幕", "content", "章节组全文"));
        planning.put("outlinePath", List.of(Map.of(
                "id", "stage-1", "title", "开端", "kind", "stage")));
        planning.put("activeArtifact", Map.of("id", "artifact-1"));

        Map<String, Object> workspace = new LinkedHashMap<>();
        workspace.put("novel", new LinkedHashMap<>(Map.ofEntries(
                Map.entry("id", "novel-1"),
                Map.entry("name", "测试小说"),
                Map.entry("summary", "小说简介"),
                Map.entry("storyProgress", "推进到第二十三章"),
                Map.entry("appliedStyleId", "style-1"))));
        List<Map<String, Object>> chapters = new ArrayList<>();
        for (int order = 1; order <= 23; order++) {
            chapters.add(Map.of(
                    "id", "chapter-" + order,
                    "title", "第" + order + "章",
                    "order", order,
                    "content", ("第" + order + "章完整正文").repeat(1_000)));
        }
        workspace.put("chapters", chapters);
        workspace.put("characters", List.of(Map.ofEntries(
                Map.entry("id", "character-1"),
                Map.entry("name", "沈墨"),
                Map.entry("aliases", "阿墨"),
                Map.entry("identity", "铸字师"),
                Map.entry("personality", "谨慎"),
                Map.entry("coreDesire", "找回真相"),
                Map.entry("experiences", List.of()))));
        workspace.put("factions", List.of(Map.of(
                "id", "faction-1", "name", "墨门", "description", "守护文字")));
        workspace.put("locations", List.of(Map.of(
                "id", "location-1", "name", "藏书楼", "description", "古老高塔")));
        workspace.put("items", List.of(Map.of(
                "id", "item-1", "name", "墨印", "effect", "记录真名")));
        workspace.put("glossaries", List.of(Map.of(
                "id", "term-1", "term", "铸字", "definition", "文字成真")));
        workspace.put("storyBackground", Map.of("content", "故事背景全文"));
        workspace.put("worldSetting", Map.of("content", "世界设定全文"));
        workspace.put("writingBible", Map.of("storyLengthProfile", "long_serial"));
        workspace.put("outline", Map.of("content", "总纲全文"));
        workspace.put("outlineNodes", List.of(Map.ofEntries(
                Map.entry("id", "stage-1"),
                Map.entry("title", "开端"),
                Map.entry("kind", "stage"),
                Map.entry("status", "in_progress"),
                Map.entry("order", 1),
                Map.entry("content", "阶段全文"))));
        workspace.put("plotProgress", Map.of("currentStage", "开端"));
        workspace.put("references", List.of(Map.of("id", "reference-1")));
        workspace.put("styles", List.of(Map.of(
                "id", "style-1",
                "name", "冷峻克制",
                "portraitMarkdown", "文风画像全文")));
        return new LinkedHashMap<>(Map.of("planning", planning, "workspace", workspace));
    }

    private static WritingToolRequest request(String name, Map<String, Object> arguments) {
        return new WritingToolRequest(
                "user-1", "novel-1", "task-1", "run-1", null, "写作", name, arguments);
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> map(Object value) {
        return (Map<String, Object>) value;
    }

    private static List<?> list(Object value) {
        return (List<?>) value;
    }

    private record FakeReviews(boolean wrongArtifact) implements WritingReviewArtifactReader {
        @Override
        public List<Map<String, Object>> listTaskArtifacts(
                String userId,
                String novelId,
                String taskId,
                String status,
                String kind) {
            return List.of(Map.of(
                    "id", "artifact-1", "taskId", taskId, "novelId", novelId));
        }

        @Override
        public Map<String, Object> get(String userId, String artifactId) {
            return Map.ofEntries(
                    Map.entry("id", artifactId),
                    Map.entry("taskId", wrongArtifact ? "task-2" : "task-1"),
                    Map.entry("novelId", "novel-1"),
                    Map.entry("kind", "chapter_draft"),
                    Map.entry("status", "under_review"),
                    Map.entry("payload", Map.of("kind", "chapter_draft", "content", "草案全文")));
        }
    }
}
