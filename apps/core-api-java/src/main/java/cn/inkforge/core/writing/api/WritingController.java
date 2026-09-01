package cn.inkforge.core.writing.api;

import cn.inkforge.contracts.api.AgentEvent;
import cn.inkforge.contracts.api.CallbackReceipt;
import cn.inkforge.contracts.api.CancelWritingRunRequest;
import cn.inkforge.contracts.api.CancelWritingRunPublicResponse;
import cn.inkforge.contracts.api.CheckpointCallback;
import cn.inkforge.contracts.api.CreateMessageRequest;
import cn.inkforge.contracts.api.CreateWritingSessionRequest;
import cn.inkforge.contracts.api.MessageResponse;
import cn.inkforge.contracts.api.ResumeWritingRunRequest;
import cn.inkforge.contracts.api.ResumeWritingRunResponse;
import cn.inkforge.contracts.api.RunCompletionCallback;
import cn.inkforge.contracts.api.RunFailureCallback;
import cn.inkforge.contracts.api.ToolCallBody;
import cn.inkforge.contracts.api.ToolCallResponse;
import cn.inkforge.contracts.api.UpdateWritingSessionRequest;
import cn.inkforge.contracts.api.WritingRunListResponse;
import cn.inkforge.contracts.api.WritingRunStartResponse;
import cn.inkforge.contracts.api.WritingRunStatusPublicResponse;
import cn.inkforge.contracts.api.WritingSessionDetail;
import cn.inkforge.contracts.api.WritingSessionListItem;
import cn.inkforge.contracts.api.WritingSessionResponse;
import cn.inkforge.core.generated.api.WritingApi;
import cn.inkforge.core.generated.model.WritingRunStartBody;
import cn.inkforge.core.identity.application.AuthenticatedUser;
import cn.inkforge.core.identity.application.CurrentUserAccess;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.http.InternalServiceAuthenticator;
import cn.inkforge.core.platform.http.RawRequestBody;
import cn.inkforge.core.writing.application.WritingCallbackRepository;
import cn.inkforge.core.writing.application.WritingCallbackService;
import cn.inkforge.core.writing.application.WritingEventStreamService;
import cn.inkforge.core.writing.application.WritingRunService;
import cn.inkforge.core.writing.application.WritingSessionService;
import cn.inkforge.core.writing.application.WritingToolGateway;
import cn.inkforge.core.writing.application.WritingToolRequest;
import cn.inkforge.serviceauth.ServiceScope;
import jakarta.servlet.http.HttpServletRequest;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import org.openapitools.jackson.nullable.JsonNullable;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

/** 写作会话、耐久运行、受签名回调、工具网关与 SSE 的冻结 HTTP 入口。 */
@RestController
public final class WritingController implements WritingApi {

    private final Optional<WritingSessionService> configuredSessions;
    private final Optional<WritingRunService> configuredRuns;
    private final Optional<WritingCallbackService> configuredCallbacks;
    private final Optional<WritingCallbackRepository> configuredCallbackRepository;
    private final Optional<WritingToolGateway> configuredTools;
    private final Optional<WritingEventStreamService> configuredStreams;
    private final Optional<CurrentUserAccess> configuredUsers;
    private final Optional<InternalServiceAuthenticator> configuredAuthenticator;

    public WritingController(
            Optional<WritingSessionService> configuredSessions,
            Optional<WritingRunService> configuredRuns,
            Optional<WritingCallbackService> configuredCallbacks,
            Optional<WritingCallbackRepository> configuredCallbackRepository,
            Optional<WritingToolGateway> configuredTools,
            Optional<WritingEventStreamService> configuredStreams,
            Optional<CurrentUserAccess> configuredUsers,
            Optional<InternalServiceAuthenticator> configuredAuthenticator) {
        this.configuredSessions = configuredSessions;
        this.configuredRuns = configuredRuns;
        this.configuredCallbacks = configuredCallbacks;
        this.configuredCallbackRepository = configuredCallbackRepository;
        this.configuredTools = configuredTools;
        this.configuredStreams = configuredStreams;
        this.configuredUsers = configuredUsers;
        this.configuredAuthenticator = configuredAuthenticator;
    }

    @Override
    public ResponseEntity<MessageResponse>
            addWritingMessageApiV1WritingSessionsSessionIdMessagesPost(
                    String sessionId,
                    CreateMessageRequest request,
                    String inkforgeToken) {
        return ResponseEntity.status(201)
                .body(sessions().addMessage(user(inkforgeToken).id(), sessionId, request));
    }

