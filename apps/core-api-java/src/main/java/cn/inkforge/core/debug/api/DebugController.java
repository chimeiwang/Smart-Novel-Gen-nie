package cn.inkforge.core.debug.api;

import cn.inkforge.contracts.api.WorkflowRunDetailResponse;
import cn.inkforge.contracts.api.WorkflowRunListResponse;
import cn.inkforge.core.agentgateway.AgentServiceClient;
import cn.inkforge.core.generated.api.DebugApi;
import cn.inkforge.core.identity.application.AuthenticatedUser;
import cn.inkforge.core.identity.application.CurrentUserAccess;
import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.http.ApiException;
import java.util.Map;
import java.util.Optional;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RestController;
import tools.jackson.databind.ObjectMapper;

/** 默认隐藏、只转发当前用户身份的 Agent 工作流调试接口。 */
@RestController
public final class DebugController implements DebugApi {

    private final CoreSettings settings;
    private final Optional<AgentServiceClient> configuredClient;
    private final Optional<CurrentUserAccess> configuredUsers;
    private final ObjectMapper json;

    public DebugController(
            CoreSettings settings,
            Optional<AgentServiceClient> configuredClient,
            Optional<CurrentUserAccess> configuredUsers,
            ObjectMapper json) {
        this.settings = settings;
        this.configuredClient = configuredClient;
        this.configuredUsers = configuredUsers;
        this.json = json;
    }

    @Override
    public ResponseEntity<WorkflowRunListResponse> listWorkflowRunsApiV1DebugWorkflowRunsGet(
            String token) {
        AuthenticatedUser user = user(token);
        Map<String, Object> result = client().getWorkflowRuns(user.id(), null);
        return ResponseEntity.ok(convert(result, WorkflowRunListResponse.class));
    }

    @Override
    public ResponseEntity<WorkflowRunDetailResponse> getWorkflowRunApiV1DebugWorkflowRunsRunIdGet(
            String runId, String token) {
        AuthenticatedUser user = user(token);
        Map<String, Object> result = client().getWorkflowRuns(user.id(), runId);
        return ResponseEntity.ok(convert(result, WorkflowRunDetailResponse.class));
    }

    private AgentServiceClient client() {
        if (!settings.workflowEventDebugEnabled()) {
            throw new ApiException(404, "NOT_FOUND", "调试接口未启用");
        }
        return configuredClient.orElseThrow(() -> new ApiException(
                503,
                "AGENT_DEBUG_UNAVAILABLE",
                "智能体调试服务暂时不可用"));
    }

    private AuthenticatedUser user(String token) {
        return configuredUsers.orElseThrow(() ->
                        new ApiException(503, "AUTH_UNAVAILABLE", "认证服务暂时不可用"))
                .require(token);
    }

    private <T> T convert(Map<String, Object> value, Class<T> type) {
        return json.convertValue(value, type);
    }
}
