package cn.inkforge.core.workflows.catalog;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.LinkedHashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

class ExecutionPlanSnapshotTest {

    private static final String MANIFEST_FINGERPRINT =
            "9f718f00813210f321c74da7a44227c2abcdf10386ea870cd9a3836696667322";
    private final ObjectMapper json = new ObjectMapper();

    @Test
    void 冻结完整计划并绑定ManifestProfilePromptSchemaBudget与审核策略() {
        ExecutionRegistry registry =
                ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.TEST);
        ExecutionPlanSnapshot snapshot = registry.freezePlan(
                "long_serial.rewrite_chapter_selection", false);

        assertThat(registry.manifestFingerprint()).isEqualTo(MANIFEST_FINGERPRINT);
        assertThat(snapshot.executionManifestFingerprint()).isEqualTo(MANIFEST_FINGERPRINT);
        assertThat(snapshot.operationCatalogVersion()).isEqualTo(registry.catalogVersion());
        assertThat(snapshot.operation().key())
                .isEqualTo("long_serial.rewrite_chapter_selection");
        assertThat(snapshot.operation().applyHandler())
                .isEqualTo("apply.chapter_selection.v1");
        assertThat(snapshot.operation().deterministicValidators())
                .containsExactly(
                        "validator.schema_strict.v1",
                        "validator.unicode_selection.v1",
                        "validator.selection_source_hash.v1",
                        "validator.selection_outside_unchanged.v1");
        assertThat(snapshot.generator().modelProfile().promptProfile().name())
                .isEqualTo("prompt.writer.chapter_selection.v1");
        assertThat(snapshot.generator().outputSchema().jsonSchema()).isNotEmpty();
        assertThat(snapshot.generator().stepBudget().profile())
                .isEqualTo("step_budget.long_serial.rewrite_chapter_selection.generator.v1");
        assertThat(snapshot.reviewers())
                .extracting(step -> step.modelProfile().profile())
                .containsExactly("reviewer.consistency.v1", "reviewer.editorial.v1");
        assertThat(snapshot.reviewPolicy().rubricVersion())
                .isEqualTo("rubric.chapter_selection.review.v1");
        assertThat(snapshot.reviewPolicy().mergePolicy())
                .isEqualTo("review.merge_all_pass_else_author.v1");
        assertThat(snapshot.reviewPolicy().onUnavailable()).isEqualTo("awaiting_user");
        assertThat(snapshot.reviewPolicy().maxAutomaticRevisions()).isEqualTo(1);
        assertThat(snapshot.systemSteps()).isEmpty();

        String serialized = json.writeValueAsString(snapshot.stored());
        assertThat(serialized)
                .doesNotContain("systemPrompt")
                .doesNotContain("endpointProfile")
                .doesNotContain("apiKey")
                .doesNotContain("credential");
        assertThat(ExecutionPlanSnapshot.fromStored(read(serialized)).stored())
                .isEqualTo(snapshot.stored());
    }

    @Test
    void 快照形状或Canonical内容被篡改时拒绝解析() {
        ExecutionRegistry registry =
                ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.TEST);
        ExecutionPlanSnapshot snapshot = registry.freezePlan(
                "long_serial.rewrite_chapter_selection", false);
        Map<String, Object> changed = read(json.writeValueAsString(snapshot.stored()));
        Map<String, Object> plan = new LinkedHashMap<>(object(changed.get("plan")));
        plan.put("operationCatalogVersion", "changed");
        changed.put("plan", plan);

        assertThatThrownBy(() -> ExecutionPlanSnapshot.fromStored(changed))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("canonical SHA-256");

        Map<String, Object> unknown = read(json.writeValueAsString(snapshot.stored()));
        unknown.put("credentials", "forbidden");
        assertThatThrownBy(() -> ExecutionPlanSnapshot.fromStored(unknown))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("字段集合无效");
    }

    private Map<String, Object> read(String value) {
        return json.readValue(value, new TypeReference<>() {});
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> object(Object value) {
        return (Map<String, Object>) value;
    }
}