    @Override
    public ResponseEntity<CancelWritingRunPublicResponse>
            cancelWritingRunApiV1WritingRunsTaskIdCancelPost(
                    String taskId,
                    CancelWritingRunRequest request,
                    String inkforgeToken) {
        return ResponseEntity.accepted()
                .body(runs().cancel(user(inkforgeToken).id(), taskId, request));
    }

    @Override
    public ResponseEntity<WritingSessionResponse>
            createWritingSessionApiV1WritingSessionsPost(
                    CreateWritingSessionRequest request, String inkforgeToken) {
        return ResponseEntity.status(201)
                .body(sessions().create(user(inkforgeToken).id(), request));
    }

    @Override
    public ResponseEntity<Void> deleteWritingSessionApiV1WritingSessionsSessionIdDelete(
            String sessionId, String inkforgeToken) {
        sessions().delete(user(inkforgeToken).id(), sessionId);
        return ResponseEntity.noContent().build();
    }

    @Override
    public ResponseEntity<WritingRunStatusPublicResponse>
            getWritingRunStatusApiV1WritingRunsTaskIdGet(
                    String taskId, String inkforgeToken) {
        return ResponseEntity.ok(runs().get(user(inkforgeToken).id(), taskId));
    }

    @Override
    public ResponseEntity<WritingSessionDetail>
            getWritingSessionApiV1WritingSessionsSessionIdGet(
                    String sessionId, String inkforgeToken) {
        return ResponseEntity.ok(sessions().get(user(inkforgeToken).id(), sessionId));
    }

    @Override
    public ResponseEntity<WritingRunListResponse> listWritingRunsApiV1WritingRunsGet(
            String novelId,
            String chapterId,
            String writingSessionId,
            String operation,
            String outcome,
            String cursor,
            Integer limit,
            String inkforgeToken) {
        return ResponseEntity.ok(runs().list(
                user(inkforgeToken).id(),
                novelId,
                chapterId,
                writingSessionId,
                operation,
                outcome,
                cursor,
                limit == null ? 50 : limit));
    }

    @Override
    public ResponseEntity<List<WritingSessionListItem>>
            listWritingSessionsApiV1WritingSessionsGet(
                    String novelId, String chapterId, String inkforgeToken) {
        return ResponseEntity.ok(
                sessions().list(user(inkforgeToken).id(), novelId, chapterId));
    }

    @Override
    public ResponseEntity<ResumeWritingRunResponse>
            resumeWritingRunApiV1WritingRunsTaskIdResumePost(
                    String taskId,
                    ResumeWritingRunRequest request,
                    String inkforgeToken) {
        return ResponseEntity.accepted()
                .body(runs().resume(user(inkforgeToken).id(), taskId, request));
    }

    @Override
    public ResponseEntity<WritingRunStartResponse> startWritingRunApiV1WritingRunsPost(
            WritingRunStartBody request, String inkforgeToken) {
        return ResponseEntity.accepted().body(runs().start(user(inkforgeToken).id(), request));
    }

