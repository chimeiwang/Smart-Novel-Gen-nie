package cn.inkforge.core.operations;

import cn.inkforge.core.video.application.LegacyVideoPlanDispatcher;
import cn.inkforge.core.operations.background.BackgroundTaskManager;
import cn.inkforge.core.operations.background.BackgroundWorker;
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** 监督历史 VideoScene 任务补投；公共旧场景准入已经永久关闭。 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnBean(LegacyVideoPlanDispatcher.class)
class LegacyVideoPlanBackgroundConfiguration {

    @Bean
    SmartInitializingSingleton legacyVideoPlanDispatcherStarter(
            BackgroundTaskManager tasks, LegacyVideoPlanDispatcher dispatcher) {
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
        return () -> tasks.start("legacy_video_plan_dispatcher", worker);
    }
}
