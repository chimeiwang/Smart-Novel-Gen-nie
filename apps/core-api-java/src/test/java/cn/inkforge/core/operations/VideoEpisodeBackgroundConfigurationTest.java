package cn.inkforge.core.operations;

import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import cn.inkforge.core.operations.background.BackgroundTaskManager;
import cn.inkforge.core.operations.background.BackgroundWorker;
import cn.inkforge.core.video.application.MediaToolReadiness;
import cn.inkforge.core.video.application.VideoEpisodePostProductionReconciler;
import cn.inkforge.core.video.application.VideoEpisodeRenderReconciler;
import cn.inkforge.core.video.application.VideoPostProductionMediaProcessor;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.ObjectProvider;

class VideoEpisodeBackgroundConfigurationTest {

    @Test
    @SuppressWarnings("unchecked")
    void 全部单例就绪后注册逐镜协调器() throws Exception {
        BackgroundTaskManager tasks = mock(BackgroundTaskManager.class);
        VideoEpisodeRenderReconciler reconciler = mock(VideoEpisodeRenderReconciler.class);
        ObjectProvider<VideoEpisodeRenderReconciler> provider = mock(ObjectProvider.class);
        when(provider.getIfAvailable()).thenReturn(reconciler);

        new VideoEpisodeRenderBackgroundConfiguration()
                .videoEpisodeRenderReconcilerStarter(tasks, provider)
                .afterSingletonsInstantiated();

        ArgumentCaptor<BackgroundWorker> worker = ArgumentCaptor.forClass(BackgroundWorker.class);
        verify(tasks).start(eq("video_episode_render_reconciler"), worker.capture());
        worker.getValue().run();
        verify(reconciler).run();
        worker.getValue().requestStop();
        verify(reconciler).requestStop();
    }

    @Test
    @SuppressWarnings("unchecked")
    void 逐镜协调器缺席时不启动后台任务() {
        BackgroundTaskManager tasks = mock(BackgroundTaskManager.class);
        ObjectProvider<VideoEpisodeRenderReconciler> provider = mock(ObjectProvider.class);
        when(provider.getIfAvailable()).thenReturn(null);

        new VideoEpisodeRenderBackgroundConfiguration()
                .videoEpisodeRenderReconcilerStarter(tasks, provider)
                .afterSingletonsInstantiated();

        verify(tasks, never()).start(eq("video_episode_render_reconciler"), org.mockito.ArgumentMatchers.any());
    }

    @Test
    @SuppressWarnings("unchecked")
    void 媒体工具就绪后注册整集导出协调器() throws Exception {
        BackgroundTaskManager tasks = mock(BackgroundTaskManager.class);
        VideoEpisodePostProductionReconciler reconciler = mock(VideoEpisodePostProductionReconciler.class);
        VideoPostProductionMediaProcessor media = mock(VideoPostProductionMediaProcessor.class);
        ObjectProvider<VideoEpisodePostProductionReconciler> reconcilers = mock(ObjectProvider.class);
        ObjectProvider<VideoPostProductionMediaProcessor> mediaProcessors = mock(ObjectProvider.class);
        when(reconcilers.getIfAvailable()).thenReturn(reconciler);
        when(mediaProcessors.getIfAvailable()).thenReturn(media);
        when(media.readiness()).thenReturn(new MediaToolReadiness(true, true));

        new VideoEpisodePostProductionBackgroundConfiguration()
                .videoEpisodePostProductionReconcilerStarter(tasks, reconcilers, mediaProcessors)
                .afterSingletonsInstantiated();

        ArgumentCaptor<BackgroundWorker> worker = ArgumentCaptor.forClass(BackgroundWorker.class);
        verify(tasks).start(eq("video_episode_post_production_reconciler"), worker.capture());
        worker.getValue().run();
        verify(reconciler).run();
        worker.getValue().requestStop();
        verify(reconciler).requestStop();
    }

    @Test
    @SuppressWarnings("unchecked")
    void 媒体工具未就绪时不启动整集导出任务() {
        BackgroundTaskManager tasks = mock(BackgroundTaskManager.class);
        VideoEpisodePostProductionReconciler reconciler = mock(VideoEpisodePostProductionReconciler.class);
        VideoPostProductionMediaProcessor media = mock(VideoPostProductionMediaProcessor.class);
        ObjectProvider<VideoEpisodePostProductionReconciler> reconcilers = mock(ObjectProvider.class);
        ObjectProvider<VideoPostProductionMediaProcessor> mediaProcessors = mock(ObjectProvider.class);
        when(reconcilers.getIfAvailable()).thenReturn(reconciler);
        when(mediaProcessors.getIfAvailable()).thenReturn(media);
        when(media.readiness()).thenReturn(new MediaToolReadiness(true, false));

        new VideoEpisodePostProductionBackgroundConfiguration()
                .videoEpisodePostProductionReconcilerStarter(tasks, reconcilers, mediaProcessors)
                .afterSingletonsInstantiated();

        verify(tasks, never()).start(eq("video_episode_post_production_reconciler"), org.mockito.ArgumentMatchers.any());
    }
}
