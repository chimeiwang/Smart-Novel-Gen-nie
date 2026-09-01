package cn.inkforge.core.workflows.domain;

/** 拒绝会制造第二套解释或重新打开终态的非法工作流转换。 */
public final class IllegalWorkflowTransitionException extends IllegalStateException {

    public IllegalWorkflowTransitionException(String subject, String from, String to) {
        super(subject + "不允许从 " + from + " 转换到 " + to);
    }
}
