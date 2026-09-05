package cn.inkforge.core.workflows.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.io.IOException;
import java.io.InputStream;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Map;
import org.junit.jupiter.api.Test;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** a150db0 已冻结的五项计划仍使用原 v1 解析器，不依赖当前系统用途或 Registry。 */
class HistoricalFiveOperationIntentExecutionPlanSnapshotTest {

    @Test
    void 从历史五项literal恢复原解析器子计划哈希及预算() throws IOException {
        byte[] bytes;
        try (InputStream stream = getClass().getResourceAsStream(
                "/historical-fixtures/intent-execution-plan-a150db0.json")) {
            assertThat(stream).as("历史五项冻结向量资源").isNotNull();
            bytes = stream.readAllBytes();
        }
        assertThat(sha256(bytes))
                .isEqualTo("7c2b73244e9a2563e7905033d94eea7d895aaacdf16bfd8ac9975974d6ebbcc9");
        Map<String, Object> fixture = new ObjectMapper().readValue(bytes, new TypeReference<>() {});
        assertThat(fixture).containsOnlyKeys("sourceCommit", "historicalManifestSha256", "snapshot");
        assertThat(fixture.get("sourceCommit"))
                .isEqualTo("a150db05b6243c2cba45c2e72a2625ca2acfac30");
        String manifest = "2db29fa6d5e31651e0932e710c8da991c8ecdffe12dcafca57ca617f6023edbb";
        assertThat(fixture.get("historicalManifestSha256")).isEqualTo(manifest);
        Map<String, Object> stored = object(fixture.get("snapshot"));
        IntentExecutionPlanSnapshot restored = IntentExecutionPlanSnapshot.fromStored(stored);

        assertThat(restored.sha256())
                .isEqualTo("9df0f3c3b16e62897e546fbcdb6b705c4f249c2c5b7a5b38c27c4b22b9d3f473");
        assertThat(ExecutionCanonicalJson.sha256(restored.stored()))
                .isEqualTo(ExecutionCanonicalJson.sha256(stored));
        assertThat(restored.executionManifestFingerprint()).isEqualTo(manifest);
        assertThat(restored.operationCatalogVersion()).isEqualTo("1");
        assertThat(restored.resolver().modelProfile().profile()).isEqualTo("system.intent_resolver.v1");
        assertThat(restored.resolver().modelProfile().version()).isEqualTo(1);
        assertThat(restored.resolver().modelProfile().deploymentProfileKey())
                .isEqualTo("deployment.system.intent_resolver.v1");
        assertThat(restored.resolver().modelProfile().promptProfile().name())
                .isEqualTo("prompt.system.intent_resolver.v1");
        assertThat(restored.resolver().modelProfile().promptProfile().version()).isEqualTo(1);
        assertThat(restored.resolver().modelProfile().promptProfile().sha256())
                .isEqualTo("4ebf30f06de85e21db42275f10e88a9ce309ee037dfebfd0fc921bfc77796f63");
        assertThat(restored.operationPlans()).extracting(plan -> plan.operation().key())
                .containsExactly("long_serial.answer_question", "long_serial.plan_chapter",
                        "long_serial.review_chapter", "long_serial.rewrite_scene", "long_serial.write_chapter");
        assertThat(restored.operationPlans()).extracting(ExecutionPlanSnapshot::sha256)
                .containsExactly(
                        "94fee6f8340438adc30562241a42df9e67d7137a75d2917e46755573637b44ed",
                        "9505faaf9b21812f7545a4507613fa11839bb0d7747c2707c39e142ffdc22808",
                        "9a0bf23c4214cfe200391002a2f5b1eceaafc683c56d1d5fa25c7c6fcd5756fe",
                        "a9acb732b3c3810be65c0fae9a6a22e1b4f564b3eb471caf42887dc1c373db86",
                        "6bbfccf76817cb230a9a0a81949732011bd5d2ffa8c74e19b752768099a9a653");
        assertThat(restored.operationPlans()).extracting(ExecutionPlanSnapshot::executionManifestFingerprint)
                .containsOnly(manifest);
        assertThat(restored.maxClarifications()).isEqualTo(2);
        assertThat(restored.resolver().stepBudget().profile()).isEqualTo("step_budget.system.resolve_intent.v1");
        assertThat(restored.runBudget()).isEqualTo(new ExecutionRegistry.RunBudget(
                "budget.long_serial.natural.v1", 9, 204_000, 204_000, 43_000, 16_000, 27_000,
                2_150_000, 990, 2, 1));
    }

    private static String sha256(byte[] bytes) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("JVM 缺少 SHA-256", exception);
        }
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> object(Object value) {
        return (Map<String, Object>) value;
    }
}
