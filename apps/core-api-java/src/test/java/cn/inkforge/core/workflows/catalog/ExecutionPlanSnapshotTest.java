package cn.inkforge.core.workflows.catalog;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.workflows.domain.WorkflowBudgetExceededException;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.io.IOException;
import java.io.InputStream;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

class ExecutionPlanSnapshotTest {

    private static final String MANIFEST_FINGERPRINT =
            "aa9d1838a436ea5588ae034e4097fde419ca9e8300324443fb55a1f90c1d1fec";
    private final ObjectMapper json = new ObjectMapper();

    @Test
    void 冻结完整计划并绑定ManifestProfilePromptSchemaBudget与审核策略() {
        ExecutionRegistry registry =
                ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.TEST);
        ExecutionPlanSnapshot snapshot = registry.freezePlan(
                "long_serial.rewrite_chapter_selection", false);

        assertThat(checkedInManifestFingerprint()).isEqualTo(MANIFEST_FINGERPRINT);
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

    @Test
    void 既有十六项计划继续使用空系统步骤且旧重载哈希不变() {
        ExecutionRegistry registry =
                ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.TEST);
        List<String> operations = java.util.stream.Stream.of("long_serial", "short_medium")
                .flatMap(workflow -> registry.enabledOperationKeys(workflow, false).stream())
                .sorted()
                .toList();
        assertThat(operations).hasSize(16);
        for (String key : operations) {
            ExecutionRegistry.ResolvedOperation operation = registry.resolve(key, false);
            ExecutionPlanSnapshot original = ExecutionPlanSnapshot.freeze(
                    registry.catalogVersion(), registry.manifestFingerprint(), operation);
            ExecutionPlanSnapshot explicitEmpty = ExecutionPlanSnapshot.freeze(
                    registry.catalogVersion(), registry.manifestFingerprint(), operation, List.of());
            ExecutionPlanSnapshot current = registry.freezePlan(key, false);

            assertThat(current.systemSteps()).as(key).isEmpty();
            assertThat(current.stored()).as(key).isEqualTo(original.stored());
            assertThat(explicitEmpty.stored()).as(key).isEqualTo(original.stored());
            assertThat(ExecutionPlanSnapshot.fromStored(original.stored()).sha256())
                    .as(key).isEqualTo(original.sha256());
        }
    }

    @Test
    void 系统步骤按原计划版本冻结并可脱离当前目录完整恢复() {
        ExecutionRegistry registry =
                ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.TEST);
        ExecutionRegistry.ResolvedOperation operation =
                registry.resolve("long_serial.rewrite_chapter_selection", false);
        ExecutionPlanSnapshot.Step correction = systemStep(
                "protocol_correction", "system.test_protocol_corrector.v1");
        ExecutionPlanSnapshot frozen = ExecutionPlanSnapshot.freeze(
                registry.catalogVersion(), registry.manifestFingerprint(), operation, List.of(correction));

        assertThat(frozen.stored().get("planVersion")).isEqualTo("1");
        assertThat(frozen.systemSteps()).containsExactly(correction);
        ExecutionPlanSnapshot restored = ExecutionPlanSnapshot.fromStored(
                read(json.writeValueAsString(frozen.stored())));
        assertThat(restored.stored()).isEqualTo(frozen.stored());
        assertThat(restored.requireStep(
                correction.purpose(), correction.lane(), correction.modelProfile().profile(),
                correction.modelProfile().version(), correction.outputSchema().name(),
                correction.outputSchema().version(), correction.stepBudget().stored()))
                .isEqualTo(correction);
        assertThat(restored.requireStepProfile(correction.purpose(), correction.lane(),
                correction.modelProfile().profile(), correction.modelProfile().version()))
                .isEqualTo(correction.modelProfile());
        assertThatThrownBy(() -> restored.systemSteps().clear())
                .isInstanceOf(UnsupportedOperationException.class);
    }

    @ParameterizedTest
    @ValueSource(strings = {"generation", "review"})
    void 系统用途不能冒充生成或复审即使已重算快照哈希(String purpose) {
        Map<String, Object> stored = withSystems(List.of(
                systemStep(purpose, "system.test_protocol_corrector.v1")));

        assertThatThrownBy(() -> ExecutionPlanSnapshot.fromStored(stored))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("System Step purpose");
    }

    @Test
    void 系统用途不能重复且协议纠正不能冻结两份() {
        Map<String, Object> stored = withSystems(List.of(
                systemStep("protocol_correction", "system.test_protocol_corrector.v1"),
                systemStep("protocol_correction", "system.another_protocol_corrector.v1")));

        assertThatThrownBy(() -> ExecutionPlanSnapshot.fromStored(stored))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("System Step purpose 不能重复");
    }

    @ParameterizedTest
    @ValueSource(strings = {"writer.chapter_selection.v1", "reviewer.consistency.v1"})
    void 系统Profile不能复用生成或复审Profile(String profile) {
        Map<String, Object> stored = withSystems(List.of(systemStep("protocol_correction", profile)));

        assertThatThrownBy(() -> ExecutionPlanSnapshot.fromStored(stored))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("逻辑 Profile 不能重复");
    }

    @Test
    void 不同系统用途也不能重复逻辑Profile() {
        Map<String, Object> stored = withSystems(List.of(
                systemStep("summarize_evidence", "system.test_protocol_corrector.v1"),
                systemStep("protocol_correction", "system.test_protocol_corrector.v1")));

        assertThatThrownBy(() -> ExecutionPlanSnapshot.fromStored(stored))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("逻辑 Profile 不能重复");
    }

    @Test
    void Run未授权显式纠正时不能携带纠正Step() {
        Map<String, Object> stored = withSystems(List.of(
                systemStep("protocol_correction", "system.test_protocol_corrector.v1")));
        object(object(stored.get("plan")).get("runBudget")).put("maxProtocolCorrectionSteps", 0);
        rehash(stored);

        assertThatThrownBy(() -> ExecutionPlanSnapshot.fromStored(stored))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("protocol_correction");
    }

    @Test
    void 系统Step单次预算必须能装入Run预算() {
        Map<String, Object> stored = withSystems(List.of(
                systemStep("protocol_correction", "system.test_protocol_corrector.v1")));
        Map<String, Object> system = object(((List<?>) object(stored.get("plan"))
                .get("systemSteps")).getFirst());
        object(object(system.get("stepBudget")).get("budget")).put("maxInputTokens", 180_001);
        rehash(stored);

        assertThatThrownBy(() -> ExecutionPlanSnapshot.fromStored(stored))
                .isInstanceOf(WorkflowBudgetExceededException.class)
                .hasMessageContaining("INPUT_TOKENS");
    }

    @Test
    void 首轮生成复审和系统Step合计也必须装入Run调用与Token预算() {
        Map<String, Object> stored = withSystems(List.of(
                systemStep("protocol_correction", "system.test_protocol_corrector.v1")));
        Map<String, Object> budget = object(object(stored.get("plan")).get("runBudget"));
        budget.put("maxModelCalls", 3);
        rehash(stored);
        assertThatThrownBy(() -> ExecutionPlanSnapshot.fromStored(stored))
                .isInstanceOf(WorkflowBudgetExceededException.class)
                .hasMessageContaining("MODEL_CALLS");

        budget.put("maxModelCalls", 6);
        budget.put("maxInputTokens", 60_000);
        budget.put("maxPromptCacheMissTokens", 60_000);
        rehash(stored);
        assertThatThrownBy(() -> ExecutionPlanSnapshot.fromStored(stored))
                .isInstanceOf(WorkflowBudgetExceededException.class)
                .hasMessageContaining("INPUT_TOKENS");
    }

    private ExecutionPlanSnapshot.Step systemStep(String purpose, String profile) {
        ExecutionPlanSnapshot.Step reviewer = ExecutionRegistry
                .loadClasspath(ExecutionRegistry.Environment.TEST)
                .freezePlan("long_serial.rewrite_chapter_selection", false)
                .reviewers().getFirst();
        return new ExecutionPlanSnapshot.Step(
                purpose, reviewer.lane(), reviewer.evidencePolicy(),
                new ExecutionPlanSnapshot.ModelProfile(profile, 1,
                        reviewer.modelProfile().reasoningMode(),
                        reviewer.modelProfile().deploymentProfileKey(),
                        reviewer.modelProfile().promptProfile()),
                reviewer.outputSchema(), reviewer.stepBudget());
    }

    private Map<String, Object> withSystems(List<ExecutionPlanSnapshot.Step> systems) {
        ExecutionPlanSnapshot original = ExecutionRegistry
                .loadClasspath(ExecutionRegistry.Environment.TEST)
                .freezePlan("long_serial.rewrite_chapter_selection", false);
        Map<String, Object> stored = read(json.writeValueAsString(original.stored()));
        object(stored.get("plan")).put("systemSteps", systems.stream()
                .map(step -> read(json.writeValueAsString(step.toMap()))).toList());
        rehash(stored);
        return stored;
    }

    private static void rehash(Map<String, Object> stored) {
        stored.put("planSha256", ExecutionCanonicalJson.sha256(object(stored.get("plan"))));
    }

    private Map<String, Object> read(String value) {
        return json.readValue(value, new TypeReference<>() {});
    }

    private String checkedInManifestFingerprint() {
        try (InputStream input = ExecutionPlanSnapshotTest.class
                .getResourceAsStream("/agent-execution/manifest.json")) {
            if (input == null) throw new IllegalStateException("缺少当前 execution manifest 资源");
            Map<String, Object> manifest = json.readValue(input, new TypeReference<>() {});
            return ExecutionCanonicalJson.sha256(manifest);
        } catch (IOException exception) {
            throw new IllegalStateException("读取当前 execution manifest 失败", exception);
        }
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> object(Object value) {
        return (Map<String, Object>) value;
    }
}
