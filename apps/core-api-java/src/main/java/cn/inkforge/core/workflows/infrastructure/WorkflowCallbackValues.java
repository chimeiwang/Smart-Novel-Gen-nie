package cn.inkforge.core.workflows.infrastructure;

import cn.inkforge.contracts.api.EvaluationEvidenceReference;
import cn.inkforge.contracts.api.EvaluationFinding;
import cn.inkforge.contracts.api.EvidenceEvaluation;
import cn.inkforge.contracts.api.EvidenceExpansionRequest;
import cn.inkforge.contracts.api.EvidenceRange;
import cn.inkforge.contracts.api.ExecutionStepFailure;
import cn.inkforge.contracts.api.ExecutionStepResult;
import cn.inkforge.contracts.api.ModelProfileRef;
import cn.inkforge.contracts.api.ProposedCommand;
import cn.inkforge.contracts.api.ResolvedModelRef;
import cn.inkforge.contracts.api.StepUsage;
import cn.inkforge.core.workflows.domain.WorkflowResolvedModel;
import cn.inkforge.core.workflows.domain.WorkflowStepUsage;
import cn.inkforge.core.workflows.domain.WorkflowUsageStatus;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.openapitools.jackson.nullable.JsonNullable;

/** 将生成 DTO 投影为稳定 canonical JSON；可空未知字段不得以 0 伪装。 */
final class WorkflowCallbackValues {

    private WorkflowCallbackValues() {}

    static WorkflowStepUsage usage(StepUsage value) {
        Objects.requireNonNull(value, "Step usage 不能为空");
        return new WorkflowStepUsage(
                WorkflowUsageStatus.fromWireValue(value.getUsageStatus().getValue()),
                optionalLong(value.getInputTokens()),
                optionalLong(value.getCachedTokens()),
                optionalLong(value.getPromptCacheMissTokens()),
                optionalLong(value.getCompletionTokens()),
                optionalLong(value.getReasoningTokens()),
                optionalLong(value.getVisibleOutputTokens()),
                optionalLong(value.getCostMicros()),
                value.getProviderAttempts(),
                value.getProtocolCorrections(),
                value.getWallTimeMillis());
    }

