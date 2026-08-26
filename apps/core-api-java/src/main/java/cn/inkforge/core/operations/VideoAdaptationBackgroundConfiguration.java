package cn.inkforge.core.operations;

import cn.inkforge.core.operations.background.BackgroundTaskManager;
import cn.inkforge.core.operations.background.BackgroundWorker;
import cn.inkforge.core.video.application.VideoAdaptationTaskDispatcher;
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** Operations 单向托管章节影视化任务补投循环。 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnBean(VideoAdaptationTaskDispatcher.class)
class VideoAdaptationBackgroundConfiguration {

    @Bean
    SmartInitializingSingleton videoAdaptationTaskDispatcherStarter(
            BackgroundTaskManager tasks, VideoAdaptationTaskDispatcher dispatcher) {
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
        return () -> tasks.start("video_adaptation_dispatcher", worker);
    }
}
