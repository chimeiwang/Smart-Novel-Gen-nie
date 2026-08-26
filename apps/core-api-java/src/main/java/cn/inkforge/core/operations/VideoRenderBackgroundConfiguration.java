package cn.inkforge.core.operations;

import cn.inkforge.core.operations.background.BackgroundTaskManager;
import cn.inkforge.core.operations.background.BackgroundWorker;
import cn.inkforge.core.video.application.VideoRenderReconciler;
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** Operations 单向托管逐镜 Seedance 耐久任务协调循环。 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnBean(VideoRenderReconciler.class)
class VideoRenderBackgroundConfiguration {

    @Bean
    SmartInitializingSingleton videoRenderReconcilerStarter(
            BackgroundTaskManager tasks, VideoRenderReconciler reconciler) {
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
        return () -> tasks.start("video_render_reconciler", worker);
    }
}
