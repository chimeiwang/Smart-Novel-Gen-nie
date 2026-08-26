package cn.inkforge.core.writing.infrastructure;

import cn.inkforge.core.references.application.ReferenceRepository;
import cn.inkforge.core.references.domain.RagSearchHit;
import cn.inkforge.core.writing.application.WritingSemanticReferenceReader;
import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;

/** 复用参考资料领域的归属校验与 pgvector 检索。 */
final class RepositoryWritingSemanticReferenceReader
        implements WritingSemanticReferenceReader {

    private final ReferenceRepository references;

    RepositoryWritingSemanticReferenceReader(ReferenceRepository references) {
        this.references = Objects.requireNonNull(references);
    }

    @Override
    public List<RagSearchHit> search(
            String userId,
            String novelId,
            List<Double> embedding,
            int topK) {
        return references.search(
                novelId,
                userId,
                embedding.stream().map(BigDecimal::valueOf).toList(),
                topK);
    }
}
