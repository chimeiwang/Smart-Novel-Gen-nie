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

class VideoEpisodeStoryboardTransitionsTest {
    @Test
    void 局部修订由Core保留范围外镜头且终态只是候选() {
        Flow flow = new Flow();
        flow.complete(proposal("选中镜头新动作"), null);
        assertThat(flow.decision.nextInput())
                .containsEntry("stageKey", "episode_storyboard_review");
        flow.complete(null, review("pass"));

        assertThat(flow.decision.nextInput()).isNull();
        List<?> shots = (List<?>) flow.decision.document().get("shots");
        assertThat(((Map<?, ?>) shots.get(0)).get("action")).isEqualTo("选中镜头新动作");
        assertThat(((Map<?, ?>) shots.get(1)).get("action")).isEqualTo("范围外动作");
        assertThat(flow.decision.document())
                .doesNotContainKeys("currentStoryboardVersionId", "currentProductionBaselineId");
    }

    @Test
    void 审片最多自动返工一次且第二轮问题交作者() {
        Flow flow = new Flow();
        flow.complete(proposal("第一稿"), null);
        flow.complete(null, review("revise"));
        assertThat(flow.decision.nextInput()).containsEntry("cycle", 1);
        assertThat((List<?>) flow.decision.nextInput().get("dependencies")).hasSize(2);
        flow.complete(proposal("第二稿"), null);
        flow.complete(null, review("revise"));

        assertThat(flow.history).hasSize(4);
        assertThat(flow.decision.nextInput()).isNull();
        assertThat(flow.decision.review()).containsEntry("decision", "revise");
    }

    @Test
    void 模型不能返回范围外镜头或切换真实执行() {
        Map<String, Object> scopeWrong = proposal("越权");
        scopeWrong.put("shots", List.of(proposalShot("shot-2", "越权")));
        assertThatThrownBy(() -> VideoEpisodeStoryboardDocuments.merge(context(), scopeWrong))
                .hasMessageContaining("恰好包含");

        Map<String, Object> shot = proposalShot("shot-1", "切换 live");
        Map<String, Object> intent = new LinkedHashMap<>((Map<String, Object>) shot.get("productionIntent"));
        intent.put("executionMode", "live");
        intent.put("feeConfirmed", true);
        shot.put("productionIntent", intent);
        Map<String, Object> wrong = new LinkedHashMap<>();
        wrong.put("shots", List.of(shot));
        Map<String, Object> finalWrong = wrong;
        assertThatThrownBy(() -> VideoEpisodeStoryboardDocuments.merge(context(), finalWrong))
                .hasMessageContaining("执行参数");
    }

    @Test
    void 审片问题必须定位真实镜头或正式剧本场次() {
        Map<String, Object> document = VideoEpisodeStoryboardDocuments.merge(
                context(), proposal("修订动作"));
        Map<String, Object> finding = Map.of(
                "code", "shot_clarity",
                "shotId", "foreign-shot",
                "scriptSceneId", "scene-1",
                "message", "动作不清楚");
        Map<String, Object> review = Map.of(
                "decision", "pass",
                "summary", "有建议",
                "requiredChanges", List.of(),
                "findings", List.of(finding));

        assertThatThrownBy(() ->
                        VideoEpisodeStoryboardDocuments.validateReview(context(), document, review))
                .hasMessageContaining("不存在");
    }

    private static Map<String, Object> context() {
        Map<String, Object> script = Map.of(
                "schemaVersion", "video-episode-script/1.0",
                "overview", Map.of(),
                "scenes", List.of(scriptScene("scene-1", "line-1"), scriptScene("scene-2", "line-2")),
                "endingStates", List.of(),
                "dependencies", List.of());
        Map<String, Object> draft = Map.of(
                "schemaVersion", "video-episode-storyboard/1.0",
                "shots", List.of(frozenShot("shot-1", "scene-1", "line-1", "原动作"),
                        frozenShot("shot-2", "scene-2", "line-2", "范围外动作")));
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("operation", "episode_storyboard_revise");
        result.put("draft", draft);
        result.put("script", script);
        result.put("stableShotIds", List.of("shot-1", "shot-2"));
        result.put("selectedShotIds", List.of("shot-1"));
        result.put("productionDefaults", defaults());
        result.put("availableReferences", List.of(referenceEvidence()));
        return result;
    }

