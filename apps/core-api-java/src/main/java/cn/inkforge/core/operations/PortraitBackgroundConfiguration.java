package cn.inkforge.core.operations;

import cn.inkforge.core.operations.background.BackgroundTaskManager;
import cn.inkforge.core.operations.background.BackgroundWorker;
import cn.inkforge.core.styles.application.PortraitTaskDispatcher;
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** Operations 单向托管画像任务对账循环。 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnBean(PortraitTaskDispatcher.class)
class PortraitBackgroundConfiguration {

    @Bean
    SmartInitializingSingleton portraitTaskDispatcherStarter(
            BackgroundTaskManager tasks, PortraitTaskDispatcher dispatcher) {
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
        return () -> tasks.start("portrait_task_dispatcher", worker);
    }
}
