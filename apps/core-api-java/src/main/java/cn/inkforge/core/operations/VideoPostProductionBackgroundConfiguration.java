package cn.inkforge.core.operations;

import cn.inkforge.core.operations.background.BackgroundTaskManager;
import cn.inkforge.core.operations.background.BackgroundWorker;
import cn.inkforge.core.video.application.VideoPostProductionMediaProcessor;
import cn.inkforge.core.video.application.VideoPostProductionReconciler;
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** 仅在 FFmpeg 与 ffprobe 同时可用时托管整集导出循环。 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnBean(VideoPostProductionReconciler.class)
class VideoPostProductionBackgroundConfiguration {

    @Bean
    SmartInitializingSingleton videoPostProductionReconcilerStarter(
            BackgroundTaskManager tasks,
            VideoPostProductionReconciler reconciler,
            VideoPostProductionMediaProcessor media) {
        return () -> {
            if (!media.readiness().ready()) return;
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
            tasks.start("video_post_production_reconciler", worker);
        };
    }
}
