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
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import java.util.stream.Stream;

class VideoStageTransitionsTest {
    @Test
    void 正常三阶段产物与审镜发现完整交作者且不创建通用复审() {
        Flow flow = new Flow(false, null);
        flow.complete("ready", Map.of("checkpoint", checkpoint()));
        flow.complete("ready", Map.of("candidate", Map.of("sourceHash", "a".repeat(64), "scenes", List.of("完整镜头"))));
        flow.complete("ready", Map.of("review", review("pass")));
        assertThat(flow.decision.candidate()).containsEntry("reviewSummary", "完整审镜结论")
                .containsEntry("reviewFindings", List.of(Map.of("description", "交作者核对")));
        assertThat(flow.decision.nextInput()).isNull();
        assertThat(flow.plan.reviewers()).isEmpty();
        assertThat(flow.history).hasSize(3);
    }

    @Test
    void 原有十次上界独立计算分析纠正设计重做补槽和审镜返工() {
        Flow flow = new Flow(false, null);
        flow.fail(VideoStageTransitions.CORRECTION_REQUIRED, true);
        assertThat(flow.decision.nextInput()).containsEntry("correction", true);
        flow.complete("ready", Map.of("checkpoint", checkpoint()));
        flow.supplement();
        flow.complete("needs_correction", Map.of("validationFindings", findings()));
        assertThat(flow.decision.nextInput()).containsEntry("stageKey", "shot_design").containsEntry("correction", true);
        flow.supplement();
        flow.complete("ready", Map.of("candidate", Map.of("scenes", List.of("全量候选"))));
        flow.complete("ready", Map.of("review", review("revise")));
        assertThat(flow.decision.nextInput()).containsEntry("cycle", 1).containsEntry("correction", false);
        flow.supplement();
        flow.complete("ready", Map.of("candidate", Map.of("scenes", List.of("返工全量候选"))));
        flow.complete("ready", Map.of("review", review("revise")));
        assertThat(flow.history).hasSize(10);
        assertThat(flow.decision.errorCode()).isNull();
        assertThat(flow.decision.candidate()).containsEntry("scenes", List.of("返工全量候选"));
        assertThat(flow.decision.nextInput()).isNull();
    }

    @Test
    void 补槽自身协议失败不能被解释为物化纠正() {
        Flow flow = new Flow(false, checkpoint());
        flow.supplement();
        flow.fail(VideoStageTransitions.CORRECTION_REQUIRED, true);
        assertThat(flow.decision.nextInput()).isNull();
        assertThat(flow.decision.errorCode()).isEqualTo(VideoStageTransitions.CORRECTION_REQUIRED);
        assertThat(flow.history).hasSize(2);
    }

    @Test
    void 已继承检查点从设计开始且原始来源永不重调分析() {
        Map<String, Object> checkpoint = checkpoint();
        Flow flow = new Flow(false, checkpoint);
        assertThat(flow.decision.nextInput()).containsEntry("stageKey", "shot_design")
                .containsEntry("checkpoint", checkpoint).containsEntry("dependencies", List.of());
    }

    @Test
    void 提示词只有一次完整批次纠正且第二次硬错误结束() {
        Flow flow = new Flow(true, null);
        flow.complete("needs_correction", Map.of("validationFindings", findings()));
        assertThat(flow.decision.nextInput()).containsEntry("stageKey", "shot_prompt").containsEntry("correction", true);
        flow.complete("needs_correction", Map.of("validationFindings", findings()));
        assertThat(flow.decision.errorCode()).isEqualTo("VIDEO_STAGE_CORRECTION_EXHAUSTED");
        assertThat(flow.history).hasSize(2);
    }

    @Test
    void 未知用量不会因已解析错误获得额外调用() {
        Flow flow = new Flow(true, null);
        flow.add(flow.output("needs_correction", Map.of("validationFindings", findings())), null, false);
        assertThat(flow.decision.nextInput()).isNull();
        assertThat(flow.decision.errorCode()).isEqualTo("VIDEO_STAGE_CORRECTION_EXHAUSTED");
    }

