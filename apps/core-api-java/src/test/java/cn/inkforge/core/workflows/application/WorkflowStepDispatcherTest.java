package cn.inkforge.core.workflows.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import cn.inkforge.contracts.agent.ExecutionStepRequest;
import java.time.Duration;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class WorkflowStepDispatcherTest {

    @Test
    void 确定性拒绝立即持久失败而响应未知只保留租约() {
        ExecutionStepRequest rejectedRequest = request("step-rejected");
        WorkflowDispatchRepository rejectedRepository = mock(WorkflowDispatchRepository.class);
        WorkflowExecutionSubmitter rejectedSubmitter = mock(WorkflowExecutionSubmitter.class);
        when(rejectedRepository.claimNext())
                .thenReturn(Optional.of(rejectedRequest), Optional.empty());
        when(rejectedSubmitter.submit(rejectedRequest))
                .thenThrow(new WorkflowExecutionRejectedException(
                        "EXECUTION_SUBMIT_REJECTED_409"));

        int accepted = new WorkflowStepDispatcher(
                        rejectedRepository,
                        rejectedSubmitter,
                        3,
                        Duration.ofSeconds(1))
                .runOnce();

        assertThat(accepted).isZero();
        verify(rejectedRepository)
                .recordRejected(rejectedRequest, "EXECUTION_SUBMIT_REJECTED_409");

        ExecutionStepRequest unknownRequest = request("step-unknown");
        WorkflowDispatchRepository unknownRepository = mock(WorkflowDispatchRepository.class);
        WorkflowExecutionSubmitter unknownSubmitter = mock(WorkflowExecutionSubmitter.class);
        when(unknownRepository.claimNext())
                .thenReturn(Optional.of(unknownRequest), Optional.empty());
        when(unknownSubmitter.submit(unknownRequest))
                .thenThrow(new RuntimeException("timeout"));

        new WorkflowStepDispatcher(
                        unknownRepository,
                        unknownSubmitter,
                        3,
                        Duration.ofSeconds(1))
                .runOnce();

        verify(unknownRepository, never()).recordRejected(any(), anyString());
        verify(unknownRepository, never()).recordAdmissionSaturated(any(), any());
    }

    @Test
    void 明确Journal前Admission饱和才快速释放Lease并退避() {
        ExecutionStepRequest request = request("step-saturated");
        WorkflowDispatchRepository repository = mock(WorkflowDispatchRepository.class);
        WorkflowExecutionSubmitter submitter = mock(WorkflowExecutionSubmitter.class);
        when(repository.claimNext()).thenReturn(Optional.of(request), Optional.empty());
        when(submitter.submit(request))
                .thenThrow(new WorkflowExecutionAdmissionSaturatedException(
                        Duration.ofSeconds(1)));

        int accepted = new WorkflowStepDispatcher(
                        repository,
                        submitter,
                        3,
                        Duration.ofSeconds(1))
                .runOnce();

        assertThat(accepted).isZero();
        verify(repository).recordAdmissionSaturated(request, Duration.ofSeconds(1));
        verify(repository, never()).recordRejected(any(), anyString());
    }

    private static ExecutionStepRequest request(String stepId) {
        ExecutionStepRequest request = mock(ExecutionStepRequest.class);
        when(request.getRunId()).thenReturn("run-1");
        when(request.getStepId()).thenReturn(stepId);
        when(request.getJobId()).thenReturn("job-1");
        when(request.getFencingToken()).thenReturn(1);
        return request;
    }
}
