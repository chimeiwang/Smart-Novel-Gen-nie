package cn.inkforge.core.writing.application;

import cn.inkforge.core.writing.domain.WritingReconciliationTask;
import java.util.List;

/** 旧写作任务扫描和耐久对账命令创建端口。 */
public interface WritingReconciliationRepository {

    List<WritingReconciliationTask> listReconcilable(int limit);

    boolean createCommand(WritingReconciliationTask expected);
}
