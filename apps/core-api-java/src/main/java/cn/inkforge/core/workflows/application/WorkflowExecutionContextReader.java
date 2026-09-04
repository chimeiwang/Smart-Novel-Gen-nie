package cn.inkforge.core.workflows.application;

import cn.inkforge.contracts.api.WorkflowClarificationSnapshot;
import cn.inkforge.core.workflows.catalog.WorkflowExecutionContext;
import java.util.Map;
import org.jooq.DSLContext;

/** 在调用方事务内读取不可变选择与待回答问题；不得另开连接或偷偷加写锁。 */
public interface WorkflowExecutionContextReader {

    WorkflowExecutionContext load(DSLContext transaction, WorkflowExecutionContext.RunIdentity identity,
            Map<String, Object> initialMap);

    WorkflowClarificationSnapshot pendingClarification(DSLContext transaction, String runId, String status);

    /** 只供旧构造器保留显式 v1 计划行为；自然入口必须注入数据库 Reader，不能漏读 selection。 */
    static WorkflowExecutionContextReader frozenBusinessPlansOnly() {
        return new WorkflowExecutionContextReader() {
            @Override
            public WorkflowExecutionContext load(DSLContext transaction, WorkflowExecutionContext.RunIdentity identity,
                    Map<String, Object> initialMap) {
                if (!"1".equals(initialMap.get("planVersion"))) {
                    throw new IllegalStateException("自然入口缺少共享 WorkflowExecutionContextReader 装配");
                }
                return WorkflowExecutionContext.fromStored(initialMap, null, null, identity);
            }

            @Override
            public WorkflowClarificationSnapshot pendingClarification(DSLContext transaction, String runId, String status) {
                return null;
            }
        };
    }
}
