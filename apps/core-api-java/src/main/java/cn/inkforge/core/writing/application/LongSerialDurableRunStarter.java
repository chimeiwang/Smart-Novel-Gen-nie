package cn.inkforge.core.writing.application;

import cn.inkforge.contracts.api.LongSerialStartWritingRunRequest;
import cn.inkforge.contracts.api.WritingRunV2Response;
import java.util.Set;

/** 已启用的 V2 长篇纵切；业务域负责冻结来源，再交给通用 Workflow 内核。 */
public interface LongSerialDurableRunStarter {

    /** 本进程实际装配的完整 Operation key；必须与 Catalog 启用集合精确相等。 */
    Set<String> supportedOperationKeys();

    /** 仅允许读取既有 V2 幂等事实；缺失时必须拒绝，绝不能创建。 */
    WritingRunV2Response replayExisting(
            String userId, LongSerialStartWritingRunRequest request);

    /** 最后一把 PostgreSQL 锁取得后、第一条 V2 INSERT 前再次执行发布授权。 */
    WritingRunV2Response startFresh(
            String userId,
            LongSerialStartWritingRunRequest request,
            Runnable finalFreshStartAuthorization);
}
