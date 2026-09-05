package cn.inkforge.core.workflows.catalog;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

class VideoExecutionPlanSnapshotTest {
    private final ObjectMapper json = new ObjectMapper();

    @Test
    void 四阶段分别冻结完整身份并可离线恢复() {
        var plan = registry().freezePlan("video.chapter_cinematic_adaptation_v2", true);
        assertThat(plan.stageSteps()).extracting(ExecutionPlanSnapshot.StageStep::stageKey)
                .containsExactly("dramatic_structure", "shot_design", "missing_beat_shots", "cinematic_review");
        assertThat(plan.stageSteps()).extracting(ExecutionPlanSnapshot.StageStep::maxInvocations).containsExactly(2, 3, 3, 2);
        assertThat(plan.generator()).isEqualTo(plan.stageSteps().getFirst().step());
        assertThat(plan.reviewers()).isEmpty();
        assertThat(plan.systemSteps()).isEmpty();
        var restored = ExecutionPlanSnapshot.fromStored(copy(plan.stored()));
        assertThat(restored.stored()).isEqualTo(plan.stored());
        for (var stage : restored.stageSteps()) {
            var step = stage.step();
            assertThat(restored.requireStep("generation", step.lane(), step.modelProfile().profile(), step.modelProfile().version(),
                    step.outputSchema().name(), step.outputSchema().version(), step.stepBudget().stored())).isEqualTo(step);
            assertThat(restored.requireStepProfile("generation", step.lane(), step.modelProfile().profile(), step.modelProfile().version()))
                    .isEqualTo(step.modelProfile());
        }
    }

    @Test
    void 历史十九项不添加可选字段且不更改快照哈希() {
        var registry = registry();
        for (String workflow : List.of("long_serial", "short_medium", "quality", "style", "rag")) {
            for (String operation : registry.enabledOperationKeys(workflow, false)) {
                var plan = registry.freezePlan(operation, false);
                assertThat(plan.stageSteps()).isEmpty();
                assertThat(plan.videoStagePolicy()).isNull();
                assertThat(copy(plan.stored()).get("plan").toString()).doesNotContain("stageSteps", "videoStagePolicy");
                assertThat(ExecutionPlanSnapshot.fromStored(copy(plan.stored())).sha256()).isEqualTo(plan.sha256());
            }
        }
    }

    @Test
    void 重算哈希也不能增添节点放大次数或把电影化审镜变成通用Reviewer() {
        var original = registry().freezePlan("video.chapter_cinematic_adaptation_v2", true);
        for (String mutation : List.of("count", "order", "policy", "missing")) {
            Map<String, Object> root = copy(original.stored());
            Map<String, Object> plan = object(root.get("plan"));
            var stages = new ArrayList<>((List<?>) plan.get("stageSteps"));
            if (mutation.equals("count")) object(stages.getFirst()).put("maxInvocations", 3);
            if (mutation.equals("order")) java.util.Collections.swap(stages, 0, 1);
            if (mutation.equals("missing")) stages.removeLast();
            if (mutation.equals("policy")) plan.put("videoStagePolicy", VideoStagePolicy.PROMPT);
            plan.put("stageSteps", stages);
            root.put("planSha256", ExecutionCanonicalJson.sha256(plan));
            assertThatThrownBy(() -> ExecutionPlanSnapshot.fromStored(root)).as(mutation).isInstanceOf(IllegalStateException.class);
        }
    }

    @Test
    void 非视频计划不能偷带阶段且残缺扩展必须拒绝() {
        var original = registry().freezePlan("long_serial.answer_question", false);
        Map<String, Object> root = copy(original.stored());
        Map<String, Object> plan = object(root.get("plan"));
        plan.put("stageSteps", List.of());
        root.put("planSha256", ExecutionCanonicalJson.sha256(plan));
        assertThatThrownBy(() -> ExecutionPlanSnapshot.fromStored(root)).hasMessageContaining("字段集合");
        plan.put("videoStagePolicy", VideoStagePolicy.PROMPT);
        root.put("planSha256", ExecutionCanonicalJson.sha256(plan));
        assertThatThrownBy(() -> ExecutionPlanSnapshot.fromStored(root)).hasMessageContaining("不匹配");
    }

    private static ExecutionRegistry registry() { return ExecutionRegistryFixtures.videoOperationsEnabled(ExecutionRegistry.Environment.TEST); }
    private Map<String, Object> copy(Map<String, Object> value) { return json.readValue(json.writeValueAsString(value), new TypeReference<>() {}); }
    @SuppressWarnings("unchecked")
    private static Map<String, Object> object(Object value) { return (Map<String, Object>) value; }
}
