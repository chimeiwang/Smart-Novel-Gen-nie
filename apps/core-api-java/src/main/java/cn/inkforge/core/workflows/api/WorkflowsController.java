package cn.inkforge.core.workflows.api;

import cn.inkforge.contracts.api.ExecutionCallbackReceipt;
import cn.inkforge.contracts.api.ExecutionStepFailure;
import cn.inkforge.contracts.api.ExecutionStepProgress;
import cn.inkforge.contracts.api.ExecutionStepResult;
import cn.inkforge.core.generated.api.WorkflowsApi;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.http.InternalServiceAuthenticator;
import cn.inkforge.core.platform.http.RawRequestBody;
import cn.inkforge.core.workflows.application.WorkflowCallbackRepository;
import cn.inkforge.core.workflows.application.WorkflowCallbackResources;
import cn.inkforge.serviceauth.ServiceScope;
import jakarta.servlet.http.HttpServletRequest;
import java.util.Objects;
import java.util.Optional;
import org.openapitools.jackson.nullable.JsonNullable;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

/** V2 Workflow 的三个受签名回调入口；路径、正文、JWT 与数据库归属必须一致。 */
@RestController
@ConditionalOnProperty(
        name = "DURABLE_AGENT_EXECUTION_SCHEMA_READY",
        havingValue = "true")
public final class WorkflowsController implements WorkflowsApi {

    private final Optional<WorkflowCallbackRepository> configuredCallbacks;
    private final Optional<InternalServiceAuthenticator> configuredAuthenticator;

    public WorkflowsController(
            Optional<WorkflowCallbackRepository> configuredCallbacks,
            Optional<InternalServiceAuthenticator> configuredAuthenticator) {
        this.configuredCallbacks = configuredCallbacks;
        this.configuredAuthenticator = configuredAuthenticator;
    }

    @Override
    public ResponseEntity<ExecutionCallbackReceipt>
            reportExecutionProgressInternalV1WorkflowRunsRunIdStepsStepIdProgressPut(
                    String runId, String stepId, ExecutionStepProgress body) {
        verify(runId, stepId, body.getRunId(), body.getStepId(), body.getNovelId(),
                ServiceScope.EXECUTION_PROGRESS);
        return ResponseEntity.ok(callbacks().progress(body));
    }

    @Override
    public ResponseEntity<ExecutionCallbackReceipt>
            reportExecutionResultInternalV1WorkflowRunsRunIdStepsStepIdResultPut(
                    String runId, String stepId, ExecutionStepResult body) {
        verify(runId, stepId, body.getRunId(), body.getStepId(), body.getNovelId(),
                ServiceScope.EXECUTION_RESULT);
        return ResponseEntity.ok(callbacks().result(body));
    }

    @Override
    public ResponseEntity<ExecutionCallbackReceipt>
            reportExecutionFailureInternalV1WorkflowRunsRunIdStepsStepIdFailurePut(
                    String runId, String stepId, ExecutionStepFailure body) {
        verify(runId, stepId, body.getRunId(), body.getStepId(), body.getNovelId(),
                ServiceScope.EXECUTION_RESULT);
        return ResponseEntity.ok(callbacks().failure(body));
    }

    private void verify(
            String pathRunId,
            String pathStepId,
            String bodyRunId,
            String bodyStepId,
            JsonNullable<String> bodyNovelId,
            ServiceScope scope) {
        if (!Objects.equals(pathRunId, bodyRunId) || !Objects.equals(pathStepId, bodyStepId)) {
            throw mismatch("路径资源与 Workflow 回调载荷不一致");
        }
        WorkflowCallbackResources resources = callbacks().resources(pathRunId, pathStepId);
        String novelId = requiredNullable(bodyNovelId);
        if (!Objects.equals(resources.novelId(), novelId)) {
            throw mismatch("Workflow 回调小说归属不一致");
        }
        configuredAuthenticator.orElseThrow(() -> new ApiException(
                        503,
                        "WORKFLOW_CALLBACK_AUTH_UNAVAILABLE",
                        "耐久 Workflow 回调认证暂时不可用"))
                .authenticate(
                        currentRequest(),
                        RawRequestBody.current(),
                        scope,
                        pathStepId,
                        pathRunId,
                        novelId,
                        "WORKFLOW_CALLBACK_AUTH_UNAVAILABLE",
                        "耐久 Workflow 回调认证暂时不可用");
    }

    private WorkflowCallbackRepository callbacks() {
        return configuredCallbacks.orElseThrow(() -> new ApiException(
                503,
                "WORKFLOW_CALLBACK_UNAVAILABLE",
                "耐久 Workflow 回调暂时不可用"));
    }

    private static String requiredNullable(JsonNullable<String> value) {
        if (value == null || !value.isPresent()) {
            throw mismatch("Workflow 回调必须显式携带 novelId");
        }
        return value.get();
    }

    private static HttpServletRequest currentRequest() {
        if (RequestContextHolder.getRequestAttributes()
                instanceof ServletRequestAttributes attributes) {
            return attributes.getRequest();
        }
        throw new ApiException(500, "REQUEST_CONTEXT_UNAVAILABLE", "内部请求上下文不可用");
    }

    private static ApiException mismatch(String message) {
        return new ApiException(409, "WORKFLOW_RESOURCE_MISMATCH", message);
    }
}
