package cn.inkforge.core.writing.application;

import cn.inkforge.contracts.api.LongSerialStartWritingRunRequest;
import cn.inkforge.contracts.api.WritingRunV2Response;

/** 首个 V2 长篇纵切；业务域负责冻结来源，再交给通用 Workflow 内核。 */
public interface LongSerialDurableRunStarter {

    WritingRunV2Response start(String userId, LongSerialStartWritingRunRequest request);
}