    @Override
    public ResponseEntity<StreamingResponseBody>
            streamWritingRunEventsApiV1WritingRunsTaskIdEventsGet(
                    String taskId, String lastEventID, String inkforgeToken) {
        StreamingResponseBody body = streams().stream(
                user(inkforgeToken).id(), taskId, lastEventID);
        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_EVENT_STREAM)
                .header(HttpHeaders.CACHE_CONTROL, "no-cache, no-transform")
                .header("X-Accel-Buffering", "no")
                .body(body);
    }

    @Override
    public ResponseEntity<WritingSessionResponse>
            updateWritingSessionApiV1WritingSessionsSessionIdPatch(
                    String sessionId,
                    UpdateWritingSessionRequest request,
                    String inkforgeToken) {
        return ResponseEntity.ok(
                sessions().update(user(inkforgeToken).id(), sessionId, request));
    }

    @Override
    public ResponseEntity<CallbackReceipt> acceptEventInternalV1WritingRunsRunIdEventsPost(
            String runId, AgentEvent body) {
        verifyCallback(
                runId,
                body.getRunId(),
                body.getTaskId(),
                ServiceScope.CALLBACK_EVENT);
        return ResponseEntity.ok(callbacks().acceptEvent(body));
    }

    @Override
    public ResponseEntity<CallbackReceipt> saveCheckpointInternalV1WritingRunsRunIdCheckpointPut(
            String runId, CheckpointCallback body) {
        WritingCallbackRepository.TaskResources resources = verifyCallback(
                runId,
                body.getRunId(),
                body.getTaskId(),
                ServiceScope.CALLBACK_CHECKPOINT);
        return ResponseEntity.ok(callbacks().saveCheckpoint(
                body, resources.userId(), resources.novelId()));
    }

    @Override
    public ResponseEntity<CallbackReceipt> completeRunInternalV1WritingRunsRunIdCompletePut(
            String runId, RunCompletionCallback body) {
        verifyCallback(
                runId,
                body.getRunId(),
                body.getTaskId(),
                ServiceScope.CALLBACK_COMPLETE);
        return ResponseEntity.ok(callbacks().complete(body));
    }

    @Override
    public ResponseEntity<CallbackReceipt> failRunInternalV1WritingRunsRunIdFailPut(
            String runId, RunFailureCallback body) {
        verifyCallback(
                runId,
                body.getRunId(),
                body.getTaskId(),
                ServiceScope.CALLBACK_FAIL);
        return ResponseEntity.ok(callbacks().fail(body));
    }

    @Override
    public ResponseEntity<ToolCallResponse> executeInternalToolInternalV1ToolsToolNamePost(
            String toolName, ToolCallBody body) {
        WritingToolGateway gateway = tools();
        ServiceScope scope = gateway.isReadOnly(toolName)
                ? ServiceScope.TOOL_READ
                : ServiceScope.TOOL_WRITE;
        authenticate(
                scope,
                body.getTaskId(),
                body.getRunId(),
                body.getNovelId(),
                "TOOL_GATEWAY_UNAVAILABLE",
                "智能体工具网关暂时不可用");
        return ResponseEntity.ok(new ToolCallResponse(gateway.execute(new WritingToolRequest(
                body.getUserId(),
                body.getNovelId(),
                body.getTaskId(),
                body.getRunId(),
                nullable(body.getJobId()),
                body.getAgentId(),
                toolName,
                body.getArguments()))));
    }

    private WritingCallbackRepository.TaskResources verifyCallback(
            String pathRunId,
            String bodyRunId,
            String taskId,
            ServiceScope scope) {
        if (!Objects.equals(pathRunId, bodyRunId)) {
            throw new ApiException(409, "RUN_ID_MISMATCH", "路径运行标识与回调载荷不一致");
        }
        WritingCallbackRepository.TaskResources resources = callbackRepository().resources(taskId);
        authenticate(
                scope,
                taskId,
                pathRunId,
                resources.novelId(),
                "WRITING_CALLBACK_UNAVAILABLE",
                "写作运行回调认证暂时不可用");
        return resources;
    }

    private void authenticate(
            ServiceScope scope,
            String taskId,
            String runId,
            String novelId,
            String unavailableCode,
            String unavailableMessage) {
        configuredAuthenticator.orElseThrow(() -> new ApiException(
                        503, unavailableCode, unavailableMessage))
                .authenticate(
                        currentRequest(),
                        RawRequestBody.current(),
                        scope,
                        taskId,
                        runId,
                        novelId,
                        unavailableCode,
                        unavailableMessage);
    }

    private WritingSessionService sessions() {
        return configuredSessions.orElseThrow(() -> new ApiException(
                503, "WRITING_UNAVAILABLE", "写作服务暂时不可用"));
    }

    private WritingRunService runs() {
        return configuredRuns.orElseThrow(() -> new ApiException(
                503, "WRITING_TASK_UNAVAILABLE", "写作任务服务暂时不可用"));
    }

    private WritingCallbackService callbacks() {
        return configuredCallbacks.orElseThrow(() -> new ApiException(
                503, "WRITING_CALLBACK_UNAVAILABLE", "写作运行回调暂时不可用"));
    }

    private WritingCallbackRepository callbackRepository() {
        return configuredCallbackRepository.orElseThrow(() -> new ApiException(
                503, "WRITING_CALLBACK_UNAVAILABLE", "写作运行回调暂时不可用"));
    }

    private WritingToolGateway tools() {
        return configuredTools.orElseThrow(() -> new ApiException(
                503, "TOOL_GATEWAY_UNAVAILABLE", "智能体工具网关暂时不可用"));
    }

    private WritingEventStreamService streams() {
        return configuredStreams.orElseThrow(() -> new ApiException(
                503, "WRITING_EVENTS_UNAVAILABLE", "写作事件流暂时不可用"));
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
        throw new ApiException(500, "REQUEST_CONTEXT_UNAVAILABLE", "内部请求上下文不可用");
    }

    private static <T> T nullable(JsonNullable<T> value) {
        return value == null || value.isUndefined() ? null : value.orElse(null);
    }
}
