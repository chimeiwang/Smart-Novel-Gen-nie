package cn.inkforge.core.operations;

import cn.inkforge.core.operations.background.BackgroundTaskManager;
import cn.inkforge.core.operations.background.BackgroundWorker;
import cn.inkforge.core.video.application.VideoEpisodePostProductionReconciler;
import cn.inkforge.core.video.application.VideoPostProductionMediaProcessor;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** Operations 单向托管独立剧集后期导出的耐久协调循环。 */
@Configuration(proxyBeanMethods = false)
class VideoEpisodePostProductionBackgroundConfiguration {

    @Bean
    SmartInitializingSingleton videoEpisodePostProductionReconcilerStarter(
            BackgroundTaskManager tasks,
            ObjectProvider<VideoEpisodePostProductionReconciler> reconcilers,
            ObjectProvider<VideoPostProductionMediaProcessor> mediaProcessors) {
        return () -> {
            // 延迟到全部单例注册完成后读取可选协作者，避免配置类解析顺序让已启用 worker 静默缺席。
            VideoEpisodePostProductionReconciler reconciler = reconcilers.getIfAvailable();
            VideoPostProductionMediaProcessor media = mediaProcessors.getIfAvailable();
            if (reconciler == null || media == null || !media.readiness().ready()) return;
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
            tasks.start("video_episode_post_production_reconciler", worker);
        };
    }
}