    @Test
    void 前序依赖缺失或被替换必须拒绝即使当前候选看似合法() {
        Flow flow = new Flow(true, null);
        flow.complete("needs_correction", Map.of("validationFindings", findings()));
        Map<String, Object> changed = new LinkedHashMap<>(flow.decision.nextInput());
        changed.put("dependencies", List.of());
        flow.history.add(new VideoStageTransitions.Completed("s2", "b".repeat(64), changed,
                Map.of("stageKey", "shot_prompt", "outcome", "ready", "promptBatch", Map.of("prompts", List.of("完整批次"))), null, true));
        assertThatThrownBy(() -> VideoStageTransitions.replay(flow.plan, flow.context, flow.history))
                .isInstanceOf(IllegalStateException.class).hasMessageContaining("前序结果");
    }

    @Test
    void 原契约允许的空格审镜摘要必须原样完成() {
        Flow flow = reviewFlow();
        Map<String, Object> review = new LinkedHashMap<>(review("pass"));
        review.put("summary", " \t ");
        flow.complete("ready", Map.of("review", review));
        assertThat(flow.decision.candidate()).containsEntry("reviewSummary", " \t ");
        assertThat(flow.decision.errorCode()).isNull();
    }

    @Test
    void 输出包络不能把可用产物与结构纠正或部分设计混合() {
        Flow dramatic = new Flow(false, null);
        assertThatThrownBy(() -> dramatic.complete("ready", Map.of("checkpoint", checkpoint(), "validationFindings", findings())))
                .isInstanceOf(IllegalStateException.class).hasMessageContaining("纠正发现");
        Flow design = new Flow(false, checkpoint());
        assertThatThrownBy(() -> design.complete("ready", Map.of("candidate", Map.of("scenes", List.of()),
                "design", design(), "missingBeatKeys", List.of("B02", "B03"))))
                .isInstanceOf(IllegalStateException.class).hasMessageContaining("候选、缺槽");
        Flow supplement = new Flow(false, checkpoint());
        supplement.supplement();
        assertThatThrownBy(() -> supplement.complete("needs_correction", Map.of("candidate", Map.of("scenes", List.of()),
                "validationFindings", findings())))
                .isInstanceOf(IllegalStateException.class).hasMessageContaining("产物或纠正");
        Flow prompt = new Flow(true, null);
        assertThatThrownBy(() -> prompt.complete("ready", Map.of("promptBatch", Map.of("prompts", List.of()),
                "validationFindings", findings())))
                .isInstanceOf(IllegalStateException.class).hasMessageContaining("硬错误");
    }

    @Test
    void 审镜通过不得夹带返工要求且返工必须给出具体要求() {
        for (String verdict : List.of("pass", "revise")) {
            Flow flow = reviewFlow();
            Map<String, Object> review = new LinkedHashMap<>(review(verdict));
            review.put("requiredChanges", "pass".equals(verdict) ? List.of("矛盾返工要求") : List.of());
            assertThatThrownBy(() -> flow.complete("ready", Map.of("review", review)))
                    .isInstanceOf(IllegalStateException.class).hasMessageContaining("审镜决定与返工要求");
        }
    }

