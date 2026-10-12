package cn.inkforge.core.workflows.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.Test;

class WorkflowCancellationReconcilerTest {
    @Test
    void 有界发现质量旧来源后复用原取消并继续租约收敛() {
        var cancellations = mock(WorkflowRunCancellationService.class);
        var quality = mock(WorkflowQualityCompletion.class);
        var run = new WorkflowQualityCompletion.InvalidatedRun("user", "run");
        when(quality.findInvalidatedRuns(20)).thenReturn(List.of(run));
        when(cancellations.runOnce()).thenReturn(2);
        var reconciler = new WorkflowCancellationReconciler(cancellations, Duration.ofSeconds(1), () -> quality);
        assertThat(reconciler.runOnce()).isEqualTo(3);
        var order = inOrder(quality, cancellations);
        order.verify(quality).findInvalidatedRuns(20);
        order.verify(cancellations).cancelInvalidatedQuality(run);
        order.verify(cancellations).runOnce();
        assertThat(run.cancelRequestId()).isEqualTo("quality-invalidated.run");
    }
}
