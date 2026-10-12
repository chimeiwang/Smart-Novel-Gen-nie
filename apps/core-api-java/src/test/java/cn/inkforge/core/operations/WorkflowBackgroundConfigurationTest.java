package cn.inkforge.core.operations;

import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import cn.inkforge.core.operations.background.BackgroundTaskManager;
import cn.inkforge.core.operations.background.BackgroundWorker;
import cn.inkforge.core.workflows.application.WorkflowCancellationReconciler;
import cn.inkforge.core.workflows.application.WorkflowStepDispatcher;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.ObjectProvider;

class WorkflowBackgroundConfigurationTest {

    @Test
    @SuppressWarnings("unchecked")
    void 取消收敛器无需步骤提交器也会注册独立后台任务() throws Exception {
        BackgroundTaskManager tasks = mock(BackgroundTaskManager.class);
        WorkflowCancellationReconciler reconciler = mock(WorkflowCancellationReconciler.class);
        ObjectProvider<WorkflowCancellationReconciler> provider = mock(ObjectProvider.class);
        when(provider.getIfAvailable()).thenReturn(reconciler);

        new WorkflowBackgroundConfiguration()
                .workflowCancellationReconcilerStarter(tasks, provider)
                .afterSingletonsInstantiated();

        ArgumentCaptor<BackgroundWorker> worker = ArgumentCaptor.forClass(BackgroundWorker.class);
        verify(tasks).start(eq("workflow_cancellation_reconciler"), worker.capture());
        worker.getValue().run();
        verify(reconciler).run();
        worker.getValue().requestStop();
        verify(reconciler).requestStop();
    }

    @Test
    @SuppressWarnings("unchecked")
    void 步骤提交器存在时注册独立后台任务() throws Exception {
        BackgroundTaskManager tasks = mock(BackgroundTaskManager.class);
        WorkflowStepDispatcher dispatcher = mock(WorkflowStepDispatcher.class);
        ObjectProvider<WorkflowStepDispatcher> provider = mock(ObjectProvider.class);
        when(provider.getIfAvailable()).thenReturn(dispatcher);

        new WorkflowBackgroundConfiguration()
                .workflowStepDispatcherStarter(tasks, provider)
                .afterSingletonsInstantiated();

        ArgumentCaptor<BackgroundWorker> worker = ArgumentCaptor.forClass(BackgroundWorker.class);
        verify(tasks).start(eq("workflow_step_dispatcher"), worker.capture());
        worker.getValue().run();
        verify(dispatcher).run();
        worker.getValue().requestStop();
        verify(dispatcher).requestStop();
    }
}
