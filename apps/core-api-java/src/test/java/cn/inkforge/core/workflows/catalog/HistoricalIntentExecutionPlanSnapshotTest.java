package cn.inkforge.core.workflows.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.io.InputStream;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** 验证已持久化的 94a5298 三项自然入口计划不依赖当前 Registry 仍可恢复。 */
class HistoricalIntentExecutionPlanSnapshotTest {

    private static final String SOURCE_COMMIT =
            "94a5298e717f4a8f7dd760d9f8ef1f44d3f3dc03";
    private static final String HISTORICAL_MANIFEST =
            "7405feccad1c014edbae8833ce260e2db67772b96d90d2814af9892203382142";
    private static final String FIXTURE_SHA256 =
            "00cdb1dd3ccadf463d18fa8016238eabcf4b5d7032841bd348feb4c0335684dd";
    private static final String PLAN_SHA256 =
            "b31f1ad36c5111d1171595ec2c8769599348d2da8e286fb0f572a161c6238137";
    private static final List<String> OPERATIONS = List.of(
            "long_serial.answer_question",
            "long_serial.plan_chapter",
            "long_serial.write_chapter");
    private static final List<String> CHILD_PLAN_SHA256 = List.of(
            "92af2c1c3e5df13e6b72b0905332b9414be7b69418dcd7538f7ead7c20a05c79",
            "26e52998a2448f62a965e40687d8a3203c7968dccc96915ac2ff0daab1bcc483",
            "bdc35685a67c869434a0402d75597a5c5f22412273bd0ffcb1121f8fbbe7f8d8");

    private final ObjectMapper json = new ObjectMapper();

    @Test
    void 从历史literal恢复原计划哈希三项操作及全部预算维度() throws IOException {
        Fixture fixture = fixture();

        assertThat(fixture.sourceCommit()).isEqualTo(SOURCE_COMMIT);
        assertThat(fixture.historicalManifestSha256()).isEqualTo(HISTORICAL_MANIFEST);
        IntentExecutionPlanSnapshot restored =
                IntentExecutionPlanSnapshot.fromStored(fixture.snapshot());

        assertThat(restored.sha256()).isEqualTo(PLAN_SHA256);
        assertThat(restored.operationCatalogVersion()).isEqualTo("1");
        assertThat(restored.executionManifestFingerprint()).isEqualTo(HISTORICAL_MANIFEST);
        assertThat(restored.operationPlans())
                .extracting(plan -> plan.operation().key())
                .containsExactlyElementsOf(OPERATIONS);
        assertThat(restored.operationPlans())
                .extracting(ExecutionPlanSnapshot::sha256)
                .containsExactlyElementsOf(CHILD_PLAN_SHA256);
        assertThat(restored.operationPlans())
                .extracting(ExecutionPlanSnapshot::executionManifestFingerprint)
                .containsOnly(HISTORICAL_MANIFEST);
        assertThat(restored.runBudget()).isEqualTo(new ExecutionRegistry.RunBudget(
                "budget.long_serial.natural.v1",
                9,
                204_000,
                204_000,
                43_000,
                16_000,
                27_000,
                2_150_000,
                990,
                2,
                1));
        assertThat(restored.operationPlans())
                .extracting(ExecutionPlanSnapshot::runBudget)
                .containsExactly(
                        new ExecutionRegistry.RunBudget(
                                "budget.long_serial.answer.v1",
                                1, 40_000, 20_000, 8_000, 0, 8_000, 300_000, 120, 2, 1),
                        new ExecutionRegistry.RunBudget(
                                "budget.long_serial.chapter_plan.v1",
                                4, 120_000, 120_000, 20_000, 12_000, 8_000, 800_000, 480, 2, 1),
                        new ExecutionRegistry.RunBudget(
                                "budget.long_serial.chapter_draft.v1",
                                6, 180_000, 180_000, 40_000, 16_000, 24_000, 2_000_000, 900, 2, 1));
    }

