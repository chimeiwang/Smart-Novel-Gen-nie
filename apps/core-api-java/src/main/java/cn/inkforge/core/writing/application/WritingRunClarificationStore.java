package cn.inkforge.core.writing.application;

import cn.inkforge.contracts.api.ClarifyWritingRunRequest;
import cn.inkforge.contracts.api.WritingRunV2Response;

/** 当前自然 Run 的澄清决定；同请求重放冻结受理回执而非最新状态。 */
public interface WritingRunClarificationStore {
    WritingRunV2Response accept(String userId, String runId, ClarifyWritingRunRequest request);
}
