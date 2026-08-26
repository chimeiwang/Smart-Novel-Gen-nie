package cn.inkforge.core.operations;

import cn.inkforge.core.operations.background.BackgroundTaskManager;
import cn.inkforge.core.operations.background.BackgroundWorker;
import cn.inkforge.core.styles.application.PortraitTaskDispatcher;
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** Operations 单向托管画像任务对账循环。 */
@Configuration(proxyBeanMethods = false)
class PortraitBackgroundConfiguration {

    @Bean
    SmartInitializingSingleton portraitTaskDispatcherStarter(
            BackgroundTaskManager tasks,
            ObjectProvider<PortraitTaskDispatcher> dispatchers) {
        return () -> {
            // 条件 Bean 在配置扫描阶段可能尚未登记；启动期再解析，保证有数据库文风域时一定接管 pending。
            PortraitTaskDispatcher dispatcher = dispatchers.getIfAvailable();
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
            tasks.start("portrait_task_dispatcher", worker);
        };
    }
}
