package cn.inkforge.core.shortmedium.domain;

import java.time.OffsetDateTime;
import java.util.Objects;
import java.util.Set;

/** ReviewArtifact 与首个 Revision 共同投影出的中短篇不可变版本。 */
public record ShortMediumVersion(
        String id,
        String novelId,
        String chapterId,
        String artifactKey,
        String status,
        String summary,
        ShortMediumVersionPayload payload,
        DocumentDiff diff,
        String createdByAgent,
        String taskId,
        OffsetDateTime createdAt,
        OffsetDateTime updatedAt,
        OffsetDateTime appliedAt) {

    private static final Set<String> STATUSES = Set.of("awaiting_user", "applied");

    public ShortMediumVersion {
        Objects.requireNonNull(id);
        Objects.requireNonNull(novelId);
        Objects.requireNonNull(artifactKey);
        Objects.requireNonNull(payload);
        Objects.requireNonNull(createdAt);
        Objects.requireNonNull(updatedAt);
        if (!STATUSES.contains(status)) {
            throw new IllegalArgumentException("中短篇版本状态无效");
        }
    }

    public String content() {
        return payload.content();
    }

    public int versionNumber() {
        return payload.versionNumber();
    }

    public ShortMediumVersion withStatus(
            String value, OffsetDateTime updated, OffsetDateTime applied) {
        return new ShortMediumVersion(
                id,
                novelId,
                chapterId,
                artifactKey,
                value,
                summary,
                payload,
                diff,
                createdByAgent,
                taskId,
                createdAt,
                updated,
                applied);
    }

    public ShortMediumVersion withDiff(DocumentDiff value) {
        return new ShortMediumVersion(
                id,
                novelId,
                chapterId,
                artifactKey,
                status,
                summary,
                payload,
                value,
                createdByAgent,
                taskId,
                createdAt,
                updatedAt,
                appliedAt);
    }
}
