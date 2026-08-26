package cn.inkforge.core.writing.application;

import cn.inkforge.core.references.domain.RagSearchHit;
import java.util.List;

/** 读取工具访问已生成 pgvector 索引的窄端口。 */
@FunctionalInterface
public interface WritingSemanticReferenceReader {

    List<RagSearchHit> search(
            String userId,
            String novelId,
            List<Double> embedding,
            int topK);
}
