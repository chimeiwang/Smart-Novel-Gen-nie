package cn.inkforge.core.video.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import cn.inkforge.contracts.api.ExtractTakeFrameRequest;
import cn.inkforge.contracts.api.PostProductionAssetResponse;
import cn.inkforge.core.platform.http.ApiException;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class VideoPostProductionServiceTest {

    private final VideoPostProductionRepository repository =
            mock(VideoPostProductionRepository.class);
    private final VideoAssetStore storage = mock(VideoAssetStore.class);
    private final VideoPostProductionMediaProcessor media =
            mock(VideoPostProductionMediaProcessor.class);

    @Test
    void 缺少媒体工具只阻止抽帧和导出() {
        when(media.readiness()).thenReturn(new MediaToolReadiness(false, false));
        VideoPostProductionService service = service();

        assertThat(service.readiness().getBlockers())
                .containsExactly(
                        "当前环境缺少 ffmpeg，不能抽帧或导出",
                        "当前环境缺少 ffprobe，不能检查 Take 音轨");
        assertThatThrownBy(() -> service.extractTakeFrame(
                        "user",
                        "take",
                        new ExtractTakeFrameRequest(
                                "frame-service-request-01", "中间帧", 1_000)))
                .isInstanceOfSatisfying(ApiException.class, exception -> {
                    assertThat(exception.statusCode()).isEqualTo(503);
                    assertThat(exception.code()).isEqualTo("VIDEO_MEDIA_TOOLS_UNAVAILABLE");
                });
    }

    @Test
    void 抽帧使用确定性素材标识并原子登记来源事实() {
        when(media.readiness()).thenReturn(new MediaToolReadiness(true, true));
        String requestId = "frame-service-request-01";
        String sourceKey = "project/take.mp4";
        TakeFrameSource source = new TakeFrameSource(
                "take",
                "shot",
                "adaptation",
                "project",
                "novel",
                sourceKey,
                "a".repeat(64),
                5_000);
        when(repository.getExtractionReplay(any(), any(), any())).thenReturn(null);
        when(repository.getTakeFrameSource("user", "take", 1_000)).thenReturn(source);
        when(storage.resolve(sourceKey)).thenReturn(Path.of("/safe/project/take.mp4"));
        StoredVideoAsset stored = new StoredVideoAsset(
                "project/frame.png",
                Path.of("/safe/project/frame.png"),
                "image/png",
                512,
                "b".repeat(64));
        when(media.extractFrame(
                        Path.of("/safe/project/take.mp4"),
                        "a".repeat(64),
                        1_000,
                        storage,
                        "project",
                        "frame_1961cd6c4440a3e4d2f4b3b37093143f8e2c7fe7"))
                .thenReturn(stored);
        PostProductionAssetResponse expected = mock(PostProductionAssetResponse.class);
        when(repository.completeExtractedFrame(any())).thenReturn(expected);

        VideoPostProductionService service = service();
        assertThat(service.extractTakeFrame(
                        "user",
                        "take",
                        new ExtractTakeFrameRequest(requestId, "  中间帧  ", 1_000)))
                .isSameAs(expected);

        ArgumentCaptor<CompletedTakeFrameExtraction> completed =
                ArgumentCaptor.forClass(CompletedTakeFrameExtraction.class);
        verify(repository).completeExtractedFrame(completed.capture());
        assertThat(completed.getValue().assetId())
                .isEqualTo("frame_1961cd6c4440a3e4d2f4b3b37093143f8e2c7fe7");
        assertThat(completed.getValue().name()).isEqualTo("中间帧");
        assertThat(completed.getValue().requestHash()).hasSize(64);
    }

    private VideoPostProductionService service() {
        return new VideoPostProductionService(repository, storage, media);
    }
}
