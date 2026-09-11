package cn.inkforge.core.video.infrastructure;

import cn.inkforge.core.video.application.ArchivedVideoRender;
import cn.inkforge.core.video.application.ArchivedVideoFrame;
import cn.inkforge.core.video.application.SeedanceResultUrlPolicy;
import cn.inkforge.core.video.application.StoredVideoAsset;
import cn.inkforge.core.video.application.VideoAssetStore;
import cn.inkforge.core.video.application.VideoRenderResultArchiver;
import cn.inkforge.core.video.application.VideoMediaProbe;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;
import java.util.Objects;

/** 把供应商临时 URL 无重定向、限流地归档到 InkForge 受控媒体存储。 */
final class SeedanceResultArchiver implements VideoRenderResultArchiver {

    private static final long MAXIMUM_VIDEO_BYTES = 200L * 1024 * 1024;
    private static final long MAXIMUM_IMAGE_BYTES = 30L * 1024 * 1024;

    private final VideoAssetStore storage;
    private final List<String> allowedHostSuffixes;
    private final HttpClient http;
    private final VideoMediaProbe mediaProbe;

    SeedanceResultArchiver(
            VideoAssetStore storage, List<String> allowedHostSuffixes, VideoMediaProbe mediaProbe) {
        this(
                storage,
                allowedHostSuffixes,
                mediaProbe,
                HttpClient.newBuilder()
                        .connectTimeout(Duration.ofSeconds(5))
                        .followRedirects(HttpClient.Redirect.NEVER)
                        .build());
    }

    SeedanceResultArchiver(
            VideoAssetStore storage,
            List<String> allowedHostSuffixes,
            VideoMediaProbe mediaProbe,
            HttpClient http) {
        this.storage = Objects.requireNonNull(storage);
        this.allowedHostSuffixes = List.copyOf(allowedHostSuffixes);
        this.http = Objects.requireNonNull(http);
        this.mediaProbe = Objects.requireNonNull(mediaProbe);
    }

    /** 校验结果 URL 后限量下载，探测成功才保留为受控素材。 */
    @Override
    public ArchivedVideoRender archive(
            String projectId, String assetId, String videoUrl) {
        URI safeUrl = SeedanceResultUrlPolicy.requireAllowed(videoUrl, allowedHostSuffixes);
        HttpRequest request = HttpRequest.newBuilder(safeUrl)
                .timeout(Duration.ofSeconds(120))
                .GET()
                .build();
        try {
            HttpResponse<InputStream> response =
                    http.send(request, HttpResponse.BodyHandlers.ofInputStream());
            try (InputStream body = response.body()) {
                int status = response.statusCode();
                if (status >= 300 && status < 400) {
                    throw new IllegalStateException("SEEDANCE_RESULT_REDIRECT_FORBIDDEN");
                }
                if (status < 200 || status >= 300) {
                    throw new IllegalStateException("SEEDANCE_RESULT_HTTP_" + status);
                }
                StoredVideoAsset stored = storage.saveStream(
                        projectId, assetId, "video", body, MAXIMUM_VIDEO_BYTES);
                try {
                    int durationMs = mediaProbe.probeVideoDurationMs(stored.absolutePath());
                    return new ArchivedVideoRender(assetId, stored, durationMs);
                } catch (RuntimeException exception) {
                    // 无有效画面或时长的文件不能留在素材区，删除失败由存储层异常继续上抛。
                    storage.delete(stored.storageKey());
                    throw exception;
                }
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Seedance 结果归档被中断", exception);
        } catch (IOException exception) {
            throw new UncheckedIOException("Seedance 结果下载失败", exception);
        }
    }

    /** 尾帧 URL 同样是短期供应商结果；立即归档为受控图片，不持久化临时地址。 */
    @Override
    public ArchivedVideoFrame archiveImage(
            String projectId, String assetId, String imageUrl) {
        URI safeUrl = SeedanceResultUrlPolicy.requireAllowed(imageUrl, allowedHostSuffixes);
        HttpRequest request = HttpRequest.newBuilder(safeUrl)
                .timeout(Duration.ofSeconds(120))
                .GET()
                .build();
        try {
            HttpResponse<InputStream> response =
                    http.send(request, HttpResponse.BodyHandlers.ofInputStream());
            try (InputStream body = response.body()) {
                int status = response.statusCode();
                if (status >= 300 && status < 400) {
                    throw new IllegalStateException("SEEDANCE_RESULT_REDIRECT_FORBIDDEN");
                }
                if (status < 200 || status >= 300) {
                    throw new IllegalStateException("SEEDANCE_RESULT_HTTP_" + status);
                }
                StoredVideoAsset stored = storage.saveStream(
                        projectId, assetId, "image", body, MAXIMUM_IMAGE_BYTES);
                return new ArchivedVideoFrame(assetId, stored);
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Seedance 尾帧归档被中断", exception);
        } catch (IOException exception) {
            throw new UncheckedIOException("Seedance 尾帧下载失败", exception);
        }
    }
}
