package cn.inkforge.core.shortmedium.application;

import cn.inkforge.core.shortmedium.domain.ShortMediumVersion;
import cn.inkforge.core.shortmedium.domain.VersionDocumentBinding;
import java.util.List;
import java.util.Map;
import java.util.function.Function;

/** 中短篇版本仓储端口；写操作必须把业务回调包在同一 PostgreSQL 事务内。 */
public interface ShortMediumVersionRepository {

    <T> T inDocument(
            String userId,
            String novelId,
            VersionDocumentBinding binding,
            Function<ShortMediumVersionTransaction, T> operation);

    /**
     * 候选采用事务。V1 实现保持原文档事务；支持 V2 的仓储会先锁用户幂等键和来源 Run，再锁业务写面。
     */
    default <T> T inAdoption(
            String userId,
            String novelId,
            VersionDocumentBinding binding,
            String versionId,
            String clientRequestId,
            String requestHash,
            Map<String, Object> normalizedRequest,
            Function<ShortMediumVersionTransaction, T> operation) {
        return inDocument(userId, novelId, binding, operation);
    }

    List<ShortMediumVersion> list(
            String userId, String novelId, VersionDocumentBinding binding);

    ShortMediumVersion requireVersion(String userId, String novelId, String versionId);
}
