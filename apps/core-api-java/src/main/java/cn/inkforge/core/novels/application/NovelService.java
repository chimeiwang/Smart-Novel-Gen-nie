package cn.inkforge.core.novels.application;

import cn.inkforge.contracts.api.CreateNovelRequest;
import cn.inkforge.contracts.api.CreateNovelResponse;
import cn.inkforge.contracts.api.DashboardResponse;
import cn.inkforge.contracts.api.NovelResponse;
import cn.inkforge.contracts.api.ShortMediumSourceKind;
import cn.inkforge.contracts.api.StoryLengthProfile;
import cn.inkforge.contracts.api.UpdateNovelSummaryRequest;
import cn.inkforge.contracts.api.WorkspaceBootstrapResponse;
import cn.inkforge.contracts.api.WorkspaceLoreResponse;
import cn.inkforge.contracts.api.WorkspacePlanningResponse;
import cn.inkforge.contracts.api.WorkspaceResourcesResponse;
import cn.inkforge.contracts.api.WorkspaceResponse;
import cn.inkforge.core.novels.domain.NovelCreation;
import cn.inkforge.core.platform.http.ApiException;
import java.util.List;
import java.util.Objects;
import org.openapitools.jackson.nullable.JsonNullable;

/** 小说创建、摘要和工作区读取的公共用例层。 */
public final class NovelService {

    private final NovelRepository repository;

    public NovelService(NovelRepository repository) {
        this.repository = Objects.requireNonNull(repository);
    }

    public CreateNovelResponse create(String userId, CreateNovelRequest request) {
        String name = request.getName().strip();
        if (name.isEmpty()) {
            throw new ApiException(
                    422, "NOVEL_NAME_REQUIRED", "小说名称不能为空");
        }
        boolean shortMedium = request.getStoryLengthProfile()
                == StoryLengthProfile.SHORT_MEDIUM;
        String clientRequestId = value(request.getClientRequestId());
        String sourceText = value(request.getSourceText());
        ShortMediumSourceKind sourceKindValue = request.getSourceKind();
        Integer requestedWords = value(request.getTargetTotalWordCount());
        validateProfile(
                shortMedium,
                clientRequestId,
                sourceKindValue,
                sourceText,
                requestedWords);

        String goal = clean(value(request.getFirstChapterGoal()));
        String protagonist = clean(value(request.getProtagonist()));
        String notes = joinNotes(protagonist, goal);
        String sourceKind = shortMedium ? sourceKindValue.getValue() : null;
        int targetWords = requestedWords == null ? 1_000_000 : requestedWords;
        return repository.create(new NovelCreation(
                userId,
                shortMedium ? clientRequestId : null,
                name,
                clean(value(request.getSummary())),
                goal == null ? null : "第一章目标：" + goal,
                request.getStoryLengthProfile().getValue(),
                targetWords,
                clean(value(request.getGenre())),
                clean(value(request.getCoreSellingPoint())),
                clean(value(request.getReaderPromise())),
                notes,
                shortMedium ? "全文" : "第一章",
                1,
                sourceKindValue == ShortMediumSourceKind.OPENING ? sourceText : "",
                sourceKindValue == ShortMediumSourceKind.OUTLINE ? sourceText : "",
                sourceKind,
                shortMedium ? sourceText : null,
                "开篇",
                goal));
    }

    public DashboardResponse dashboard(String userId) {
        return repository.dashboard(userId);
    }

    public List<NovelResponse> list(String userId, StoryLengthProfile profile) {
        return repository.list(userId, profile);
    }

    public NovelResponse get(String userId, String novelId) {
        return repository.get(novelId, userId);
    }

    public NovelResponse updateSummary(
            String userId,
            String novelId,
            UpdateNovelSummaryRequest request) {
        return repository.updateSummary(
                novelId,
                userId,
                clean(value(request.getSummary())),
                request.getExpectedUpdatedAt());
    }

    public WorkspaceResponse workspace(
            String userId, String novelId, String chapterId) {
        return repository.workspace(novelId, userId, chapterId);
    }

    public WorkspaceBootstrapResponse workspaceBootstrap(
            String userId, String novelId, String chapterId) {
        return repository.workspaceBootstrap(novelId, userId, chapterId);
    }

    public WorkspaceLoreResponse workspaceLore(String userId, String novelId) {
        return repository.workspaceLore(novelId, userId);
    }

    public WorkspacePlanningResponse workspacePlanning(
            String userId, String novelId) {
        return repository.workspacePlanning(novelId, userId);
    }

    public WorkspaceResourcesResponse workspaceResources(
            String userId, String novelId) {
        return repository.workspaceResources(novelId, userId);
    }

    private static void validateProfile(
            boolean shortMedium,
            String clientRequestId,
            ShortMediumSourceKind sourceKind,
            String sourceText,
            Integer targetWords) {
        if (shortMedium) {
            if (clientRequestId == null
                    || clientRequestId.length() < 16
                    || clientRequestId.length() > 128
                    || sourceKind == null
                    || sourceText == null
                    || sourceText.strip().isEmpty()
                    || targetWords == null
                    || targetWords < 6_000
                    || targetWords > 80_000) {
                throw validationError();
            }
            return;
        }
        if (clientRequestId != null
                || sourceKind != null
                || sourceText != null
                || (targetWords != null && targetWords <= 0)) {
            throw validationError();
        }
    }

    private static String joinNotes(String protagonist, String goal) {
        StringBuilder notes = new StringBuilder();
        if (protagonist != null) notes.append("主角起点：").append(protagonist);
        if (goal != null) {
            if (!notes.isEmpty()) notes.append('\n');
            notes.append("第一章目标：").append(goal);
        }
        return notes.isEmpty() ? null : notes.toString();
    }

    private static String clean(String value) {
        if (value == null) return null;
        String cleaned = value.strip();
        return cleaned.isEmpty() ? null : cleaned;
    }

    private static <T> T value(JsonNullable<T> value) {
        return value == null || value.isUndefined() ? null : value.orElse(null);
    }

    private static ApiException validationError() {
        return new ApiException(422, "VALIDATION_ERROR", "请求参数校验失败");
    }
}
