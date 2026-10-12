package cn.inkforge.core.writing.application;

import cn.inkforge.contracts.api.ClarifyWritingRunRequest;
import cn.inkforge.contracts.api.WritingRunV2Response;
import java.util.Objects;

/** 澄清受理不复用 V1 resume 或 Artifact revise；模型派发由既有耐久扫描器完成。 */
public final class WritingRunClarificationService {
    private final WritingRunClarificationStore store;

    public WritingRunClarificationService(WritingRunClarificationStore store) {
        this.store = Objects.requireNonNull(store);
    }

    public WritingRunV2Response accept(String userId, String runId, ClarifyWritingRunRequest request) {
        return store.accept(userId, runId, request);
    }
}
