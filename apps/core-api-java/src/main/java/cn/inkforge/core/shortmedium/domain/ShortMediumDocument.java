package cn.inkforge.core.shortmedium.domain;

import java.time.OffsetDateTime;
import java.util.Objects;

/** 当前可编辑工作稿；版本服务永远从服务端读取完整内容。 */
public record ShortMediumDocument(
        String novelId,
        String chapterId,
        VersionDocumentBinding binding,
        String artifactKey,
        String content,
        OffsetDateTime updatedAt) {

    public ShortMediumDocument {
        Objects.requireNonNull(novelId);
        Objects.requireNonNull(binding);
        Objects.requireNonNull(artifactKey);
        Objects.requireNonNull(content);
        Objects.requireNonNull(updatedAt);
    }

    public ShortMediumDocument withContent(String value, OffsetDateTime updated) {
        return new ShortMediumDocument(
                novelId, chapterId, binding, artifactKey, value, updated);
    }
}
