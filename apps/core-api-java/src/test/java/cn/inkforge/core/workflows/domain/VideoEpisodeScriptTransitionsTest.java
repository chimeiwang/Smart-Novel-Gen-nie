package cn.inkforge.core.workflows.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.workflows.catalog.ExecutionPlanSnapshot;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.catalog.ExecutionRegistryFixtures;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class VideoEpisodeScriptTransitionsTest {
    @Test
    void 局部改稿在Core合并范围外内容且Run完成只产生候选() {
        Flow flow = new Flow();
        flow.complete(proposal(), null);
        assertThat(flow.decision.nextInput()).containsEntry("stageKey", "episode_script_review");
        flow.complete(null, review("pass"));
        assertThat(flow.history).hasSize(2);
        assertThat(flow.decision.nextInput()).isNull();
        assertThat(flow.decision.document()).containsEntry("schemaVersion", "video-episode-script/1.0");
        List<?> scenes = (List<?>) flow.decision.document().get("scenes");
        assertThat(scenes.get(1)).isEqualTo(((List<?>) ((Map<?, ?>) flow.context.get("draft")).get("scenes")).get(1));
        assertThat(flow.decision.document()).doesNotContainKeys("currentScriptVersionId", "currentProductionBaselineId");
    }

    @Test
    void 审阅最多促成一次返工且第二次问题完整交作者() {
        Flow flow = new Flow();
        flow.complete(proposal(), null);
        flow.complete(null, review("revise"));
        assertThat(flow.decision.nextInput()).containsEntry("cycle", 1);
        assertThat((List<?>) flow.decision.nextInput().get("dependencies")).hasSize(2);
        flow.complete(proposal(), null);
        flow.complete(null, review("revise"));
        assertThat(flow.history).hasSize(4);
        assertThat(flow.decision.nextInput()).isNull();
        assertThat(flow.decision.review()).containsEntry("decision", "revise");
    }

    @Test
    void 无法删除前序依赖或替换未授权场次() {
        Flow flow = new Flow();
        flow.complete(proposal(), null);
        Map<String, Object> forgedInput = new LinkedHashMap<>(flow.decision.nextInput());
        forgedInput.put("dependencies", List.of());
        flow.history.add(new VideoEpisodeScriptTransitions.Completed("step-2", "b".repeat(64), forgedInput,
                output("episode_script_review", null, review("pass"))));
        assertThatThrownBy(() -> VideoEpisodeScriptTransitions.replay(flow.plan, flow.context, flow.history))
                .isInstanceOf(IllegalArgumentException.class).hasMessageContaining("唯一接续");
        var wrong = new LinkedHashMap<>(proposal());
        wrong.put("scenes", List.of(scene("scene-2", "line-2", "覆盖无关场次")));
        assertThatThrownBy(() -> VideoEpisodeScriptDocuments.merge(flow.context, wrong)).hasMessageContaining("范围");
    }

    @Test
    void 模型不能冒造稳定身份或跨场借用台词() {
        Flow flow = new Flow();
        var wrong = new LinkedHashMap<>(proposal());
        wrong.put("scenes", List.of(scene("scene-1", "line-2", "借用其他场次身份")));
        assertThatThrownBy(() -> VideoEpisodeScriptDocuments.merge(flow.context, wrong)).hasMessageContaining("挪用");
        wrong.put("scenes", List.of(scene("scene-1", "unknown-stable-id", "伪造身份")));
        assertThatThrownBy(() -> VideoEpisodeScriptDocuments.merge(flow.context, wrong)).hasMessageContaining("稳定台词");
    }

    @Test
    void 局部修订不能换结尾状态且空范围不能升级为全稿() {
        Flow flow = new Flow();
        Map<String, Object> wrong = new LinkedHashMap<>(proposal());
        wrong.put("endingStates", List.of());
        assertThatThrownBy(() -> VideoEpisodeScriptDocuments.merge(flow.context, wrong)).hasMessageContaining("结尾状态");
        flow.context.put("selectedSceneIds", List.of());
        assertThatThrownBy(() -> VideoEpisodeScriptDocuments.merge(flow.context, proposal())).hasMessageContaining("限定场次");
    }

    static Map<String, Object> context() {
        var document = Map.of("schemaVersion", "video-episode-script/1.0", "overview", Map.of("summary", "本集目标"),
                "scenes", List.of(scene("scene-1", "line-1", "原行动"), scene("scene-2", "line-2", "范围外原文")),
                "endingStates", List.of(), "dependencies", List.of());
        return new LinkedHashMap<>(Map.of("operation", "episode_script_revise", "draft", document,
                "selectedSceneIds", List.of("scene-1"), "characters", List.of(), "sources", List.of(), "inheritedStates", List.of()));
    }

    static Map<String, Object> proposal() {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("overview", null); result.put("endingStates", null); result.put("dependencies", null);
        result.put("scenes", List.of(scene("scene-1", "line-1", "修订行动")));
        return result;
    }

    private static Map<String, Object> scene(String id, String lineId, String text) {
        Map<String, Object> line = new LinkedHashMap<>();
        line.put("id", lineId); line.put("tempKey", null); line.put("kind", "action");
        line.put("speakerId", null); line.put("text", text); line.put("sourceRefs", List.of());
        return Map.of("id", id, "title", "书房", "locationLabel", "书房", "timeLabel", "夜",
                "narrativeTime", "当晚", "characterIds", List.of(), "lines", List.of(line));
    }

    private static Map<String, Object> review(String decision) {
        return Map.of("decision", decision, "summary", "审阅结论", "requiredChanges",
                "revise".equals(decision) ? List.of("具体问题") : List.of(), "findings", List.of());
    }

    private static Map<String, Object> output(String stage, Map<String, Object> candidate, Map<String, Object> review) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("stageKey", stage); result.put("candidate", candidate); result.put("review", review);
        return result;
    }

    private static final class Flow {
        final ExecutionPlanSnapshot plan = ExecutionRegistryFixtures.videoOperationsEnabled(ExecutionRegistry.Environment.TEST)
                .freezePlan("video.episode_script_revise", true);
        final Map<String, Object> context = context();
        final List<VideoEpisodeScriptTransitions.Completed> history = new ArrayList<>();
        VideoEpisodeScriptTransitions.Decision decision = VideoEpisodeScriptTransitions.replay(plan, context, history);

        void complete(Map<String, Object> proposal, Map<String, Object> review) {
            history.add(new VideoEpisodeScriptTransitions.Completed("step-" + (history.size() + 1), "a".repeat(64),
                    decision.nextInput(), output((String) decision.nextInput().get("stageKey"), proposal, review)));
            decision = VideoEpisodeScriptTransitions.replay(plan, context, history);
        }
    }
}
