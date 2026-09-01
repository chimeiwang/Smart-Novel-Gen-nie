package cn.inkforge.core.billing.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import cn.inkforge.contracts.api.BillingReconciliationReceipt;
import cn.inkforge.contracts.api.BillingReconciliationRequest;
import cn.inkforge.core.billing.reconciliation.WorkflowBillingReconciliation;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.http.InternalServiceAuthenticator;
import cn.inkforge.serviceauth.ServiceScope;
import java.nio.charset.StandardCharsets;
import java.util.Optional;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.mockito.InOrder;
import org.openapitools.jackson.nullable.JsonNullable;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

class BillingReconciliationControllerTest {

    @AfterEach
    void clearRequest() {
        RequestContextHolder.resetRequestAttributes();
    }

    @Test
    void 未认证请求在任何对账端口调用前失败() {
        WorkflowBillingReconciliation reconciliation = mock(WorkflowBillingReconciliation.class);
        BillingController controller = new BillingController(
                Optional.empty(),
                Optional.empty(),
                Optional.empty(),
                Optional.of(reconciliation));
        BillingReconciliationRequest request = request("run-1", "step-1", "novel-1");

        assertThatThrownBy(() -> controller
                        .reconcileWorkflowBillingInternalV1WorkflowRunsRunIdStepsStepIdBillingReconciliationPut(
                                "run-1", "step-1", request))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(503);
                    assertThat(error.code())
                            .isEqualTo("WORKFLOW_BILLING_RECONCILIATION_AUTH_UNAVAILABLE");
                });
        verifyNoInteractions(reconciliation);
    }

    @Test
    void 对账必须先完成独立Scope验签再调用应用端口() {
        WorkflowBillingReconciliation reconciliation = mock(WorkflowBillingReconciliation.class);
        InternalServiceAuthenticator authenticator = mock(InternalServiceAuthenticator.class);
        BillingController controller = new BillingController(
                Optional.empty(),
                Optional.empty(),
                Optional.of(authenticator),
                Optional.of(reconciliation));
        BillingReconciliationRequest request = request("run-1", "step-1", "novel-1");
        BillingReconciliationReceipt receipt = mock(BillingReconciliationReceipt.class);
        when(reconciliation.reconcile(request)).thenReturn(receipt);
        bindRequest();

        var response = controller
                .reconcileWorkflowBillingInternalV1WorkflowRunsRunIdStepsStepIdBillingReconciliationPut(
                        "run-1", "step-1", request);

        assertThat(response.getBody()).isSameAs(receipt);
        InOrder order = inOrder(authenticator, reconciliation);
        order.verify(authenticator).authenticate(
                any(),
                any(byte[].class),
                eq(ServiceScope.BILLING_RECONCILE),
                eq("step-1"),
                eq("run-1"),
                eq("novel-1"),
                anyString(),
                anyString());
        order.verify(reconciliation).reconcile(request);
    }

    @Test
    void 路径与正文不一致时不触发验签或对账() {
        WorkflowBillingReconciliation reconciliation = mock(WorkflowBillingReconciliation.class);
        InternalServiceAuthenticator authenticator = mock(InternalServiceAuthenticator.class);
        BillingController controller = new BillingController(
                Optional.empty(),
                Optional.empty(),
                Optional.of(authenticator),
                Optional.of(reconciliation));

        assertThatThrownBy(() -> controller
                        .reconcileWorkflowBillingInternalV1WorkflowRunsRunIdStepsStepIdBillingReconciliationPut(
                                "run-path", "step-1", request("run-body", "step-1", "novel-1")))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("WORKFLOW_RESOURCE_MISMATCH"));
        verifyNoInteractions(authenticator, reconciliation);
    }

    private static BillingReconciliationRequest request(
            String runId, String stepId, String novelId) {
        BillingReconciliationRequest request = mock(BillingReconciliationRequest.class);
        when(request.getRunId()).thenReturn(runId);
        when(request.getStepId()).thenReturn(stepId);
        when(request.getNovelId()).thenReturn(JsonNullable.of(novelId));
        return request;
    }

    private static void bindRequest() {
        MockHttpServletRequest request = new MockHttpServletRequest(
                "PUT",
                "/internal/v1/workflow-runs/run-1/steps/step-1/billing-reconciliation");
        request.setAttribute(
                "cn.inkforge.core.platform.http.RawRequestBody.bytes",
                "{\"protocolVersion\":\"2.0\"}".getBytes(StandardCharsets.UTF_8));
        RequestContextHolder.setRequestAttributes(new ServletRequestAttributes(request));
    }
}