    @Test
    void 历史向量固定真实ProfilePromptSchema与StepBudget而不读取当前Registry() throws IOException {
        IntentExecutionPlanSnapshot restored =
                IntentExecutionPlanSnapshot.fromStored(fixture().snapshot());

        assertThat(restored.resolver().modelProfile().profile())
                .isEqualTo("system.intent_resolver.v1");
        assertThat(restored.resolver().modelProfile().promptProfile().sha256())
                .isEqualTo("4ebf30f06de85e21db42275f10e88a9ce309ee037dfebfd0fc921bfc77796f63");
        assertThat(restored.resolver().outputSchema().sha256())
                .isEqualTo("d01c3444cfd4da13d9df6fe5dee58dfe5a75c413ad89ac28a766d18f6e8bde25");
        assertThat(restored.resolver().stepBudget().profile())
                .isEqualTo("step_budget.system.resolve_intent.v1");

        assertThat(restored.operationPlans())
                .extracting(plan -> plan.generator().modelProfile().profile())
                .containsExactly("editor.answer.v1", "plot.chapter_plan.v1", "writer.chapter_draft.v1");
        assertThat(restored.operationPlans())
                .extracting(plan -> plan.generator().modelProfile().promptProfile().sha256())
                .containsExactly(
                        "f258523852408facd24f6a90d2a1806c5bbcc08dd7895d8f50e2928acd055fa5",
                        "89b4b735b17aaba78fb800c3c02257c6adc0915beac9e37cb39adee939a13576",
                        "e4498a0652bc623fecd12ba27a4297ae962d6d7352ab8199064100ba6649aadb");
        assertThat(restored.operationPlans())
                .extracting(plan -> plan.generator().outputSchema().sha256())
                .containsExactly(
                        "aa3eb62823c66c739cbee6227e67c099c170b99478358e0003003816f87eed70",
                        "711ef3169c19c540e5ac2dd7a25da87d510cc527fadf33b6331929a19f2be0cd",
                        "ed5217b26afed3daa41ed790672bd720e6b451a382801a877a2a484e68016a84");
        assertThat(restored.operationPlans())
                .extracting(plan -> plan.generator().stepBudget().profile())
                .containsExactly(
                        "step_budget.long_serial.answer_question.generator.v1",
                        "step_budget.long_serial.plan_chapter.generator.v1",
                        "step_budget.long_serial.write_chapter.generator.v1");
        assertThat(restored.operationPlans().stream()
                        .flatMap(plan -> plan.reviewers().stream())
                        .map(step -> step.modelProfile().profile()))
                .containsExactly(
                        "reviewer.chapter_plan_editorial.v1",
                        "reviewer.chapter_draft_consistency.v1",
                        "reviewer.chapter_draft_editorial.v1");
    }

    private Fixture fixture() throws IOException {
        byte[] bytes;
        try (InputStream stream = HistoricalIntentExecutionPlanSnapshotTest.class.getResourceAsStream(
                "/historical-fixtures/intent-execution-plan-94a5298.json")) {
            assertThat(stream).as("历史冻结向量资源").isNotNull();
            bytes = stream.readAllBytes();
        }
        assertThat(sha256(bytes)).isEqualTo(FIXTURE_SHA256);
        Map<String, Object> root = json.readValue(bytes, new TypeReference<>() {});
        assertThat(root).containsOnlyKeys("sourceCommit", "historicalManifestSha256", "snapshot");
        return new Fixture(
                (String) root.get("sourceCommit"),
                (String) root.get("historicalManifestSha256"),
                object(root.get("snapshot")));
    }

    private static String sha256(byte[] value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("JVM 缺少 SHA-256", exception);
        }
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> object(Object value) {
        return (Map<String, Object>) value;
    }

    private record Fixture(
            String sourceCommit,
            String historicalManifestSha256,
            Map<String, Object> snapshot) {}
}
