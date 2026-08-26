package cn.inkforge.core.references.application;

import cn.inkforge.core.references.domain.RagDispatchStatus;
import java.time.OffsetDateTime;

/** 参考资料模块对 Agent 队列的最小出站端口。 */
public interface RagIndexSubmitter {

    RagDispatchStatus submit(
            String userId,
            String novelId,
            String referenceId,
            String contentHash,
            OffsetDateTime generation);
}
