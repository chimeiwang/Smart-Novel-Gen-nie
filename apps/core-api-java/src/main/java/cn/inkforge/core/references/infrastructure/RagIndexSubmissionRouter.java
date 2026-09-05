package cn.inkforge.core.references.infrastructure;

import cn.inkforge.core.references.application.RagIndexSubmitter;
import cn.inkforge.core.references.application.RagSubmissionException;
import cn.inkforge.core.references.domain.RagDispatchStatus;
import cn.inkforge.core.platform.http.ApiException;
import java.time.OffsetDateTime;
import java.util.Objects;
import java.util.function.Supplier;

/** 所有原自动/显式/补偿投递都先核对已登记代次，绝不按当前开关重选旧代次引擎。 */
final class RagIndexSubmissionRouter implements RagIndexSubmitter {
    private final JooqReferenceRepository repository;
    private final Supplier<RagIndexSubmitter> legacy;

    RagIndexSubmissionRouter(JooqReferenceRepository repository, Supplier<RagIndexSubmitter> legacy) {
        this.repository = Objects.requireNonNull(repository); this.legacy = Objects.requireNonNull(legacy);
    }

    @Override
    public RagDispatchStatus submit(String userId, String novelId, String referenceId, String contentHash, OffsetDateTime generation) {
        final RagDispatchStatus existing;
        try { existing = repository.recordedSubmission(userId, novelId, referenceId, contentHash, generation); }
        catch (ApiException exception) { throw new RagSubmissionException(exception.code()); }
        if (existing != null) return existing;
        RagIndexSubmitter submitter = legacy.get();
        if (submitter == null) throw new RagSubmissionException("RAG_INDEX_UNAVAILABLE");
        return submitter.submit(userId, novelId, referenceId, contentHash, generation);
    }
}
