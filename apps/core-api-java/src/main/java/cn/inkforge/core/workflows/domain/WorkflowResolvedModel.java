package cn.inkforge.core.workflows.domain;

import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

/** Agent 在受理 Step 时冻结的无密钥部署解析；终报不得换模型。 */
public record WorkflowResolvedModel(
        String deploymentProfileKey,
        String deploymentFingerprint,
        String provider,
        String model,
        String transportProfile,
        String endpointProfile,
        String structuredOutputRoute,
        String capabilityVersion,
        String reasoningMode,
        boolean supportsRequestIdempotency) {

    public WorkflowResolvedModel {
        deploymentProfileKey = nonBlank(deploymentProfileKey, "部署 Profile key");
        provider = nonBlank(provider, "Provider");
        model = nonBlank(model, "模型");
        transportProfile = nonBlank(transportProfile, "传输 Profile");
        endpointProfile = nonBlank(endpointProfile, "端点 Profile");
        structuredOutputRoute = nonBlank(structuredOutputRoute, "结构化输出路由");
        capabilityVersion = nonBlank(capabilityVersion, "能力版本");
        if (!"disabled".equals(reasoningMode) && !"bounded".equals(reasoningMode)) {
            throw new IllegalArgumentException("未知 reasoning mode");
        }
        String expected = fingerprint(
                deploymentProfileKey,
                provider,
                model,
                transportProfile,
                endpointProfile,
                structuredOutputRoute,
                capabilityVersion,
                reasoningMode,
                supportsRequestIdempotency);
        if (!Objects.equals(deploymentFingerprint, expected)) {
            throw new IllegalArgumentException("部署模型 fingerprint 与公开解析材料不一致");
        }
    }

    public WorkflowResolvedModel requireAuthorizedBy(WorkflowModelProfile logical) {
        Objects.requireNonNull(logical, "逻辑模型 Profile 不能为空");
        if (!deploymentProfileKey.equals(logical.deploymentProfileKey())
                || !reasoningMode.equals(logical.reasoningMode())) {
            throw new IllegalArgumentException("解析模型超出逻辑 Profile 授权");
        }
        return this;
    }

    public static String fingerprint(
            String deploymentProfileKey,
            String provider,
            String model,
            String transportProfile,
            String endpointProfile,
            String structuredOutputRoute,
            String capabilityVersion,
            String reasoningMode,
            boolean supportsRequestIdempotency) {
        Map<String, Object> material = new LinkedHashMap<>();
        material.put("deploymentProfileKey", deploymentProfileKey);
        material.put("model", model);
        material.put("provider", provider);
        material.put("transportProfile", transportProfile);
        material.put("endpointProfile", endpointProfile);
        material.put("structuredOutputRoute", structuredOutputRoute);
        material.put("capabilityVersion", capabilityVersion);
        material.put("reasoningMode", reasoningMode);
        material.put("supportsRequestIdempotency", supportsRequestIdempotency);
        return ExecutionCanonicalJson.sha256(material);
    }

    private static String nonBlank(String value, String label) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(label + "不能为空");
        }
        return value;
    }
}
