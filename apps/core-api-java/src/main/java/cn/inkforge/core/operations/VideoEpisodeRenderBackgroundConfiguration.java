package cn.inkforge.core.operations;

import cn.inkforge.core.operations.background.BackgroundTaskManager;
import cn.inkforge.core.operations.background.BackgroundWorker;
import cn.inkforge.core.video.application.VideoEpisodeRenderReconciler;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** Operations 单向托管独立剧集逐镜生成的耐久协调循环。 */
@Configuration(proxyBeanMethods = false)
class VideoEpisodeRenderBackgroundConfiguration {

    @Bean
    SmartInitializingSingleton videoEpisodeRenderReconcilerStarter(
            BackgroundTaskManager tasks,
            ObjectProvider<VideoEpisodeRenderReconciler> reconcilers) {
        return () -> {
            // 普通 Configuration 的类级 ConditionalOnBean 依赖解析顺序；到单例就绪时再取值才能可靠发现视频 Bean。
            VideoEpisodeRenderReconciler reconciler = reconcilers.getIfAvailable();
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
            tasks.start("video_episode_render_reconciler", worker);
        };
    }
}
