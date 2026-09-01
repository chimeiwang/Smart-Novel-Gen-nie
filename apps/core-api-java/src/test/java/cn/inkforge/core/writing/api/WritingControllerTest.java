package cn.inkforge.core.writing.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import cn.inkforge.contracts.api.AgentEvent;
import cn.inkforge.contracts.api.CallbackReceipt;
import cn.inkforge.contracts.api.CheckpointCallback;
import cn.inkforge.contracts.api.CreateWritingSessionRequest;
import cn.inkforge.contracts.api.ToolCallBody;
import cn.inkforge.contracts.api.WritingSessionResponse;
import cn.inkforge.core.identity.application.AuthenticatedUser;
import cn.inkforge.core.identity.application.CurrentUserAccess;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.http.InternalServiceAuthenticator;
import cn.inkforge.core.platform.http.ManagedSseEmitter;
import cn.inkforge.core.writing.application.WritingCallbackRepository;
import cn.inkforge.core.writing.application.WritingCallbackService;
import cn.inkforge.core.writing.application.WritingEventStreamService;
import cn.inkforge.core.writing.application.WritingRunService;
import cn.inkforge.core.writing.application.WritingSessionService;
import cn.inkforge.core.writing.application.WritingToolGateway;
import cn.inkforge.serviceauth.ServiceScope;
import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

class WritingControllerTest {

    private final WritingSessionService sessions = mock(WritingSessionService.class);
    private final WritingRunService runs = mock(WritingRunService.class);
    private final WritingCallbackService callbacks = mock(WritingCallbackService.class);
    private final WritingCallbackRepository callbackRepository = mock(WritingCallbackRepository.class);
    private final WritingToolGateway tools = mock(WritingToolGateway.class);
    private final WritingEventStreamService streams = mock(WritingEventStreamService.class);
    private final InternalServiceAuthenticator authenticator = mock(InternalServiceAuthenticator.class);
    private final CurrentUserAccess users = token -> new AuthenticatedUser("user-1", "测试用户");
    private final WritingController controller = new WritingController(
            Optional.of(sessions),
            Optional.of(runs),
            Optional.of(callbacks),
            Optional.of(callbackRepository),
            Optional.of(tools),
            Optional.of(streams),
            Optional.of(users),
            Optional.of(authenticator));

    @AfterEach
    void clearRequest() {
        RequestContextHolder.resetRequestAttributes();
    }

    @Test
    void 浏览器会话创建只使用Cookie当前用户并返回201() {
        CreateWritingSessionRequest request =
                new CreateWritingSessionRequest("chapter-1", "novel-1");
        WritingSessionResponse expected = mock(WritingSessionResponse.class);
        when(sessions.create("user-1", request)).thenReturn(expected);

        var response = controller.createWritingSessionApiV1WritingSessionsPost(
                request, "session-token");

        assertThat(response.getStatusCode().value()).isEqualTo(201);
        assertThat(response.getBody()).isSameAs(expected);
    }

    @Test
    void 回调路径运行标识不一致时必须在查库和验签前拒绝() {
        AgentEvent event = new AgentEvent(
                Map.of(),
                "progress",
                "event-1",
                "job-1",
                OffsetDateTime.parse("2026-08-25T09:00:00Z"),
                "1.1",
                "run-body",
                1,
                "task-1");

        assertThatThrownBy(() -> controller.acceptEventInternalV1WritingRunsRunIdEventsPost(
                        "run-path", event))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(409);
                    assertThat(error.code()).isEqualTo("RUN_ID_MISMATCH");
                });
        verifyNoInteractions(callbackRepository, authenticator, callbacks);
    }

    @Test
    void 检查点回调按任务资源和专属权限验签后执行() {
        bindRequest("PUT", "/internal/v1/writing/runs/run-1/checkpoint", "{\"x\":1}");
        CheckpointCallback body = new CheckpointCallback(
                Map.of("workflow", "short_medium", "operation", "full_check", "phase", "completed", "eventSequence", 1),
                "event-1",
                "job-1",
                OffsetDateTime.parse("2026-08-25T09:00:00Z"),
                "1.1",
                "run-1",
                1,
                "task-1");
        CallbackReceipt receipt = mock(CallbackReceipt.class);
        when(callbackRepository.resources("task-1"))
                .thenReturn(new WritingCallbackRepository.TaskResources("novel-1", "user-1"));
        when(callbacks.saveCheckpoint(body, "user-1", "novel-1")).thenReturn(receipt);

        var response = controller.saveCheckpointInternalV1WritingRunsRunIdCheckpointPut(
                "run-1", body);

        assertThat(response.getBody()).isSameAs(receipt);
        verify(authenticator).authenticate(
                any(),
                any(byte[].class),
                eq(ServiceScope.CALLBACK_CHECKPOINT),
                eq("task-1"),
                eq("run-1"),
                eq("novel-1"),
                anyString(),
                anyString());
    }

    @Test
    void 工具接口先选择只读权限验签再透传完整结果() {
        bindRequest("POST", "/internal/v1/tools/get_novel_info", "{\"arguments\":{}}");
        ToolCallBody body = new ToolCallBody(
                "写作", Map.of(), "novel-1", "run-1", "task-1", "user-1");
        when(tools.isReadOnly("get_novel_info")).thenReturn(true);
        when(tools.execute(any())).thenReturn(Map.of("content", "完整结果".repeat(10_000)));

        var response = controller.executeInternalToolInternalV1ToolsToolNamePost(
                "get_novel_info", body);

        assertThat(response.getBody().getResult().get("content"))
                .isEqualTo("完整结果".repeat(10_000));
        verify(authenticator).authenticate(
                any(),
                any(byte[].class),
                eq(ServiceScope.TOOL_READ),
                eq("task-1"),
                eq("run-1"),
                eq("novel-1"),
                anyString(),
                anyString());
    }

    @Test
    void 事件接口返回真实Sse媒体类型与禁用代理缓冲头() {
        bindRequest("GET", "/api/v1/writing/runs/task-1/events", "");
        ManagedSseEmitter stream = new ManagedSseEmitter(0L) {
            @Override
            protected void startManagedSession() {}

            @Override
            protected void abortManagedSession() {}
        };
        when(streams.stream("user-1", "task-1", "3-0")).thenReturn(stream);

        var response = controller.streamWritingRunEventsApiV1WritingRunsTaskIdEventsGet(
                "task-1", "3-0", "session-token");

        assertThat(response.getHeaders().getContentType())
                .isEqualTo(MediaType.TEXT_EVENT_STREAM);
        assertThat(response.getHeaders().getFirst(HttpHeaders.CACHE_CONTROL))
                .isEqualTo("no-cache, no-transform");
        assertThat(response.getHeaders().getFirst("X-Accel-Buffering")).isEqualTo("no");
        assertThat(response.getBody()).isSameAs(stream);
        var request = ((ServletRequestAttributes) RequestContextHolder.currentRequestAttributes())
                .getRequest();
        assertThat(request.getAttribute(ManagedSseEmitter.class.getName() + ".session"))
                .isSameAs(stream);
    }

    private static void bindRequest(String method, String path, String body) {
        MockHttpServletRequest request = new MockHttpServletRequest(method, path);
        request.setAttribute(
                "cn.inkforge.core.platform.http.RawRequestBody.bytes",
                body.getBytes(StandardCharsets.UTF_8));
        RequestContextHolder.setRequestAttributes(new ServletRequestAttributes(request));
    }
}
