package cn.inkforge.core.video.infrastructure;

import cn.inkforge.core.video.application.ArchivedVideoRender;
import cn.inkforge.core.video.application.SeedanceResultUrlPolicy;
import cn.inkforge.core.video.application.StoredVideoAsset;
import cn.inkforge.core.video.application.VideoAssetStore;
import cn.inkforge.core.video.application.VideoRenderResultArchiver;
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

    private final VideoAssetStore storage;
    private final List<String> allowedHostSuffixes;
    private final HttpClient http;

    SeedanceResultArchiver(VideoAssetStore storage, List<String> allowedHostSuffixes) {
        this(
                storage,
                allowedHostSuffixes,
                HttpClient.newBuilder()
                        .connectTimeout(Duration.ofSeconds(5))
                        .followRedirects(HttpClient.Redirect.NEVER)
                        .build());
    }

    SeedanceResultArchiver(
            VideoAssetStore storage, List<String> allowedHostSuffixes, HttpClient http) {
        this.storage = Objects.requireNonNull(storage);
        this.allowedHostSuffixes = List.copyOf(allowedHostSuffixes);
        this.http = Objects.requireNonNull(http);
    }

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
                return new ArchivedVideoRender(assetId, stored);
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Seedance 结果归档被中断", exception);
        } catch (IOException exception) {
            throw new UncheckedIOException("Seedance 结果下载失败", exception);
        }
    }
}
