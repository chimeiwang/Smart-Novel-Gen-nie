package cn.inkforge.core.writing.infrastructure;

import cn.inkforge.core.reviews.application.ReviewRepository;
import cn.inkforge.core.reviews.domain.ReviewArtifactSummary;
import cn.inkforge.core.writing.application.WritingReviewArtifactReader;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** 复用审核领域的归属校验，并将任务摘要限制在不含草案正文的字段集合。 */
final class RepositoryWritingReviewArtifactReader implements WritingReviewArtifactReader {

    private final ReviewRepository reviews;
    private final ObjectMapper json;

    RepositoryWritingReviewArtifactReader(ReviewRepository reviews, ObjectMapper json) {
        this.reviews = Objects.requireNonNull(reviews);
        this.json = Objects.requireNonNull(json);
    }

    @Override
    public List<Map<String, Object>> listTaskArtifacts(
            String userId,
            String novelId,
            String taskId,
            String status,
            String kind) {
        return reviews.listTaskSummaries(userId, novelId, taskId, status, kind).stream()
                .map(RepositoryWritingReviewArtifactReader::summary)
                .toList();
    }

    @Override
    public Map<String, Object> get(String userId, String artifactId) {
        return json.convertValue(
                reviews.get(userId, artifactId),
                new TypeReference<Map<String, Object>>() {});
    }

    private static Map<String, Object> summary(ReviewArtifactSummary value) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("id", value.id());
        result.put("novelId", value.novelId());
        result.put("chapterId", value.chapterId());
        result.put("taskId", value.taskId());
        result.put("artifactKey", value.artifactKey());
        result.put("kind", value.kind());
        result.put("status", value.status());
        result.put("title", value.title());
        result.put("summary", value.summary());
        result.put("revision", value.revision());
        result.put("updatedByAgent", value.updatedByAgent());
        result.put("reviewerAgent", value.reviewerAgent());
        result.put("updatedAt", value.updatedAt().toString());
        return result;
    }
}
