package cn.inkforge.core.references.domain;

import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;
import java.util.Objects;

/** RAG 任务稳定身份；格式与 Python 的毫秒 UTC 序列化保持字节级一致。 */
public record RagJobIdentity(String taskId, String runId) {

    private static final DateTimeFormatter UTC_MILLISECONDS =
            DateTimeFormatter.ofPattern("uuuu-MM-dd'T'HH:mm:ss.SSS'Z'");

    public RagJobIdentity {
        Objects.requireNonNull(taskId);
        Objects.requireNonNull(runId);
    }

    public static RagJobIdentity create(
            String referenceId, String contentHash, OffsetDateTime generation) {
        Objects.requireNonNull(referenceId);
        Objects.requireNonNull(contentHash);
        Objects.requireNonNull(generation);
        String generationText = UTC_MILLISECONDS.format(
                generation.withOffsetSameInstant(ZoneOffset.UTC).truncatedTo(ChronoUnit.MILLIS));
        String taskDigest = digestPrefix("rag:" + referenceId + ":" + contentHash);
        String runDigest =
                digestPrefix("rag:" + referenceId + ":" + contentHash + ":" + generationText);
        return new RagJobIdentity("rag-" + taskDigest, "rag-" + runDigest);
    }

    private static String digestPrefix(String value) {
        return RagRules.sha256(value).substring(0, 32);
    }
}
