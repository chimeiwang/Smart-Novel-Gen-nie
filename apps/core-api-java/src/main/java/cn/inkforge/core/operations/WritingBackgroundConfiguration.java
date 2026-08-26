package cn.inkforge.core.operations;

import cn.inkforge.core.operations.background.BackgroundTaskManager;
import cn.inkforge.core.operations.background.BackgroundWorker;
import cn.inkforge.core.writing.application.WritingRunCommandDispatcher;
import cn.inkforge.core.writing.application.WritingRunReconciler;
import cn.inkforge.core.writing.application.WritingOutboxPublisher;
import cn.inkforge.core.writing.application.WritingOutboxReadiness;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** Operations 单向托管写作命令补投循环。 */
@Configuration(proxyBeanMethods = false)
class WritingBackgroundConfiguration {

    @Bean
    SmartInitializingSingleton writingRunCommandDispatcherStarter(
            BackgroundTaskManager tasks,
            ObjectProvider<WritingRunCommandDispatcher> dispatchers) {
        return () -> {
            WritingRunCommandDispatcher dispatcher = dispatchers.getIfAvailable();
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
            tasks.start("writing_command_dispatcher", worker);
        };
    }

    @Bean
    SmartInitializingSingleton writingRunReconcilerStarter(
            BackgroundTaskManager tasks,
            ObjectProvider<WritingRunReconciler> reconcilers) {
        return () -> {
            WritingRunReconciler reconciler = reconcilers.getIfAvailable();
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
            tasks.start("writing_reconciler", worker);
        };
    }

    @Bean
    SmartInitializingSingleton writingOutboxStarter(
            BackgroundTaskManager tasks,
            ReadinessRegistry readiness,
            ObjectProvider<WritingOutboxReadiness> outboxReadinesses,
            ObjectProvider<WritingOutboxPublisher> publishers) {
        return () -> {
            WritingOutboxReadiness outboxReadiness = outboxReadinesses.getIfAvailable();
            if (outboxReadiness != null) {
                readiness.register(
                        "writing_outbox",
                        outboxReadiness::check,
                        outboxReadiness::errorCodes);
            }
            WritingOutboxPublisher publisher = publishers.getIfAvailable();
            if (publisher == null) return;
            BackgroundWorker worker = new BackgroundWorker() {
                @Override
                public void run() throws Exception {
                    publisher.run();
                }

                @Override
                public void requestStop() {
                    publisher.requestStop();
                }
            };
            tasks.start("writing_outbox_publisher", worker);
        };
    }
}
