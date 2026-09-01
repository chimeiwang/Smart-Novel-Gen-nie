package cn.inkforge.core.workflows.domain;

/** Core 从共享 Registry 冻结的逻辑模型授权，不包含供应商部署配置。 */
public record WorkflowModelProfile(
        String profile,
        int version,
        String reasoningMode,
        String deploymentProfileKey) {

    public WorkflowModelProfile {
        profile = nonBlank(profile, "模型 Profile");
        if (version < 1) throw new IllegalArgumentException("模型 Profile 版本必须为正数");
        if (!"disabled".equals(reasoningMode) && !"bounded".equals(reasoningMode)) {
            throw new IllegalArgumentException("未知 reasoning mode");
        }
        deploymentProfileKey = nonBlank(deploymentProfileKey, "部署 Profile key");
    }

    private static String nonBlank(String value, String label) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(label + "不能为空");
        }
        return value;
    }
}
