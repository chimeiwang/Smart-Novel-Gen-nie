package cn.inkforge.core.quality.application;

import cn.inkforge.core.quality.domain.QualityDispatchRecord;
import cn.inkforge.core.quality.domain.QualityDispatchStatus;

/** 提交同一个耐久 WorkflowRun 到 Agent 的端口。 */
@FunctionalInterface
public interface QualityRunSubmitter {

    QualityDispatchStatus submit(QualityDispatchRecord record);
}
