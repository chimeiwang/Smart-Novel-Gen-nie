package cn.inkforge.core.workflows.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.EvidenceEvaluation;
import cn.inkforge.contracts.api.ExecutionStepResult;
import cn.inkforge.contracts.api.ProposedCommand;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.openapitools.jackson.nullable.JsonNullableJackson3Module;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

class WorkflowCallbackValuesTest {
    @Test
    void 意图完整结果哈希与Python固定向量相同且拒绝混入第二结果分支() {
        ObjectMapper json = JsonMapper.builder().addModule(new JsonNullableJackson3Module()).build();
        Map<String, Object> model = new LinkedHashMap<>(Map.of(
                "deploymentProfileKey", "deployment.system.intent_resolver.v1", "provider", "fake", "model", "fake",
                "transportProfile", "transport.fake.v1", "endpointProfile", "endpoint.local-fake.v1",
                "structuredOutputRoute", "responses_json_schema_v1", "capabilityVersion", "capability.fake.structured-output.v1",
                "reasoningMode", "disabled", "supportsRequestIdempotency", true));
        model.put("deploymentFingerprint", ExecutionCanonicalJson.sha256(model));
        Map<String, Object> usage = new LinkedHashMap<>(Map.of(
                "usageStatus", "complete", "inputTokens", 100, "cachedTokens", 0, "promptCacheMissTokens", 100,
                "completionTokens", 20, "reasoningTokens", 0, "visibleOutputTokens", 20, "costMicros", 0,
                "providerAttempts", 1, "protocolCorrections", 0));
        usage.put("wallTimeMillis", 50);
        var command = Map.of("workflow", "long_serial", "operation", "write_chapter", "confidence", 0.85, "arguments", Map.of());
        Map<String, Object> body = new LinkedHashMap<>(Map.of("resultKind", "proposed_command",
                "resolvedModel", model, "usage", usage, "proposedCommand", command));
        ExecutionStepResult result = json.convertValue(body, ExecutionStepResult.class);
        // 由共享 Pydantic ProposedCommand 与 canonical_execution_sha256 独立计算的固定向量。
        assertThat(ExecutionCanonicalJson.sha256(WorkflowCallbackValues.resultHashMaterial(result)))
                .isEqualTo("2606a746056e783c6e2bad28ccea0e03136771a260fb842f6e7328393052ea1b");
        body.put("output", Map.of("answer", "不能混入另一个结果"));
        assertThatThrownBy(() -> WorkflowCallbackValues.resultHashMaterial(json.convertValue(body, ExecutionStepResult.class)))
                .isInstanceOf(IllegalArgumentException.class);
        result.setProposedCommand(null);
        assertThatThrownBy(() -> WorkflowCallbackValues.resultHashMaterial(result)).isInstanceOf(NullPointerException.class);
    }

    @Test
    void 意图结果省略空身份并保留参数默认值和完整澄清原文() {
        ObjectMapper json = JsonMapper.builder().addModule(new JsonNullableJackson3Module()).build();
        Map<String, Object> resolved = new LinkedHashMap<>(Map.of(
                "workflow", "long_serial", "operation", "write_chapter", "confidence", 0.85));
        resolved.put("targetId", null);
        resolved.put("targetType", null);
        resolved.put("scopeKind", null);
        resolved.put("clarification", null);
        var command = json.convertValue(resolved, ProposedCommand.class);
        var expected = Map.of("workflow", "long_serial", "operation", "write_chapter",
                "confidence", 0.85, "arguments", Map.of());
        assertThat(ExecutionCanonicalJson.sha256(WorkflowCallbackValues.proposedCommandMap(command)))
                .isEqualTo(ExecutionCanonicalJson.sha256(expected));
        String prompt = "  请明确😀\r\n本次任务  ";
        var clarification = Map.of("confidence", 0.5, "arguments", Map.of(),
                "clarification", Map.of("code", "ambiguous_intent", "prompt", prompt));
        assertThat(ExecutionCanonicalJson.sha256(WorkflowCallbackValues.proposedCommandMap(
                json.convertValue(clarification, ProposedCommand.class))))
                .isEqualTo(ExecutionCanonicalJson.sha256(clarification));
    }

    @Test
    void 意图投影拒绝不完整命令和澄清夹带目标() {
        ObjectMapper json = JsonMapper.builder().addModule(new JsonNullableJackson3Module()).build();
        for (Map<String, Object> invalid : List.of(
                Map.<String, Object>of("workflow", "long_serial", "confidence", 1),
                Map.<String, Object>of("confidence", 0.5),
                Map.<String, Object>of("workflow", "long_serial", "operation", "write_chapter", "confidence", 1,
                        "clarification", Map.of("code", "question", "prompt", "请选择")),
                Map.<String, Object>of("confidence", 0.5, "targetType", "chapter", "targetId", "other",
                        "clarification", Map.of("code", "question", "prompt", "请选择")))) {
            assertThatThrownBy(() -> WorkflowCallbackValues.proposedCommandMap(
                    json.convertValue(invalid, ProposedCommand.class)))
                    .isInstanceOf(IllegalArgumentException.class);
        }
    }

    @Test
    void 缺省或显式空Patch不改变旧投影而结构化替换完整进入结果() {
        ObjectMapper json = new ObjectMapper();
        Map<String, Object> reference = new LinkedHashMap<>(Map.of("evidenceItemId", "evidence", "contentSha256", "a".repeat(64)));
        reference.put("range", null);
        Map<String, Object> finding = new LinkedHashMap<>(Map.of("dimension", "chapter_draft.local", "severity", "warning",
                "claim", "局部问题", "suggestion", "说明不能当作替换文本", "confidence", 0.9, "evidence", List.of(reference)));
        finding.put("candidateRange", null);
        Map<String, Object> expected = Map.of("contentVerdict", "issues_found", "findings", List.of(finding));
        var absent = json.convertValue(expected, EvidenceEvaluation.class);
        String oldHash = ExecutionCanonicalJson.sha256(expected);
        assertThat(json.valueToTree(WorkflowCallbackValues.reviewerOutput(absent)).path("findings").get(0).has("candidatePatch")).isFalse();
        assertThat(ExecutionCanonicalJson.sha256(WorkflowCallbackValues.reviewerOutput(absent))).isEqualTo(oldHash);
        finding.put("candidatePatch", null);
        var explicitNull = json.convertValue(expected, EvidenceEvaluation.class);
        assertThat(ExecutionCanonicalJson.sha256(WorkflowCallbackValues.reviewerOutput(explicitNull))).isEqualTo(oldHash);
        Map<String, Object> patch = Map.of("kind", "text_replace", "find", "  ", "replace", "完整Unicode😀\n替换");
        finding.put("candidatePatch", patch);
        var patched = json.convertValue(expected, EvidenceEvaluation.class);
        assertThat(ExecutionCanonicalJson.sha256(WorkflowCallbackValues.reviewerOutput(patched))).isEqualTo(ExecutionCanonicalJson.sha256(expected));
        assertThat(ExecutionCanonicalJson.sha256(WorkflowCallbackValues.reviewerOutput(patched))).isNotEqualTo(oldHash);
    }
}
