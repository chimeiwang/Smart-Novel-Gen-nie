package cn.inkforge.core.chapters.application;

import cn.inkforge.contracts.api.ChapterListResponse;
import cn.inkforge.contracts.api.ChapterMutationResponse;
import cn.inkforge.contracts.api.ChapterProgressRequest;
import cn.inkforge.contracts.api.ChapterStatusRequest;
import cn.inkforge.contracts.api.ChapterStatusResponse;
import cn.inkforge.contracts.api.CreateChapterResponse;
import cn.inkforge.contracts.api.UpdateChapterRequest;
import cn.inkforge.contracts.api.WorkspaceChapter;
import java.util.Objects;
import cn.inkforge.core.platform.http.RequiredRequestField;

/** 章节公共接口的用例层；正文不做 trim、截断或隐式格式化。 */
public final class ChapterService {

    private final ChapterRepository repository;

    public ChapterService(ChapterRepository repository) {
        this.repository = Objects.requireNonNull(repository);
    }

    public CreateChapterResponse create(String userId, String novelId) {
        return new CreateChapterResponse(repository.create(novelId, userId));
    }

    public ChapterListResponse list(String userId, String novelId) {
        return new ChapterListResponse(repository.list(novelId, userId));
    }

    public WorkspaceChapter get(String userId, String chapterId) {
        return repository.get(chapterId, userId);
    }

    public ChapterMutationResponse update(
            String userId, String chapterId, UpdateChapterRequest request) {
        String title = request.getTitle().strip();
        if (title.isEmpty()) {
            title = "未命名章节";
        }
        return new ChapterMutationResponse(repository.updateDraft(
                chapterId,
                userId,
                title,
                request.getContent(),
                request.getExpectedUpdatedAt()));
    }

    public ChapterMutationResponse updateProgress(
            String userId, String chapterId, ChapterProgressRequest request) {
        return new ChapterMutationResponse(repository.upsertProgress(
                chapterId,
                userId,
                request.getContent(),
                RequiredRequestField.nullable(
                        request.getExpectedUpdatedAt(), "expectedUpdatedAt")));
    }

    public ChapterStatusResponse setStatus(
            String userId, String chapterId, ChapterStatusRequest request) {
        ChapterRecord record = repository.transitionStatus(
                chapterId,
                userId,
                request.getStatus(),
                request.getExpectedUpdatedAt());
        return new ChapterStatusResponse(
                record.completedAt(), record.id(), record.status(), record.updatedAt());
    }
}
