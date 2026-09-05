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
        String generationText = generationText(generation);
        String taskDigest = digestPrefix("rag:" + referenceId + ":" + contentHash);
        String runDigest =
                digestPrefix("rag:" + referenceId + ":" + contentHash + ":" + generationText);
        return new RagJobIdentity("rag-" + taskDigest, "rag-" + runDigest);
    }

    /** 原 RAG 身份的固定 UTC 毫秒格式，同时用于 V2 冻结输入，不能套用通用 execution 微秒格式。 */
    public static String generationText(OffsetDateTime generation) {
        return UTC_MILLISECONDS.format(Objects.requireNonNull(generation)
                .withOffsetSameInstant(ZoneOffset.UTC).truncatedTo(ChronoUnit.MILLIS));
    }

    private static String digestPrefix(String value) {
        return RagRules.sha256(value).substring(0, 32);
    }
}
