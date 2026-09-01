package cn.inkforge.core.operations;

import cn.inkforge.core.operations.background.BackgroundTaskManager;
import cn.inkforge.core.operations.background.BackgroundWorker;
import cn.inkforge.core.workflows.application.WorkflowCancellationReconciler;
import cn.inkforge.core.workflows.application.WorkflowStepDispatcher;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** Operations 单向托管 V2 Workflow 租约调度循环。 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        name = "DURABLE_AGENT_EXECUTION_SCHEMA_READY",
        havingValue = "true")
class WorkflowBackgroundConfiguration {

    @Bean
    SmartInitializingSingleton workflowCancellationReconcilerStarter(
            BackgroundTaskManager tasks,
            ObjectProvider<WorkflowCancellationReconciler> reconcilers) {
        return () -> {
            WorkflowCancellationReconciler reconciler = reconcilers.getIfAvailable();
            if (reconciler == null) return;
            BackgroundWorker worker = new BackgroundWorker() {
                @Override
                public void run() throws Exception {
                    reconciler.run();
                }

                @Override
                public void requestStop() {
                    reconciler.requestStop();
                }
            };
            tasks.start("workflow_cancellation_reconciler", worker);
        };
    }

    @Bean
    SmartInitializingSingleton workflowStepDispatcherStarter(
            BackgroundTaskManager tasks,
            ObjectProvider<WorkflowStepDispatcher> dispatchers) {
        return () -> {
            WorkflowStepDispatcher dispatcher = dispatchers.getIfAvailable();
            if (dispatcher == null) return;
            BackgroundWorker worker = new BackgroundWorker() {
                @Override
                public void run() throws Exception {
                    dispatcher.run();
                }

                @Override
                public void requestStop() {
                    dispatcher.requestStop();
                }
            };
            tasks.start("workflow_step_dispatcher", worker);
        };
    }
}
