package cn.inkforge.core.writing.application;

import cn.inkforge.contracts.api.ShortMediumStartWritingRunRequest;
import cn.inkforge.contracts.api.WritingRunV2Response;
import java.util.Set;

/** 已装配的 V2 中短篇纵切；业务来源由 Core 冻结后交给通用 Workflow 内核。 */
public interface ShortMediumDurableRunStarter {

    /** 本进程实际装配的中短篇 Operation key。 */
    Set<String> supportedOperationKeys();

    /** 仅重放既有 V2 幂等事实；缺失时禁止创建。 */
    WritingRunV2Response replayExisting(
            String userId, ShortMediumStartWritingRunRequest request);

    WritingRunV2Response startFresh(
            String userId, ShortMediumStartWritingRunRequest request);
}
