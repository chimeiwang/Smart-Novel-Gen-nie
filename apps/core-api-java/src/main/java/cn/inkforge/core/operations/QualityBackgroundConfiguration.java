package cn.inkforge.core.operations;

import cn.inkforge.core.operations.background.BackgroundTaskManager;
import cn.inkforge.core.operations.background.BackgroundWorker;
import cn.inkforge.core.quality.application.QualityRunDispatcher;
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** Operations 单向托管质量运行补投循环。 */
@Configuration(proxyBeanMethods = false)
class QualityBackgroundConfiguration {

    @Bean
    SmartInitializingSingleton qualityRunDispatcherStarter(
            BackgroundTaskManager tasks,
            ObjectProvider<QualityRunDispatcher> dispatchers) {
        return () -> {
            QualityRunDispatcher dispatcher = dispatchers.getIfAvailable();
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
            tasks.start("quality_run_dispatcher", worker);
        };
    }
}
