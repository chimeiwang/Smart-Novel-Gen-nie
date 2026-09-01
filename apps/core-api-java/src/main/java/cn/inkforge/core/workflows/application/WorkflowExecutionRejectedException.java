package cn.inkforge.core.workflows.application;

/** Agent 在未受理前给出的确定性 HTTP 拒绝；与响应未知/网络故障严格区分。 */
public final class WorkflowExecutionRejectedException extends RuntimeException {

    private final String errorCode;

    public WorkflowExecutionRejectedException(String errorCode) {
        super("Agent 确定性拒绝 Workflow Step");
        if (errorCode == null || errorCode.isBlank()) {
            throw new IllegalArgumentException("确定性拒绝错误码不能为空");
        }
        this.errorCode = errorCode;
    }

    public String errorCode() {
        return errorCode;
    }
}
