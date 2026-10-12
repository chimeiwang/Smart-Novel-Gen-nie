package cn.inkforge.core.writing.application;

import cn.inkforge.contracts.api.LongSerialStartWritingRunRequest;
import cn.inkforge.contracts.api.NaturalStartWritingRunRequest;
import cn.inkforge.contracts.api.WritingRunV2Response;
import java.util.Set;

/** 已启用的 V2 长篇纵切；业务域负责冻结来源，再交给通用 Workflow 内核。 */
public interface LongSerialDurableRunStarter {

    /** 本进程实际装配的完整 Operation key；必须与 Catalog 启用集合精确相等。 */
    Set<String> supportedOperationKeys();

    default WritingRunV2Response replayNatural(String userId, NaturalStartWritingRunRequest request) {
        throw new IllegalStateException("自然入口耐久重放未装配");
    }

    default WritingRunV2Response startNatural(String userId, NaturalStartWritingRunRequest request) {
        throw new IllegalStateException("自然入口耐久启动未装配");
    }

    /** 仅允许读取既有 V2 幂等事实；缺失时必须拒绝，绝不能创建。 */
    WritingRunV2Response replayExisting(
            String userId, LongSerialStartWritingRunRequest request);

    WritingRunV2Response startFresh(
            String userId, LongSerialStartWritingRunRequest request);
}
