package cn.inkforge.core.reviews.api;

import cn.inkforge.contracts.api.ArtifactConflictQuarantineRequest;
import cn.inkforge.contracts.api.ArtifactConflictQuarantineResponse;
import cn.inkforge.contracts.api.ArtifactDecisionAcceptedResponse;
import cn.inkforge.contracts.api.CreateArtifactRequest;
import cn.inkforge.contracts.api.ReviewArtifactDecisionRequest;
import cn.inkforge.contracts.api.ReviewArtifactListResponse;
import cn.inkforge.contracts.api.ReviewArtifactResponse;
import cn.inkforge.contracts.api.SubmitArtifactEvaluationRequest;
import cn.inkforge.core.generated.api.ReviewsApi;
import cn.inkforge.core.identity.application.AuthenticatedUser;
import cn.inkforge.core.identity.application.CurrentUserAccess;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.http.InternalServiceAuthenticator;
import cn.inkforge.core.platform.http.RawRequestBody;
import cn.inkforge.core.reviews.application.ReviewRepository;
import cn.inkforge.serviceauth.ServiceScope;
import jakarta.servlet.http.HttpServletRequest;
import java.util.Optional;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

/** 冻结的四个浏览器审核接口与三个 Agent 内部审核接口。 */
@RestController
public final class ReviewController implements ReviewsApi {

    private final Optional<ReviewRepository> configuredRepository;
    private final Optional<CurrentUserAccess> configuredUsers;
    private final Optional<InternalServiceAuthenticator> configuredAuthenticator;

    public ReviewController(
            Optional<ReviewRepository> configuredRepository,
            Optional<CurrentUserAccess> configuredUsers,
            Optional<InternalServiceAuthenticator> configuredAuthenticator) {
        this.configuredRepository = configuredRepository;
        this.configuredUsers = configuredUsers;
        this.configuredAuthenticator = configuredAuthenticator;
    }

    @Override
    public ResponseEntity<ReviewArtifactResponse>
            createOrReviseArtifactInternalV1ReviewArtifactsPost(
                    CreateArtifactRequest request) {
        authenticate(
                request.getTaskId(),
                request.getRunId(),
                request.getNovelId());
        return ResponseEntity.ok(repository().createOrRevise(request));
    }

    @Override
    public ResponseEntity<ArtifactDecisionAcceptedResponse>
            decideReviewArtifactApiV1ReviewArtifactsArtifactIdDecisionPost(
                    String artifactId,
                    ReviewArtifactDecisionRequest request,
                    String inkforgeToken) {
        ArtifactDecisionAcceptedResponse response = repository().decide(
                user(inkforgeToken).id(), artifactId, request);
        return ResponseEntity.accepted().body(response);
    }

    @Override
    public ResponseEntity<ReviewArtifactResponse>
            getReviewArtifactApiV1ReviewArtifactsArtifactIdGet(
                    String artifactId, String inkforgeToken) {
        return ResponseEntity.ok(repository().get(user(inkforgeToken).id(), artifactId));
    }

    @Override
    public ResponseEntity<ReviewArtifactResponse>
            getTaskReviewArtifactApiV1WritingTasksTaskIdArtifactGet(
                    String taskId, String inkforgeToken) {
        return ResponseEntity.ok(repository().getTaskArtifact(user(inkforgeToken).id(), taskId));
    }

    @Override
    public ResponseEntity<ReviewArtifactListResponse>
            listReviewArtifactsApiV1ReviewArtifactsGet(
                    String novelId,
                    String chapterId,
                    String taskId,
                    String status,
                    String kind,
                    String cursor,
                    Integer limit,
                    String inkforgeToken) {
        return ResponseEntity.ok(repository().list(
                user(inkforgeToken).id(),
                novelId,
                chapterId,
                taskId,
                status,
                kind,
                cursor,
                limit));
    }

    @Override
    public ResponseEntity<ArtifactConflictQuarantineResponse>
            quarantineArtifactAfterRevisionConflictInternalV1ReviewArtifactsArtifactIdAwaitingUserAfterConflictPost(
                    String artifactId,
                    ArtifactConflictQuarantineRequest request) {
        authenticate(
                request.getTaskId(),
                request.getRunId(),
                request.getNovelId());
        return ResponseEntity.ok(repository().quarantine(artifactId, request));
    }

    @Override
    public ResponseEntity<ReviewArtifactResponse>
            submitArtifactEvaluationInternalV1ReviewArtifactsArtifactIdEvaluationsPost(
                    String artifactId,
                    SubmitArtifactEvaluationRequest request) {
        authenticate(
                request.getTaskId(),
                request.getRunId(),
                request.getNovelId());
        return ResponseEntity.ok(repository().submitEvaluation(artifactId, request));
    }

    private void authenticate(String taskId, String runId, String novelId) {
        configuredAuthenticator.orElseThrow(() -> new ApiException(
                        503,
                        "SERVICE_AUTH_UNAVAILABLE",
                        "内部服务认证暂时不可用"))
                .authenticate(
                        currentRequest(),
                        RawRequestBody.current(),
                        ServiceScope.TOOL_WRITE,
                        taskId,
                        runId,
                        novelId,
                        "SERVICE_AUTH_UNAVAILABLE",
                        "内部服务认证暂时不可用");
    }

    private ReviewRepository repository() {
        return configuredRepository.orElseThrow(() -> new ApiException(
                503, "REVIEW_SERVICE_UNAVAILABLE", "草案审核服务暂时不可用"));
    }

    private AuthenticatedUser user(String token) {
        return configuredUsers.orElseThrow(() ->
                        new ApiException(503, "AUTH_UNAVAILABLE", "认证服务暂时不可用"))
                .require(token);
    }

    private static HttpServletRequest currentRequest() {
        if (RequestContextHolder.getRequestAttributes()
                instanceof ServletRequestAttributes attributes) {
            return attributes.getRequest();
        }
        throw new ApiException(
                500, "REQUEST_CONTEXT_UNAVAILABLE", "内部请求上下文不可用");
    }
}
