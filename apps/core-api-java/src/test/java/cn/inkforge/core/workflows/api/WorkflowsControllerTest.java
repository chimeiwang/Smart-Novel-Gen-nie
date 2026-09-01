package cn.inkforge.core.workflows.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import cn.inkforge.contracts.api.ExecutionCallbackReceipt;
import cn.inkforge.contracts.api.ExecutionStepProgress;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.http.InternalServiceAuthenticator;
import cn.inkforge.core.workflows.application.WorkflowCallbackRepository;
import cn.inkforge.core.workflows.application.WorkflowCallbackResources;
import cn.inkforge.serviceauth.ServiceScope;
import java.nio.charset.StandardCharsets;
import java.util.Optional;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.openapitools.jackson.nullable.JsonNullable;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

class WorkflowsControllerTest {

    private final WorkflowCallbackRepository callbacks = mock(WorkflowCallbackRepository.class);
    private final InternalServiceAuthenticator authenticator = mock(InternalServiceAuthenticator.class);
    private final WorkflowsController controller =
            new WorkflowsController(Optional.of(callbacks), Optional.of(authenticator));

    @AfterEach
    void clearRequest() {
        RequestContextHolder.resetRequestAttributes();
    }

    @Test
    void 路径与正文不一致时在查库验签前拒绝() {
        ExecutionStepProgress body = progress("run-body", "step-body", "novel-1");

        assertThatThrownBy(() -> controller
                        .reportExecutionProgressInternalV1WorkflowRunsRunIdStepsStepIdProgressPut(
                                "run-path", "step-path", body))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(409);
                    assertThat(error.code()).isEqualTo("WORKFLOW_RESOURCE_MISMATCH");
                });
        verifyNoInteractions(callbacks, authenticator);
    }

    @Test
    void progress按数据库归属和Step身份验签后始终返回200Receipt() {
        bindRequest("PUT", "/internal/v1/workflow-runs/run-1/steps/step-1/progress", "{\"x\":1}");
        ExecutionStepProgress body = progress("run-1", "step-1", "novel-1");
        ExecutionCallbackReceipt receipt = mock(ExecutionCallbackReceipt.class);
        when(callbacks.resources("run-1", "step-1"))
                .thenReturn(new WorkflowCallbackResources("run-1", "step-1", "novel-1"));
        when(callbacks.progress(body)).thenReturn(receipt);

        var response = controller
                .reportExecutionProgressInternalV1WorkflowRunsRunIdStepsStepIdProgressPut(
                        "run-1", "step-1", body);

        assertThat(response.getStatusCode().value()).isEqualTo(200);
        assertThat(response.getBody()).isSameAs(receipt);
        verify(authenticator).authenticate(
                any(),
                any(byte[].class),
                eq(ServiceScope.EXECUTION_PROGRESS),
                eq("step-1"),
                eq("run-1"),
                eq("novel-1"),
                anyString(),
                anyString());
    }

    private static ExecutionStepProgress progress(String runId, String stepId, String novelId) {
        ExecutionStepProgress body = mock(ExecutionStepProgress.class);
        when(body.getRunId()).thenReturn(runId);
        when(body.getStepId()).thenReturn(stepId);
        when(body.getNovelId()).thenReturn(JsonNullable.of(novelId));
        return body;
    }

    private static void bindRequest(String method, String path, String body) {
        MockHttpServletRequest request = new MockHttpServletRequest(method, path);
        request.setAttribute(
                "cn.inkforge.core.platform.http.RawRequestBody.bytes",
                body.getBytes(StandardCharsets.UTF_8));
        RequestContextHolder.setRequestAttributes(new ServletRequestAttributes(request));
    }
}