    @Test
    void 补槽必须完整且按检查点顺序精确列出真实空槽() {
        for (List<String> missing : List.of(List.of("B02"), List.of("B03", "B02"), List.of("B02", "B02", "B03"))) {
            Flow flow = new Flow(false, checkpoint());
            assertThatThrownBy(() -> flow.complete("needs_supplement", Map.of("design", design(), "missingBeatKeys", missing)))
                    .isInstanceOf(IllegalStateException.class).hasMessageContaining("有序缺槽集合");
        }
        Flow extra = new Flow(false, checkpoint());
        Map<String, Object> slots = new LinkedHashMap<>(Map.of("B01", List.of(shot()), "B04", List.of(shot())));
        assertThatThrownBy(() -> extra.complete("needs_supplement", Map.of("design", Map.of("beatsByKey", slots,
                "suggestedEpisodeBreakAfterShotNumbers", List.of()), "missingBeatKeys", List.of("B02", "B03"))))
                .isInstanceOf(IllegalStateException.class).hasMessageContaining("检查点之外");
        Flow valid = new Flow(false, checkpoint());
        valid.supplement();
        assertThat(valid.decision.nextInput()).containsEntry("missingBeatKeys", List.of("B02", "B03"));
    }

    @Test
    void 提示词可用结果继续允许非阻断发现而不升级为质量门禁() {
        Flow flow = new Flow(true, null);
        Map<String, Object> warning = new LinkedHashMap<>();
        warning.put("code", "prompt_metadata"); warning.put("shotKey", "S01");
        warning.put("parameters", Map.of()); warning.put("blocking", false);
        flow.complete("ready", Map.of("promptBatch", Map.of("prompts", List.of("完整批次")), "validationFindings", List.of(warning)));
        assertThat(flow.decision.promptBatch()).containsEntry("prompts", List.of("完整批次"));
        assertThat(flow.decision.errorCode()).isNull();
    }

    @ParameterizedTest
    @MethodSource("invalidFindings")
    void 验证发现的参数形状与镜号范围必须匹配其固定错误码(String code, Map<String, Object> parameters,
            String shotKey, boolean blocking) {
        Flow flow = new Flow(true, null);
        Map<String, Object> finding = new LinkedHashMap<>();
        finding.put("code", code); finding.put("parameters", parameters);
        finding.put("shotKey", shotKey); finding.put("blocking", blocking);
        assertThatThrownBy(() -> flow.complete("needs_correction", Map.of("validationFindings", List.of(finding))))
                .isInstanceOf(IllegalStateException.class).hasMessageContaining("视频验证发现");
    }

    private static Stream<Arguments> invalidFindings() {
        return Stream.of(
                Arguments.of("prompt_budget", Map.of(), "S01", true),
                Arguments.of("prompt_action_count", Map.of("actual", 2, "maximum", 1), "S01", true),
                Arguments.of("prompt_scale", Map.of("effects", List.of("火花")), "S01", false),
                Arguments.of("prompt_effects", Map.of("markers", List.of("打开")), "S01", false),
                Arguments.of("prompt_affirmative_effects", Map.of(), "S01", false),
                Arguments.of("prompt_unconfirmed_action", Map.of("fields", List.of("camera", "audio")), "S01", false),
                Arguments.of("prompt_repeated_fields", Map.of("effects", List.of("火花")), "S01", false),
                Arguments.of("prompt_metadata", Map.of("actual", 2, "maximum", 1), "S01", false),
                Arguments.of("protocol_invalid", Map.of(), "S01", true),
                Arguments.of("dramatic_protocol", Map.of(), null, false),
                Arguments.of("prompt_budget", Map.of("actual", 2, "maximum", 1), null, true));
    }

    private static Flow reviewFlow() {
        Flow flow = new Flow(false, checkpoint());
        flow.complete("ready", Map.of("candidate", Map.of("scenes", List.of("完整候选"))));
        return flow;
    }

    private static Map<String, Object> review(String decision) {
        return Map.of("decision", decision, "summary", "完整审镜结论", "requiredChanges", "revise".equals(decision) ? List.of("完整返工要求") : List.of(),
                "findings", List.of(Map.of("description", "交作者核对")));
    }

    private static List<Map<String, Object>> findings() {
        Map<String, Object> finding = new LinkedHashMap<>();
        finding.put("code", "design_materialization"); finding.put("shotKey", null);
        finding.put("parameters", Map.of()); finding.put("blocking", true);
        return List.of(finding);
    }

