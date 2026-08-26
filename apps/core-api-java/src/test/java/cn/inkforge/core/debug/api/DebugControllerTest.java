package cn.inkforge.core.debug.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import cn.inkforge.core.agentgateway.AgentServiceClient;
import cn.inkforge.core.identity.application.AuthenticatedUser;
import cn.inkforge.core.identity.application.CurrentUserAccess;
import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.http.ApiException;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class DebugControllerTest {

    @Test
    void 开启后只能转发Cookie当前用户并完整返回日志() {
        AgentServiceClient client = mock(AgentServiceClient.class);
        CurrentUserAccess users = mock(CurrentUserAccess.class);
        when(users.require("cookie")).thenReturn(new AuthenticatedUser("user-1", "alice"));
        Map<String, Object> summary = Map.of(
                "runId", "run-1",
                "taskId", "task-1",
                "runKind", "初次运行",
                "userId", "user-1",
                "novelId", "novel-1",
                "chapterId", "chapter-1",
                "startedAt", "2026-07-11T00:00:00Z",
                "endedAt", "2026-07-11T00:01:00Z",
                "status", "完成");
        when(client.getWorkflowRuns("user-1", null))
                .thenReturn(Map.of("runs", List.of(summary)));
        when(client.getWorkflowRuns("user-1", "run-1"))
                .thenReturn(Map.of("summary", summary, "content", "完整日志\n不截断"));
        DebugController controller = new DebugController(
                settings(true), Optional.of(client), Optional.of(users), new ObjectMapper());

        var listed = controller.listWorkflowRunsApiV1DebugWorkflowRunsGet("cookie");
        var detail = controller.getWorkflowRunApiV1DebugWorkflowRunsRunIdGet(
                "run-1", "cookie");

        assertThat(listed.getBody().getRuns()).singleElement()
                .extracting(value -> value.getUserId())
                .isEqualTo("user-1");
        assertThat(detail.getBody().getContent()).isEqualTo("完整日志\n不截断");
        verify(client).getWorkflowRuns("user-1", null);
        verify(client).getWorkflowRuns("user-1", "run-1");
    }

    @Test
    void 关闭时必须先认证再隐藏且不能调用Agent() {
        AgentServiceClient client = mock(AgentServiceClient.class);
        CurrentUserAccess users = mock(CurrentUserAccess.class);
        when(users.require("cookie")).thenReturn(new AuthenticatedUser("user-1", "alice"));
        DebugController controller = new DebugController(
                settings(false), Optional.of(client), Optional.of(users), new ObjectMapper());

        assertThatThrownBy(() ->
                        controller.listWorkflowRunsApiV1DebugWorkflowRunsGet("cookie"))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(404);
                    assertThat(error.code()).isEqualTo("NOT_FOUND");
                });
        verify(users).require("cookie");
        verify(client, never()).getWorkflowRuns("user-1", null);
    }

    private static CoreSettings settings(boolean enabled) {
        return CoreSettings.from(Map.of(
                "ENVIRONMENT", "test",
                "WORKFLOW_EVENT_DEBUG_ENABLED", Boolean.toString(enabled),
                "VIDEO_PREVIEW_ENABLED", "true"));
    }
}
