package cn.inkforge.core.shortmedium.application;

import cn.inkforge.core.shortmedium.domain.ShortMediumVersion;
import cn.inkforge.core.shortmedium.domain.VersionDocumentBinding;
import java.util.List;
import java.util.function.Function;

/** 中短篇版本仓储端口；写操作必须把业务回调包在同一 PostgreSQL 事务内。 */
public interface ShortMediumVersionRepository {

    <T> T inDocument(
            String userId,
            String novelId,
            VersionDocumentBinding binding,
            Function<ShortMediumVersionTransaction, T> operation);

    List<ShortMediumVersion> list(
            String userId, String novelId, VersionDocumentBinding binding);

    ShortMediumVersion requireVersion(String userId, String novelId, String versionId);
}
