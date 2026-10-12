package cn.inkforge.core.references.application;

import java.time.OffsetDateTime;
import org.jooq.DSLContext;

/** 只为本次新索引代次原子登记执行；禁止网络请求或将旧 pending 代次改换引擎。 */
public interface RagIndexRunStarter {
    void bindNewGeneration(DSLContext transaction, String userId, String novelId, String referenceId,
            String content, String contentHash, OffsetDateTime generation);
}
