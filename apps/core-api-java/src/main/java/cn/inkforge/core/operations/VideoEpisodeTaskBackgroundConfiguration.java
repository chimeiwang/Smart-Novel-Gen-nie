package cn.inkforge.core.operations;

import cn.inkforge.core.operations.background.BackgroundTaskManager;
import cn.inkforge.core.operations.background.BackgroundWorker;
import cn.inkforge.core.video.application.VideoEpisodeTaskLifecycle;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** Operations 托管 Episode 普通队列投递，关闭视频时不投递任何任务。 */
@Configuration(proxyBeanMethods=false)
class VideoEpisodeTaskBackgroundConfiguration {
    @Bean
    SmartInitializingSingleton videoEpisodeTaskStarter(BackgroundTaskManager tasks,
            ObjectProvider<VideoEpisodeTaskLifecycle> coordinators) {
        return () -> {
            var coordinator=coordinators.getIfAvailable(); if(coordinator==null) return;
            tasks.start("video_episode_tasks",new BackgroundWorker() {
                public void run() throws Exception {coordinator.run();}
                public void requestStop(){coordinator.requestStop();}
            });
        };
    }
}