    private static Map<String, Object> proposal(String action) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("shots", List.of(proposalShot("shot-1", action)));
        return result;
    }

    private static Map<String, Object> proposalShot(String id, String action) {
        String suffix = id.endsWith("2") ? "2" : "1";
        Map<String, Object> shot = new LinkedHashMap<>();
        shot.put("id", id);
        shot.put("tempKey", null);
        shot.put("lineage", List.of());
        shot.put("scriptSceneId", "scene-" + suffix);
        shot.put("scriptLineIds", List.of("line-" + suffix));
        shot.put("title", "镜头");
        shot.put("action", action);
        shot.put("framing", "medium");
        shot.put("cameraMovement", "static");
        shot.put("durationMs", 6000);
        Map<String, Object> intent = new LinkedHashMap<>(defaults());
        intent.put("prompt", action);
        intent.put("durationSeconds", 6);
        intent.put("references", List.of(Map.of("canonVersionId", "canon-v1")));
        shot.put("productionIntent", intent);
        return shot;
    }

    private static Map<String, Object> frozenShot(
            String id, String sceneId, String lineId, String action) {
        Map<String, Object> shot = proposalShot(id, action);
        shot.put("scriptSceneId", sceneId);
        shot.put("scriptLineIds", List.of(lineId));
        Map<String, Object> intent = new LinkedHashMap<>((Map<String, Object>) shot.get("productionIntent"));
        intent.put("references", List.of(Map.of(
                "ordinal", 1,
                "canonVersionId", "canon-v1",
                "canonContentHash", "1".repeat(64),
                "assetId", "asset-v1",
                "sha256", "2".repeat(64),
                "mimeType", "image/png",
                "duty", "identity",
                "strength", 70)));
        shot.put("productionIntent", intent);
        return shot;
    }

    private static Map<String, Object> scriptScene(String sceneId, String lineId) {
        Map<String, Object> line = new LinkedHashMap<>();
        line.put("id", lineId);
        line.put("tempKey", null);
        line.put("kind", "action");
        line.put("speakerId", null);
        line.put("text", "动作");
        line.put("sourceRefs", List.of());
        Map<String, Object> scene = new LinkedHashMap<>();
        scene.put("id", sceneId);
        scene.put("tempKey", null);
        scene.put("title", "场次");
        scene.put("locationLabel", "室内");
        scene.put("timeLabel", "夜");
        scene.put("narrativeTime", "当晚");
        scene.put("characterIds", List.of());
        scene.put("lines", List.of(line));
        return scene;
    }

    private static Map<String, Object> defaults() {
        return Map.of(
                "provider", "seedance",
                "model", "doubao-seedance-2-5-260628",
                "generationMode", "reference",
                "executionMode", "simulated",
                "feeConfirmed", false,
                "ratio", "9:16",
                "resolution", "720p",
                "generateAudio", true,
                "watermark", false,
                "outputFormat", "mp4");
    }

    private static Map<String, Object> referenceEvidence() {
        return Map.of(
                "canonVersionId", "canon-v1",
                "canonContentHash", "1".repeat(64),
                "assetId", "asset-v1",
                "sha256", "2".repeat(64),
                "mimeType", "image/png",
                "duty", "identity",
                "defaultStrength", 70,
                "settingName", "林岚",
                "label", "常服");
    }

    private static Map<String, Object> review(String decision) {
        return Map.of(
                "decision", decision,
                "summary", "审片结论",
                "requiredChanges", "revise".equals(decision) ? List.of("具体问题") : List.of(),
                "findings", List.of());
    }

    private static Map<String, Object> output(
            String stage, Map<String, Object> candidate, Map<String, Object> review) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("stageKey", stage);
        result.put("candidate", candidate);
        result.put("review", review);
        return result;
    }

    private static final class Flow {
        final ExecutionPlanSnapshot plan = ExecutionRegistryFixtures
                .videoOperationsEnabled(ExecutionRegistry.Environment.TEST)
                .freezePlan("video.episode_storyboard_revise", true);
        final Map<String, Object> context = context();
        final List<VideoEpisodeStoryboardTransitions.Completed> history = new ArrayList<>();
        VideoEpisodeStoryboardTransitions.Decision decision =
                VideoEpisodeStoryboardTransitions.replay(plan, context, history);

        void complete(Map<String, Object> proposal, Map<String, Object> review) {
            history.add(new VideoEpisodeStoryboardTransitions.Completed(
                    "step-" + (history.size() + 1),
                    "a".repeat(64),
                    decision.nextInput(),
                    output((String) decision.nextInput().get("stageKey"), proposal, review)));
            decision = VideoEpisodeStoryboardTransitions.replay(plan, context, history);
        }
    }
}
