package cn.inkforge.core.workflows.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.EvidenceEvaluation;
import cn.inkforge.contracts.api.EvidenceExpansionItem;
import cn.inkforge.contracts.api.EvidenceExpansionRequest;
import cn.inkforge.contracts.api.EvidenceRange;
import cn.inkforge.contracts.api.ExecutionStepResult;
import cn.inkforge.contracts.api.ProposedCommand;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;
import org.junit.jupiter.api.Test;
import org.openapitools.jackson.nullable.JsonNullableJackson3Module;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

class WorkflowCallbackValuesTest {
    private static final ObjectMapper EXPANSION_JSON = JsonMapper.builder()
            .addModule(new JsonNullableJackson3Module()).build();

    @Test
    void 证据补齐省略可空范围并保留原序且与Python完整固定向量一致() {
        var request = EXPANSION_JSON.convertValue(expansionRequest(), EvidenceExpansionRequest.class);
        var expected = Map.of("requestId", "evidence-golden-1", "sourceBundleId", "bundle-golden-1",
                "sourceBundleVersion", 2, "reasonCode", "agent_updates_sources_required", "maxAdditionalBytes", 320000,
                "items", List.of(
                        Map.of("resourceType", "world_setting", "resourceId", "novel-golden", "purposeCode", "target"),
                        Map.of("resourceType", "character", "resourceId", "character-golden", "purposeCode", "delete_impact")));
        assertThat(WorkflowCallbackValues.evidenceExpansionMap(request)).isEqualTo(expected);
        request.getItems().getFirst().setRange(null);
        assertThat(WorkflowCallbackValues.evidenceExpansionMap(request)).isEqualTo(expected);
        // 使用共享 Pydantic EvidenceExpansionRequest/ResolvedModelRef/StepUsage 与
        // canonical_execution_sha256 独立计算；不是由待测 Java 投影生成期望值。
        assertThat(ExecutionCanonicalJson.sha256(WorkflowCallbackValues.evidenceExpansionMap(request)))
                .isEqualTo("ba40a001f1f4daa51f64123960f23a33b21f0233294aa020b4bd188e23cc4467");
        assertThat(ExecutionCanonicalJson.sha256(WorkflowCallbackValues.resultHashMaterial(expansionResult(request))))
                .isEqualTo("79e2a0f0599920c837faa3a0088ceb3b03ecceaaa19bca46100047c39c9de62f");
    }

    @Test
    void 证据补齐请求身份各字段范围及原序都进入完整结果哈希() {
        var original = EXPANSION_JSON.convertValue(expansionRequest(), EvidenceExpansionRequest.class);
        String expected = ExecutionCanonicalJson.sha256(WorkflowCallbackValues.resultHashMaterial(expansionResult(original)));
        List<Consumer<EvidenceExpansionRequest>> mutations = List.of(
                value -> value.setRequestId("evidence-golden-2"),
                value -> value.setSourceBundleId("bundle-golden-2"),
                value -> value.setSourceBundleVersion(3),
                value -> value.setReasonCode("another_reason"),
                value -> value.setMaxAdditionalBytes(320001),
                value -> value.getItems().getFirst().setResourceType("story_background"),
                value -> value.getItems().getFirst().setResourceId("novel-another"),
                value -> value.getItems().getFirst().setPurposeCode("another_purpose"),
                value -> value.getItems().getFirst().setRange(new EvidenceRange(6, 1)),
                value -> value.setItems(value.getItems().reversed()),
                value -> value.setItems(List.of(value.getItems().getFirst())));
        for (Consumer<EvidenceExpansionRequest> mutation : mutations) {
            var changed = EXPANSION_JSON.convertValue(expansionRequest(), EvidenceExpansionRequest.class);
            mutation.accept(changed);
            assertThat(ExecutionCanonicalJson.sha256(WorkflowCallbackValues.resultHashMaterial(expansionResult(changed))))
                    .isNotEqualTo(expected);
        }
        var ranged = EXPANSION_JSON.convertValue(expansionRequest(), EvidenceExpansionRequest.class);
        ranged.getItems().getFirst().setRange(new EvidenceRange(6, 1));
        String rangeHash = ExecutionCanonicalJson.sha256(WorkflowCallbackValues.evidenceExpansionMap(ranged));
        ranged.getItems().getFirst().setRange(new EvidenceRange(6, 2));
        assertThat(ExecutionCanonicalJson.sha256(WorkflowCallbackValues.evidenceExpansionMap(ranged))).isNotEqualTo(rangeHash);
        ranged.getItems().getFirst().setRange(new EvidenceRange(7, 1));
        assertThat(ExecutionCanonicalJson.sha256(WorkflowCallbackValues.evidenceExpansionMap(ranged))).isNotEqualTo(rangeHash);
    }

