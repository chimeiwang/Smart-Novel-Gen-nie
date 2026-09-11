package cn.inkforge.core.video.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import cn.inkforge.core.video.application.StoredVideoAsset;
import cn.inkforge.core.video.application.VideoAssetStore;
import cn.inkforge.core.video.application.VideoMediaProbe;
import cn.inkforge.core.video.application.VideoMediaProbeException;
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;

class SeedanceResultArchiverTest {
    private final VideoAssetStore storage = mock(VideoAssetStore.class);
    private final VideoMediaProbe probe = mock(VideoMediaProbe.class);
    private final HttpClient http = mock(HttpClient.class);
    private final StoredVideoAsset stored = new StoredVideoAsset(
            "project/task.mp4", Path.of("/safe/project/task.mp4"), "video/mp4", 128, "a".repeat(64));

    @Test
    void 下载归档后使用真实视频探测时长() throws Exception {
        prepareDownload();
        when(probe.probeVideoDurationMs(stored.absolutePath())).thenReturn(4_875);
        var result = archiver().archive("project", "task", "https://result.example.volces.com/video.mp4");
        assertThat(result.durationMs()).isEqualTo(4_875);
        verify(probe).probeVideoDurationMs(stored.absolutePath());
    }

    @Test
    void 无有效视频帧时清理文件并拒绝公布成功() throws Exception {
        prepareDownload();
        when(probe.probeVideoDurationMs(stored.absolutePath())).thenThrow(new VideoMediaProbeException("无视频帧"));
        assertThatThrownBy(() -> archiver().archive("project", "task", "https://result.example.volces.com/video.mp4"))
                .isInstanceOf(VideoMediaProbeException.class);
        verify(storage).delete(stored.storageKey());
    }

    @SuppressWarnings("unchecked")
    private void prepareDownload() throws Exception {
        HttpResponse<InputStream> response = mock(HttpResponse.class);
        when(response.statusCode()).thenReturn(200);
        when(response.body()).thenReturn(new ByteArrayInputStream(new byte[] {1}));
        when(http.send(any(HttpRequest.class), org.mockito.ArgumentMatchers.<HttpResponse.BodyHandler<InputStream>>any()))
                .thenReturn(response);
        when(storage.saveStream(eq("project"), eq("task"), eq("video"), any(InputStream.class), anyLong()))
                .thenReturn(stored);
    }

    private SeedanceResultArchiver archiver() {
        return new SeedanceResultArchiver(storage, List.of(".volces.com"), probe, http);
    }
}
