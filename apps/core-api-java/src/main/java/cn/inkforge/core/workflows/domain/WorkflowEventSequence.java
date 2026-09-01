package cn.inkforge.core.workflows.domain;

/** PostgreSQL 权威事件序号规则；缺口和回退必须在事务提交前失败。 */
public final class WorkflowEventSequence {

    private WorkflowEventSequence() {}

    public static long next(long current) {
        if (current < 0) throw new IllegalArgumentException("当前事件序号不能为负数");
        return Math.addExact(current, 1L);
    }

    public static long requireNext(long current, long submitted) {
        long expected = next(current);
        if (submitted != expected) {
            throw new IllegalArgumentException(
                    "工作流事件序号必须连续：期望 " + expected + "，实际 " + submitted);
        }
        return submitted;
    }
}
