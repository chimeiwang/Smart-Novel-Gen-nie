package cn.inkforge.core.workflows.application;

import java.util.List;
import java.util.Map;
import org.jooq.DSLContext;

/** 质量域在既有 Run/Step 事务中投影检查结果；不控制模型、账务或提交事务。 */
public interface WorkflowQualityCompletion {

    /** 保存完整报告；返回 completed 或来源已失效时的 cancelled。 */
    String complete(DSLContext transaction, String runId, Map<String, Object> report);

    /** 投影失败或取消；来源已失效时统一返回 cancelled，不覆盖新的检查结果。 */
    String finish(DSLContext transaction, String runId, String requestedTerminal);

    /** 有界发现旧来源，仅返回精确身份；调用方逐条复用原耐久取消机制。 */
    List<InvalidatedRun> findInvalidatedRuns(int limit);

    /** 调用方已经持有该 Run 锁；只再锁 Chapter/Check，不反锁其他 Run。 */
    boolean isInvalidated(DSLContext transaction, String runId);

    record InvalidatedRun(String userId, String runId) {
        public String cancelRequestId() { return "quality-invalidated." + runId; }
    }
}
