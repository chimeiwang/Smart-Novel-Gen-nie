package cn.inkforge.core.video.api;

import cn.inkforge.contracts.api.*;
import cn.inkforge.core.generated.api.VideoEpisodeTasksApi;
import cn.inkforge.core.identity.application.CurrentUserAccess;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.http.InternalServiceAuthenticator;
import cn.inkforge.core.platform.http.RawRequestBody;
import cn.inkforge.core.video.infrastructure.VideoEpisodeTaskCoordinator;
import cn.inkforge.serviceauth.ServiceScope;
import jakarta.servlet.http.HttpServletRequest;
import java.util.Optional;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.http.ResponseEntity;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;
import tools.jackson.databind.ObjectMapper;

/** 视频普通任务回调的签名与归属边界；正文、路径与服务身份同时校验。 */
@RestController
public class VideoEpisodeTaskController implements VideoEpisodeTasksApi {
    private final Optional<VideoEpisodeTaskCoordinator> tasks;
    private final Optional<InternalServiceAuthenticator> auth;
    private final Optional<CurrentUserAccess> users;
    private final ObjectMapper json;
    public VideoEpisodeTaskController(Optional<VideoEpisodeTaskCoordinator> tasks,
            Optional<InternalServiceAuthenticator> auth,Optional<CurrentUserAccess> users,ObjectMapper json) {
        this.tasks=tasks;this.auth=auth;this.users=users;this.json=json;
    }
    @Override
    public ResponseEntity<VideoEpisodeTaskProgressResponse> getVideoEpisodeTaskProgress(String userId,String novelId,String taskId) {
        verify(novelId,taskId);
        return ResponseEntity.ok(json.convertValue(tasks().progress(userId,novelId,taskId),VideoEpisodeTaskProgressResponse.class));
    }
    @Override
    public ResponseEntity<Void> saveVideoEpisodeTaskCheckpoint(String userId,String novelId,String taskId,VideoEpisodeTaskCheckpointRequest body) {
        verify(novelId,taskId);tasks().checkpoint(userId,novelId,taskId,json.valueToTree(body.getCheckpoint()));
        return ResponseEntity.noContent().build();
    }
    @Override
    public ResponseEntity<Void> completeVideoEpisodeTask(String userId,String novelId,String taskId,VideoEpisodeTaskCompleteRequest body) {
        verify(novelId,taskId);tasks().complete(userId,novelId,taskId,json.valueToTree(body.getResult()));
        return ResponseEntity.noContent().build();
    }
    @Override
    public ResponseEntity<Void> failVideoEpisodeTask(String userId,String novelId,String taskId,VideoEpisodeTaskFailureRequest body) {
        verify(novelId,taskId);
        tasks().fail(userId,novelId,taskId,body.getErrorCode(),body.getErrorMessage(),body.getCancelled());
        return ResponseEntity.noContent().build();
    }
    @Override
    public ResponseEntity<VideoEpisodeScriptRunResponse> cancelVideoEpisodeTask(String episodeId,String taskId,
            VideoEpisodeTaskCancelRequest body,String inkforgeToken) {
        String userId=users.orElseThrow(()->new ApiException(503,"AUTH_UNAVAILABLE","认证服务不可用")).require(inkforgeToken).id();
        return ResponseEntity.ok(json.convertValue(tasks().cancel(userId,episodeId,taskId,body.getClientRequestId(),body.getExpectedRevision()),VideoEpisodeScriptRunResponse.class));
    }
    private void verify(String novelId,String taskId) {
        HttpServletRequest request=((ServletRequestAttributes)RequestContextHolder.currentRequestAttributes()).getRequest();
        auth.orElseThrow(()->new ApiException(503,"VIDEO_CALLBACK_AUTH_UNAVAILABLE","视频回调认证不可用"))
                .authenticate(request,RawRequestBody.current(),ServiceScope.VIDEO_WRITE,taskId,taskId,novelId,
                        "VIDEO_CALLBACK_AUTH_UNAVAILABLE","视频回调认证不可用");
    }
    private VideoEpisodeTaskCoordinator tasks(){return tasks.orElseThrow(()->new ApiException(503,"VIDEO_EPISODE_TASK_UNAVAILABLE","视频任务服务不可用"));}
}