    private static Map<String, Object> checkpoint() {
        List<Map<String, Object>> beats = new ArrayList<>();
        for (int index = 1; index <= 3; index++) beats.add(Map.of("beatKey", "B0" + index, "title", "节拍" + index,
                "sourceUnitIds", List.of("U01"), "dramaticTurn", "发现事实", "visualStrategy", "呈现动作",
                "coverageGoals", List.of(Map.of("goalKey", "G0" + index, "kind", "story_information", "priority", "essential", "description", "展示事实"))));
        return Map.of("schemaVersion", "dramatic_structure_v3", "scenes", List.of(Map.of("sceneKey", "SC01", "title", "完整场景",
                "locationLabel", "室内", "timeLabel", "夜", "objective", "发现真相", "changeSummary", "得到答案", "beats", beats)));
    }

    private static Map<String, Object> design() {
        return Map.of("beatsByKey", Map.of("B01", List.of(shot())), "suggestedEpisodeBreakAfterShotNumbers", List.of());
    }

    private static Map<String, Object> shot() {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("title", "完整已有镜头"); value.put("narrativePurpose", "action"); value.put("storyFunction", "揭示动作");
        value.put("audienceGain", "看到门打开"); value.put("coveredGoalKeys", List.of("G01")); value.put("sourceRelation", "direct");
        value.put("shotScale", "medium"); value.put("cameraAngle", "eye_level"); value.put("cameraMovement", "locked");
        value.put("visualIntent", "人物打开门"); value.put("speechMode", "none"); value.put("spokenText", null);
        value.put("soundDesign", "门轴声"); value.put("cutReason", "门开启后显露新的空间"); value.put("timelineDurationMs", 5000);
        value.put("sourceUnitIds", List.of("U01")); return value;
    }

    private static final class Flow {
        private final ExecutionPlanSnapshot plan;
        private final Map<String, Object> context = new LinkedHashMap<>();
        private final List<VideoStageTransitions.Completed> history = new ArrayList<>();
        private VideoStageTransitions.Decision decision;

        Flow(boolean prompt, Map<String, Object> checkpoint) {
            plan = ExecutionRegistryFixtures.videoOperationsEnabled(ExecutionRegistry.Environment.TEST).freezePlan(
                    prompt ? "video.chapter_shot_prompt_v2" : "video.chapter_cinematic_adaptation_v2", true);
            context.put("inheritedCheckpoint", checkpoint);
            decision = VideoStageTransitions.replay(plan, context, history);
        }

        void supplement() {
            complete("needs_supplement", Map.of("design", design(), "missingBeatKeys", List.of("B02", "B03")));
        }

        void complete(String outcome, Map<String, Object> fields) {
            add(output(outcome, fields), null, true);
        }

        Map<String, Object> output(String outcome, Map<String, Object> fields) {
            String stage = (String) decision.nextInput().get("stageKey");
            Map<String, Object> output = new LinkedHashMap<>();
            output.put("stageKey", stage); output.put("outcome", outcome); output.put("validationFindings", List.of());
            switch (stage) {
                case "dramatic_structure" -> output.put("checkpoint", null);
                case "shot_design" -> { output.put("design", null); output.put("candidate", null); output.put("missingBeatKeys", List.of()); }
                case "missing_beat_shots" -> output.put("candidate", null);
                case "cinematic_review" -> output.put("review", null);
                case "shot_prompt" -> output.put("promptBatch", null);
                default -> throw new IllegalArgumentException("未知测试阶段");
            }
            output.putAll(fields); return output;
        }

        void fail(String code, boolean allowed) { add(null, code, allowed); }

        void add(Map<String, Object> output, String code, boolean allowed) {
            history.add(new VideoStageTransitions.Completed("step" + (history.size() + 1),
                    Integer.toHexString(history.size() + 1).repeat(64), decision.nextInput(), output, code, allowed));
            decision = VideoStageTransitions.replay(plan, context, history);
        }
    }
}
