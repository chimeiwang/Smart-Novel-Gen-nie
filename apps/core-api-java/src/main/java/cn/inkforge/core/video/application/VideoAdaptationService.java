package cn.inkforge.core.video.application;

import cn.inkforge.contracts.api.ChapterAdaptationListResponse;
import cn.inkforge.contracts.api.ChapterAdaptationResponse;
import cn.inkforge.contracts.api.ChapterAdaptationTaskAcceptedResponse;
import cn.inkforge.contracts.api.CreateChapterAdaptationRequest;
import cn.inkforge.contracts.api.ConfirmAdaptationPlanRequest;
import cn.inkforge.contracts.api.DiscardAdaptationCandidateRequest;
import cn.inkforge.contracts.api.SaveEpisodePlanRequest;
import cn.inkforge.contracts.api.SaveShotPromptRequest;
import cn.inkforge.contracts.api.StartPromptRunRequest;
import cn.inkforge.contracts.api.StartShotPlanRunRequest;
import cn.inkforge.contracts.api.VideoAdaptationCheckpointCallback;
import cn.inkforge.contracts.api.VideoAdaptationFailureCallback;
import cn.inkforge.contracts.api.VideoAdaptationPlanCompletionCallback;
import cn.inkforge.contracts.api.VideoAdaptationPromptCompletionCallback;
import cn.inkforge.contracts.api.VideoAdaptationWorkflowProgressQuery;
import cn.inkforge.contracts.api.VideoAdaptationWorkflowProgressResponse;
import cn.inkforge.core.platform.http.ApiException;
import java.util.List;
import java.util.Objects;

/** 章节影视化的应用门禁；候选、正式版本和后期状态由后续同域服务逐层聚合。 */
public final class VideoAdaptationService {

    private final VideoAdaptationRepository repository;
    private final VideoAdaptationDecisionStore decisions;
    private final VideoAdaptationTaskStore tasks;
    private final boolean previewEnabled;

    public VideoAdaptationService(
            VideoAdaptationRepository repository,
            VideoAdaptationDecisionStore decisions,
            VideoAdaptationTaskStore tasks,
            boolean previewEnabled) {
        this.repository = Objects.requireNonNull(repository);
        this.decisions = Objects.requireNonNull(decisions);
        this.tasks = Objects.requireNonNull(tasks);
        this.previewEnabled = previewEnabled;
    }

    public ChapterAdaptationResponse create(
            String userId, String projectId, CreateChapterAdaptationRequest request) {
        requireEnabled();
        VideoAdaptationSnapshot created = repository.create(userId, projectId, request);
        return repository.getDetail(userId, created.id());
    }

    public ChapterAdaptationResponse get(String userId, String adaptationId) {
        return repository.getDetail(userId, adaptationId);
    }

    public ChapterAdaptationListResponse list(String userId, String projectId) {
        return repository.listDetails(userId, projectId);
    }

    public ChapterAdaptationResponse confirmPlan(
            String userId, String adaptationId, ConfirmAdaptationPlanRequest request) {
        requireEnabled();
        String resultId = decisions.confirmPlan(userId, adaptationId, request);
        return repository.getDetail(userId, resultId);
    }

    public ChapterAdaptationResponse saveEpisodePlan(
            String userId, String adaptationId, SaveEpisodePlanRequest request) {
        requireEnabled();
        String resultId = decisions.saveEpisodePlan(userId, adaptationId, request);
        return repository.getDetail(userId, resultId);
    }

    public ChapterAdaptationResponse discardCandidate(
            String userId,
            String adaptationId,
            DiscardAdaptationCandidateRequest request) {
        requireEnabled();
        String resultId = decisions.discardCandidate(userId, adaptationId, request);
        return repository.getDetail(userId, resultId);
    }

    public ChapterAdaptationResponse savePrompt(
            String userId,
            String adaptationId,
            String shotId,
            SaveShotPromptRequest request) {
        requireEnabled();
        String resultId = decisions.savePrompt(userId, adaptationId, shotId, request);
        return repository.getDetail(userId, resultId);
    }

    public ChapterAdaptationTaskAcceptedResponse startPlan(
            String userId, String adaptationId, StartShotPlanRunRequest request) {
        requireEnabled();
        VideoAdaptationTaskAcceptance accepted =
                tasks.createPlanTask(userId, adaptationId, request);
        return accepted(userId, accepted);
    }

    public ChapterAdaptationTaskAcceptedResponse startPrompts(
            String userId, String adaptationId, StartPromptRunRequest request) {
        requireEnabled();
        VideoAdaptationTaskAcceptance accepted =
                tasks.createPromptTask(userId, adaptationId, request);
        return accepted(userId, accepted);
    }

    public VideoAdaptationWorkflowProgressResponse progress(
            VideoAdaptationWorkflowProgressQuery query) {
        return tasks.progress(query);
    }

    public void saveCheckpoint(VideoAdaptationCheckpointCallback callback) {
        tasks.saveCheckpoint(callback);
    }

    public void completePlan(VideoAdaptationPlanCompletionCallback callback) {
        tasks.completePlan(callback);
    }

    public void completePrompts(VideoAdaptationPromptCompletionCallback callback) {
        tasks.completePrompts(callback);
    }

    public void fail(VideoAdaptationFailureCallback callback) {
        tasks.fail(callback);
    }

    private ChapterAdaptationTaskAcceptedResponse accepted(
            String userId, VideoAdaptationTaskAcceptance accepted) {
        return new ChapterAdaptationTaskAcceptedResponse(
                repository.getDetail(userId, accepted.adaptationId()),
                tasks.getTask(userId, accepted.taskId()));
    }

    private void requireEnabled() {
        if (!previewEnabled) {
            throw new ApiException(
                    503,
                    "VIDEO_PREVIEW_DISABLED",
                    "当前环境未开启视频开发预览写入");
        }
    }

    public static ChapterAdaptationResponse emptyResponse(VideoAdaptationSnapshot value) {
        return new ChapterAdaptationResponse(
                null,
                value.chapterId(),
                value.chapterTitle(),
                value.chapterUpdatedAt(),
                value.createdAt(),
                null,
                null,
                value.headRevision(),
                value.id(),
                null,
                value.lifecycleStatus(),
                value.novelId(),
                value.projectId(),
                List.of(),
                List.of(),
                null,
                value.sourceHash(),
                value.sourceText(),
                ChapterAdaptationResponse.StateEnum.EMPTY,
                List.of());
    }
}
