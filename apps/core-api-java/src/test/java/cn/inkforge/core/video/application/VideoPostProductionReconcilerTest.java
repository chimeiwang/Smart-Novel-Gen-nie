package cn.inkforge.core.video.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import cn.inkforge.core.video.application.VideoEpisodeExportManifest.FrozenAsset;
import cn.inkforge.core.video.application.VideoEpisodeExportManifest.FrozenVideoClip;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class VideoPostProductionReconcilerTest {

    private final VideoPostProductionRepository repository =
            mock(VideoPostProductionRepository.class);
    private final VideoPostProductionMediaProcessor media =
            mock(VideoPostProductionMediaProcessor.class);
    private final VideoAssetStore storage = mock(VideoAssetStore.class);

    @Test
    void 成功导出使用确定性素材标识并登记冻结总时长() {
        VideoEpisodeExportManifest manifest = manifest();
        when(repository.claimDueExportTasks(1))
                .thenReturn(List.of(new EpisodeExportClaim("task", "project", manifest)));
        StoredVideoAsset stored = new StoredVideoAsset(
                "project/export_task.mp4",
                Path.of("/safe/project/export_task.mp4"),
                "video/mp4",
                1_024,
                "d".repeat(64));
        when(media.renderEpisode(manifest, storage, "export_task")).thenReturn(stored);

        VideoPostProductionReconciler reconciler = new VideoPostProductionReconciler(
                repository, media, storage, 1, Duration.ofSeconds(3));
        assertThat(reconciler.runOnce()).isEqualTo(1);

        ArgumentCaptor<CompletedEpisodeExport> completed =
                ArgumentCaptor.forClass(CompletedEpisodeExport.class);
        verify(repository).completeExport(completed.capture());
        assertThat(completed.getValue().assetId()).isEqualTo("export_task");
        assertThat(completed.getValue().durationMs()).isEqualTo(4_000);
    }

    @Test
    void 媒体错误只持久化稳定公开消息() {
        VideoEpisodeExportManifest manifest = manifest();
        when(repository.claimDueExportTasks(1))
                .thenReturn(List.of(new EpisodeExportClaim("task", "project", manifest)));
        when(media.renderEpisode(any(), any(), any()))
                .thenThrow(new VideoMediaProcessingException(
                        "VIDEO_EXPORT_ASSET_HASH_MISMATCH",
                        "包含服务器绝对路径的内部详情"));

        new VideoPostProductionReconciler(
                        repository, media, storage, 1, Duration.ofSeconds(3))
                .runOnce();

        verify(repository).failExport(
                "task",
                "VIDEO_EXPORT_ASSET_HASH_MISMATCH",
                "导出引用的素材哈希已经变化");
    }

    private static VideoEpisodeExportManifest manifest() {
        return new VideoEpisodeExportManifest(
                VideoEpisodeExportManifest.SCHEMA_VERSION,
                "adaptation",
                "project",
                "novel",
                "episode-plan",
                "shot-plan",
                1,
                "edit",
                "a".repeat(64),
                "mix",
                "b".repeat(64),
                "16:9",
                "720p",
                24,
                true,
                4_000,
                List.of(new FrozenVideoClip(
                        1,
                        "shot",
                        "take",
                        new FrozenAsset(
                                "video",
                                "project/video.mp4",
                                "c".repeat(64),
                                "video/mp4",
                                5_000),
                        500,
                        4_500,
                        4_000,
                        "cut",
                        0)),
                List.of(),
                List.of());
    }
}