    @Test
    void 证据补齐拒绝混入其他结果分支以及重复资源范围() {
        var request = EXPANSION_JSON.convertValue(expansionRequest(), EvidenceExpansionRequest.class);
        for (String branch : List.of("output", "evaluation", "proposedCommand")) {
            Map<String, Object> body = expansionResultBody(request);
            body.put(branch, switch (branch) {
                case "output" -> Map.of("answer", "不能与资料请求同时返回");
                case "proposedCommand" -> Map.of("workflow", "long_serial", "operation", "write_chapter", "confidence", 1);
                default -> Map.of("contentVerdict", "pass", "findings", List.of());
            });
            assertThatThrownBy(() -> WorkflowCallbackValues.resultHashMaterial(EXPANSION_JSON.convertValue(body, ExecutionStepResult.class)))
                    .isInstanceOf(IllegalArgumentException.class);
        }
        request.setItems(List.of(new EvidenceExpansionItem("target", "character-golden", "character"),
                new EvidenceExpansionItem("delete_impact", "character-golden", "character")));
        assertThatThrownBy(() -> WorkflowCallbackValues.evidenceExpansionMap(request)).isInstanceOf(IllegalArgumentException.class);
        request.setItems(List.of(new EvidenceExpansionItem("target", "chapter-golden", "chapter_content").range(new EvidenceRange(6, 1)),
                new EvidenceExpansionItem("reference", "chapter-golden", "chapter_content").range(new EvidenceRange(6, 1))));
        assertThatThrownBy(() -> WorkflowCallbackValues.evidenceExpansionMap(request)).isInstanceOf(IllegalArgumentException.class);
        // 通用传输身份包含范围；资料操作是否允许 range 由专属 adapter 决定，不能在此缩窄共享契约。
        request.getItems().getLast().setRange(new EvidenceRange(10, 6));
        assertThat(EXPANSION_JSON.valueToTree(WorkflowCallbackValues.evidenceExpansionMap(request)).path("items").size()).isEqualTo(2);
        assertThat(EXPANSION_JSON.valueToTree(WorkflowCallbackValues.evidenceExpansionMap(request)).at("/items/1/range/startCodePoint").asInt()).isEqualTo(6);
    }

    @Test
    void 证据补齐拒绝空清单无效额度版本与无效范围() {
        List<Consumer<EvidenceExpansionRequest>> invalid = List.of(
                value -> value.setItems(List.of()),
                value -> value.setItems(null),
                value -> value.setMaxAdditionalBytes(0),
                value -> value.setSourceBundleVersion(0),
                value -> value.getItems().getFirst().setRange(new EvidenceRange(1, 1)),
                value -> value.getItems().getFirst().setRange(new EvidenceRange(2, -1)));
        for (Consumer<EvidenceExpansionRequest> mutation : invalid) {
            var request = EXPANSION_JSON.convertValue(expansionRequest(), EvidenceExpansionRequest.class);
            mutation.accept(request);
            assertThatThrownBy(() -> WorkflowCallbackValues.evidenceExpansionMap(request)).isInstanceOf(IllegalArgumentException.class);
        }
        var result = expansionResult(EXPANSION_JSON.convertValue(expansionRequest(), EvidenceExpansionRequest.class));
        result.setEvidenceExpansion(null);
        assertThatThrownBy(() -> WorkflowCallbackValues.resultHashMaterial(result)).isInstanceOf(NullPointerException.class);
    }

    private static Map<String, Object> expansionRequest() {
        Map<String, Object> first = new LinkedHashMap<>(Map.of("resourceType", "world_setting", "resourceId", "novel-golden", "purposeCode", "target"));
        first.put("range", null);
        return Map.of("requestId", "evidence-golden-1", "sourceBundleId", "bundle-golden-1", "sourceBundleVersion", 2,
                "reasonCode", "agent_updates_sources_required", "maxAdditionalBytes", 320000,
                "items", List.of(first, Map.of("resourceType", "character", "resourceId", "character-golden", "purposeCode", "delete_impact")));
    }

    private static ExecutionStepResult expansionResult(EvidenceExpansionRequest request) {
        return EXPANSION_JSON.convertValue(expansionResultBody(request), ExecutionStepResult.class);
    }

    private static Map<String, Object> expansionResultBody(EvidenceExpansionRequest request) {
        Map<String, Object> model = new LinkedHashMap<>(Map.of(
                "deploymentProfileKey", "deployment.lore.generator.v3", "provider", "fake", "model", "fake",
                "transportProfile", "transport.fake.v1", "endpointProfile", "endpoint.local-fake.v1",
                "structuredOutputRoute", "responses_json_schema_v1", "capabilityVersion", "capability.fake.structured-output.v1",
                "reasoningMode", "disabled", "supportsRequestIdempotency", true));
        model.put("deploymentFingerprint", ExecutionCanonicalJson.sha256(model));
        Map<String, Object> usage = new LinkedHashMap<>(Map.of(
                "usageStatus", "complete", "inputTokens", 100, "cachedTokens", 0, "promptCacheMissTokens", 100,
                "completionTokens", 20, "reasoningTokens", 0, "visibleOutputTokens", 20, "costMicros", 0,
                "providerAttempts", 1, "protocolCorrections", 0));
        usage.put("wallTimeMillis", 50);
        return new LinkedHashMap<>(Map.of("resultKind", "evidence_expansion", "resolvedModel", model,
                "usage", usage, "evidenceExpansion", request));
    }

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