    static Map<String, Object> usageMap(WorkflowStepUsage value) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("usageStatus", value.usageStatus().wireValue());
        putKnown(result, "inputTokens", value.inputTokens());
        putKnown(result, "cachedTokens", value.cachedTokens());
        putKnown(result, "promptCacheMissTokens", value.promptCacheMissTokens());
        putKnown(result, "completionTokens", value.completionTokens());
        putKnown(result, "reasoningTokens", value.reasoningTokens());
        putKnown(result, "visibleOutputTokens", value.visibleOutputTokens());
        putKnown(result, "costMicros", value.costMicros());
        result.put("providerAttempts", value.providerAttempts());
        result.put("protocolCorrections", value.protocolCorrections());
        result.put("wallTimeMillis", value.wallTimeMillis());
        return Collections.unmodifiableMap(result);
    }

    static WorkflowResolvedModel resolvedModel(ResolvedModelRef value) {
        Objects.requireNonNull(value, "resolvedModel 不能为空");
        return new WorkflowResolvedModel(
                value.getDeploymentProfileKey(),
                value.getDeploymentFingerprint(),
                value.getProvider(),
                value.getModel(),
                value.getTransportProfile(),
                value.getEndpointProfile(),
                value.getStructuredOutputRoute().getValue(),
                value.getCapabilityVersion(),
                value.getReasoningMode().getValue(),
                value.getSupportsRequestIdempotency());
    }

    static Map<String, Object> resolvedModelMap(ResolvedModelRef value) {
        return resolvedModelMap(resolvedModel(value));
    }

    static Map<String, Object> resolvedModelMap(WorkflowResolvedModel value) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("deploymentProfileKey", value.deploymentProfileKey());
        result.put("deploymentFingerprint", value.deploymentFingerprint());
        result.put("provider", value.provider());
        result.put("model", value.model());
        result.put("transportProfile", value.transportProfile());
        result.put("endpointProfile", value.endpointProfile());
        result.put("structuredOutputRoute", value.structuredOutputRoute());
        result.put("capabilityVersion", value.capabilityVersion());
        result.put("reasoningMode", value.reasoningMode());
        result.put("supportsRequestIdempotency", value.supportsRequestIdempotency());
        return Collections.unmodifiableMap(result);
    }

    static Map<String, Object> modelProfileMap(ModelProfileRef value) {
        Objects.requireNonNull(value, "modelProfile 不能为空");
        var prompt = Objects.requireNonNull(
                value.getPromptProfile(), "modelProfile.promptProfile 不能为空");
        return modelProfileMap(
                value.getProfile(),
                value.getVersion(),
                value.getReasoningMode().getValue(),
                value.getDeploymentProfileKey(),
                prompt.getName(),
                prompt.getVersion(),
                prompt.getSha256());
    }

    static Map<String, Object> modelProfileMap(
            cn.inkforge.contracts.agent.ModelProfileRef value) {
        Objects.requireNonNull(value, "modelProfile 不能为空");
        var prompt = Objects.requireNonNull(
                value.getPromptProfile(), "modelProfile.promptProfile 不能为空");
        return modelProfileMap(
                value.getProfile(),
                value.getVersion(),
                value.getReasoningMode().getValue(),
                value.getDeploymentProfileKey(),
                prompt.getName(),
                prompt.getVersion(),
                prompt.getSha256());
    }

    private static Map<String, Object> modelProfileMap(
            String profile,
            Integer version,
            String reasoningMode,
            String deploymentProfileKey,
            String promptName,
            Integer promptVersion,
            String promptSha256) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("profile", profile);
        result.put("version", version);
        result.put("reasoningMode", reasoningMode);
        result.put("deploymentProfileKey", deploymentProfileKey);
        result.put(
                "promptProfile",
                Map.of(
                        "name", promptName,
                        "version", promptVersion,
                        "sha256", promptSha256));
        return Collections.unmodifiableMap(result);
    }

    static Map<String, Object> resultHashMaterial(ExecutionStepResult result) {
        Object selected;
        switch (result.getResultKind()) {
            case OUTPUT -> selected = requiredPresent(result.getOutput(), "output");
            case EVALUATION -> selected = evaluationMap(Objects.requireNonNull(
                    result.getEvaluation(), "evaluation 结果分支不能为空"));
            case PROPOSED_COMMAND -> selected = proposedCommandMap(Objects.requireNonNull(
                    result.getProposedCommand(), "proposed_command 结果分支不能为空"));
            case EVIDENCE_EXPANSION -> selected = evidenceExpansionMap(Objects.requireNonNull(
                    result.getEvidenceExpansion(), "evidence_expansion 结果分支不能为空"));
            default -> throw new IllegalArgumentException("未知 Execution resultKind");
        }
        int branchCount = (present(result.getOutput()) ? 1 : 0)
                + (result.getEvaluation() == null ? 0 : 1)
                + (result.getEvidenceExpansion() == null ? 0 : 1)
                + (result.getProposedCommand() == null ? 0 : 1);
        if (branchCount != 1) throw new IllegalArgumentException("执行结果必须且只能包含一个分支");
        Map<String, Object> material = new LinkedHashMap<>();
        material.put("resultKind", result.getResultKind().getValue());
        material.put("resolvedModel", resolvedModelMap(result.getResolvedModel()));
        material.put("usage", usageMap(usage(result.getUsage())));
        material.put("value", selected);
        return Collections.unmodifiableMap(material);
    }

    /** 仅做既有传输契约的 canonical 投影，资料授权仍由对应 Operation 及来源读取器负责。 */
    static Map<String, Object> evidenceExpansionMap(EvidenceExpansionRequest value) {
        Objects.requireNonNull(value);
        if (value.getItems() == null || value.getItems().isEmpty() || value.getItems().size() > 100
                || value.getMaxAdditionalBytes() == null || value.getMaxAdditionalBytes() < 1
                || value.getSourceBundleVersion() == null || value.getSourceBundleVersion() < 1) {
            throw new IllegalArgumentException("证据扩展缺少合法资源清单或边界");
        }
        List<Map<String, Object>> items = new ArrayList<>();
        java.util.Set<String> identities = new java.util.HashSet<>();
        for (var item : value.getItems()) {
            Map<String, Object> material = new LinkedHashMap<>();
            material.put("resourceType", Objects.requireNonNull(item.getResourceType()));
            material.put("resourceId", Objects.requireNonNull(item.getResourceId()));
            Map<String, Object> range = rangeMap(item.getRange());
            if (range != null) material.put("range", range);
            if (!identities.add(ExecutionCanonicalJson.sha256(material))) {
                throw new IllegalArgumentException("证据扩展不能重复同一资源范围");
            }
            material.put("purposeCode", Objects.requireNonNull(item.getPurposeCode()));
            items.add(Collections.unmodifiableMap(material));
        }
        return Map.of("requestId", Objects.requireNonNull(value.getRequestId()),
                "sourceBundleId", Objects.requireNonNull(value.getSourceBundleId()),
                "sourceBundleVersion", value.getSourceBundleVersion(),
                "reasonCode", Objects.requireNonNull(value.getReasonCode()),
                "maxAdditionalBytes", value.getMaxAdditionalBytes(), "items", List.copyOf(items));
    }

    /** 与 Pydantic exclude_none 投影一致；命令授权仍由冻结执行计划和 Core 意图裁决负责。 */
    static Map<String, Object> proposedCommandMap(ProposedCommand value) {
        Objects.requireNonNull(value, "ProposedCommand 不能为空");
        String workflow = optional(value.getWorkflow());
        String operation = optional(value.getOperation());
        String targetType = optional(value.getTargetType());
        String targetId = optional(value.getTargetId());
        String scope = optional(value.getScopeKind());
        var clarification = value.getClarification();
        var confidence = value.getConfidence();
        Map<String, Object> arguments = Objects.requireNonNullElse(value.getArguments(), Map.of());
        if ((workflow == null) != (operation == null) || (targetType == null) != (targetId == null)
                || (workflow != null) == (clarification != null)
                || (workflow == null && (targetType != null || scope != null || !arguments.isEmpty()))
                || confidence == null || confidence.signum() < 0
                || confidence.compareTo(java.math.BigDecimal.ONE) > 0) {
            throw new IllegalArgumentException("ProposedCommand 必须且只能包含合法命令或澄清");
        }
        Map<String, Object> result = new LinkedHashMap<>();
        if (workflow != null) {
            result.put("workflow", workflow);
            result.put("operation", operation);
        }
        if (targetType != null) {
            result.put("targetType", targetType);
            result.put("targetId", targetId);
        }
        if (scope != null) result.put("scopeKind", scope);
        result.put("arguments", arguments);
        result.put("confidence", confidence);
        if (clarification != null) {
            if (clarification.getCode() == null || clarification.getPrompt() == null) {
                throw new IllegalArgumentException("澄清必须包含 code 与完整 prompt");
            }
            result.put("clarification", Map.of("code", clarification.getCode(), "prompt", clarification.getPrompt()));
        }
        return Collections.unmodifiableMap(result);
    }

    static Map<String, Object> failureHashMaterial(ExecutionStepFailure failure) {
        String category = failure.getErrorCategory().getValue();
        String cancelRequestId = optional(failure.getCancelRequestId());
        boolean outcomeUnknown = Boolean.TRUE.equals(failure.getOutcomeUnknown());
        boolean retryable = Boolean.TRUE.equals(failure.getRetryable());
        if (outcomeUnknown != "model_outcome_unknown".equals(category)) {
            throw new IllegalArgumentException("outcomeUnknown 必须只用于 MODEL_OUTCOME_UNKNOWN");
        }
        if (outcomeUnknown && retryable) {
            throw new IllegalArgumentException("结果未知时禁止盲目重试");
        }
        if (retryable && !List.of("provider_transient", "internal").contains(category)) {
            throw new IllegalArgumentException("只有明确的暂态故障可标记 retryable");
        }
        if ("cancelled".equals(category) != (cancelRequestId != null)) {
            throw new IllegalArgumentException("cancelled 失败必须且只能绑定 cancelRequestId");
        }
        Map<String, Object> material = new LinkedHashMap<>();
        material.put("errorCategory", category);
        material.put("errorCode", failure.getErrorCode());
        material.put("outcomeUnknown", outcomeUnknown);
        material.put("retryable", retryable);
        material.put("resolvedModel", resolvedModelMap(failure.getResolvedModel()));
        material.put("usage", usageMap(usage(failure.getUsage())));
        if (cancelRequestId != null) material.put("cancelRequestId", cancelRequestId);
        return Collections.unmodifiableMap(material);
    }

    static void requireHash(String actual, Map<String, Object> material, String label) {
        if (!Objects.equals(actual, ExecutionCanonicalJson.sha256(material))) {
            throw new IllegalArgumentException(label + " hash 与完整 canonical 材料不一致");
        }
    }

    static Map<String, Object> evaluationMap(EvidenceEvaluation value) {
        List<EvaluationFinding> findings = Objects.requireNonNullElse(value.getFindings(), List.of());
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("evaluationId", value.getEvaluationId());
        result.put("runId", value.getRunId());
        result.put("stepId", value.getStepId());
        result.put("evidenceBundleId", value.getEvidenceBundleId());
        String artifactId = optional(value.getArtifactId());
        Integer artifactRevision = optional(value.getArtifactRevision());
        if ((artifactId == null) != (artifactRevision == null)) {
            throw new IllegalArgumentException("Evaluation Artifact 绑定必须成对出现");
        }
        if (artifactId != null) {
            result.put("artifactId", artifactId);
            result.put("artifactRevision", artifactRevision);
        }
        result.put("evaluatorProfile", modelProfileMap(value.getEvaluatorProfile()));
        result.put("resolvedModel", resolvedModelMap(value.getResolvedModel()));
        result.put("rubricVersion", value.getRubricVersion());
        result.put("executionStatus", value.getExecutionStatus().getValue());
        result.put("contentVerdict", value.getContentVerdict().getValue());
        result.put("findings", findings.stream().map(finding -> findingMap(finding, false)).toList());
        validateEvaluationConclusion(value.getExecutionStatus().getValue(),
                value.getContentVerdict().getValue(), findings);
        return Collections.unmodifiableMap(result);
    }

    static Map<String, Object> reviewerOutput(EvidenceEvaluation value) {
        List<EvaluationFinding> findings = value.getFindings() == null
                ? List.of()
                : value.getFindings();
        return Map.of(
                "contentVerdict", value.getContentVerdict().getValue(),
                "findings", findings.stream()
                        .map(finding -> findingMap(finding, true))
                        .toList());
    }

    static <T> T optional(JsonNullable<T> value) {
        return value == null || !value.isPresent() ? null : value.get();
    }

    private static Map<String, Object> findingMap(EvaluationFinding value, boolean includeNull) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("dimension", value.getDimension());
        result.put("severity", value.getSeverity().getValue());
        result.put("claim", value.getClaim());
        Map<String, Object> candidateRange = rangeMap(value.getCandidateRange());
        if (includeNull || candidateRange != null) result.put("candidateRange", candidateRange);
        List<EvaluationEvidenceReference> evidence = Objects.requireNonNull(value.getEvidence());
        result.put("evidence", evidence.stream().map(reference -> referenceMap(reference, includeNull)).toList());
        result.put("suggestion", value.getSuggestion());
        result.put("confidence", value.getConfidence());
        var patch = value.getCandidatePatch();
        if (patch != null) {
            if (!"text_replace".equals(patch.getKind()) || patch.getFind() == null
                    || patch.getFind().isEmpty() || patch.getReplace() == null) {
                throw new IllegalArgumentException("candidatePatch 必须是完整的精确文本替换");
            }
            // 新字段缺省或 null 都不进入 canonical 材料，旧 Reviewer 回调哈希保持不变。
            result.put("candidatePatch", Map.of("kind", patch.getKind(),
                    "find", patch.getFind(), "replace", patch.getReplace()));
        }
        return Collections.unmodifiableMap(result);
    }

    private static Map<String, Object> referenceMap(
            EvaluationEvidenceReference value, boolean includeNull) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("evidenceItemId", value.getEvidenceItemId());
        result.put("contentSha256", value.getContentSha256());
        Map<String, Object> range = rangeMap(value.getRange());
        if (includeNull || range != null) result.put("range", range);
        return Collections.unmodifiableMap(result);
    }

    private static Map<String, Object> rangeMap(EvidenceRange range) {
        if (range == null) return null;
        if (range.getStartCodePoint() == null
                || range.getEndCodePoint() == null
                || range.getStartCodePoint() < 0
                || range.getEndCodePoint() <= range.getStartCodePoint()) {
            throw new IllegalArgumentException("评审证据码点范围无效");
        }
        return Map.of(
                "startCodePoint", range.getStartCodePoint(),
                "endCodePoint", range.getEndCodePoint());
    }

    private static void validateEvaluationConclusion(
            String executionStatus, String verdict, List<EvaluationFinding> findings) {
        if (!"completed".equals(executionStatus)) {
            if (!"cannot_assess".equals(verdict) || !findings.isEmpty()) {
                throw new IllegalArgumentException("未完成的评审不能生成内容结论");
            }
        } else if (("pass".equals(verdict) || "cannot_assess".equals(verdict))
                && !findings.isEmpty()) {
            throw new IllegalArgumentException("pass/cannot_assess 评审不能包含 findings");
        } else if ("issues_found".equals(verdict) && findings.isEmpty()) {
            throw new IllegalArgumentException("issues_found 评审必须包含 findings");
        }
    }

    private static Long optionalLong(JsonNullable<Integer> value) {
        Integer resolved = optional(value);
        return resolved == null ? null : resolved.longValue();
    }

    private static boolean present(JsonNullable<?> value) {
        return value != null && value.isPresent() && value.get() != null;
    }

    private static <T> T requiredPresent(JsonNullable<T> value, String label) {
        T resolved = optional(value);
        if (resolved == null) throw new IllegalArgumentException(label + " 结果分支不能为空");
        return resolved;
    }

    private static void putKnown(Map<String, Object> target, String key, Long value) {
        if (value != null) target.put(key, value);
    }
}
