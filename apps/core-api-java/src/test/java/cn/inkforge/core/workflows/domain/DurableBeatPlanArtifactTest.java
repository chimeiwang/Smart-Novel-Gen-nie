package cn.inkforge.core.workflows.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class DurableBeatPlanArtifactTest {
    private static final String HASH = "a".repeat(64);

    @Test
    void 最小持久事实保留完整计划并确定性重建() {
        Map<String, Object> output = output();
        var stored = DurableBeatPlanArtifact.create("bundle", HASH, "chapter", output, "step", HASH);
        assertThat(stored.payload()).containsKeys("plan", "evidenceBundleId", "evidenceManifestSha256")
                .doesNotContainKeys("workspace", "sourceBindings", "candidate", "replacement");
        var rebuilt = DurableBeatPlanArtifact.reconstruct(stored.payload(), stored.diff(), "bundle", HASH, "chapter");
        assertThat(rebuilt.payload()).containsEntry("kind", "beat_plan");
        assertThat(rebuilt.payload().get("beatPlan")).isEqualTo(withoutHash(output));
        assertThat(rebuilt.diff()).containsEntry("after", withoutHash(output));
        assertThat(DurableBeatPlanArtifact.output(stored.payload())).isEqualTo(output);
    }

    @Test
    void 拒绝伪造派生哈希和顺序与额外字段() {
        for (String corruption : List.of("hash", "order", "count", "extra", "blank", "nelBlank", "nullCharacters")) {
            Map<String, Object> value = new LinkedHashMap<>(output());
            switch (corruption) {
                case "hash" -> value.put("contentSha256", HASH);
                case "order" -> value.put("sceneBeats", List.of(Map.of("order", 2, "goal", "完整😀目标")));
                case "count" -> value.put("beatCount", 2);
                case "extra" -> value.put("sourceId", "模型伪造来源");
                case "blank" -> value.put("chapterGoal", " \u3000");
                case "nelBlank" -> value.put("title", "\u0085");
                case "nullCharacters" -> {
                    Map<String, Object> scene = new LinkedHashMap<>(Map.of("order", 1, "goal", "合法目标"));
                    scene.put("characters", null);
                    value.put("sceneBeats", List.of(scene));
                }
                default -> throw new AssertionError();
            }
            if (!"hash".equals(corruption)) value.put("contentSha256", ExecutionCanonicalJson.sha256(withoutHash(value)));
            assertThatThrownBy(() -> DurableBeatPlanArtifact.create("bundle", HASH, "chapter", value, "step", HASH))
                    .isInstanceOf(IllegalArgumentException.class);
        }
    }

    @Test
    void 详情拒绝其他Evidence身份和损坏持久计划() {
        var stored = DurableBeatPlanArtifact.create("bundle", HASH, "chapter", output(), "step", HASH);
        assertThatThrownBy(() -> DurableBeatPlanArtifact.reconstruct(stored.payload(), stored.diff(), "other", HASH, "chapter"))
                .isInstanceOf(ApiException.class);
        Map<String, Object> corrupted = new LinkedHashMap<>(stored.payload());
        corrupted.put("plan", Map.of("title", "不完整计划"));
        assertThatThrownBy(() -> DurableBeatPlanArtifact.reconstruct(corrupted, stored.diff(), "bundle", HASH, "chapter"))
                .isInstanceOf(ApiException.class);
    }

    static Map<String, Object> output() {
        Map<String, Object> plan = new LinkedHashMap<>();
        plan.put("title", "完整标题");
        plan.put("summary", "保留完整摘要");
        plan.put("chapterGoal", "  保留原样的章节目标😀  ");
        plan.put("sceneBeats", List.of(Map.of("order", 1, "goal", "完整😀目标", "characters", List.of("角色甲"))));
        plan.put("beatCount", 1);
        plan.put("contentSha256", ExecutionCanonicalJson.sha256(plan));
        return plan;
    }

    private static Map<String, Object> withoutHash(Map<String, Object> output) {
        Map<String, Object> plan = new LinkedHashMap<>(output);
        plan.remove("contentSha256");
        return plan;
    }
}
