package cn.inkforge.core.video.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import cn.inkforge.contracts.api.ConfirmVideoAssetRequest;
import cn.inkforge.contracts.api.CreateVideoProjectRequest;
import cn.inkforge.core.platform.http.ApiException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.OffsetDateTime;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.mock.web.MockMultipartFile;

class VideoProjectServiceTest {

    private static final OffsetDateTime NOW =
            OffsetDateTime.parse("2026-08-25T05:00:00.123Z");

    @TempDir
    private Path temporaryDirectory;

    @Test
    void 写入受预览门禁控制而历史读取始终返回真实能力状态() {
        VideoProjectRepository repository = mock(VideoProjectRepository.class);
        when(repository.listProjects("user-1", "novel-1")).thenReturn(List.of(project()));
        when(repository.getProject("user-1", "project-1"))
                .thenReturn(new VideoProjectAggregate(project(), List.of(asset())));
        VideoProjectService service = service(repository, mock(VideoAssetStore.class), probe(), false);

        assertCode(
                () -> service.createProject(
                        "user-1", "novel-1", new CreateVideoProjectRequest("项目")),
                503,
                "VIDEO_PREVIEW_DISABLED");
        assertThat(service.listProjects("user-1", "novel-1").getPreviewEnabled()).isFalse();
        assertThat(service.listProjects("user-1", "novel-1").getSeedanceConfigured()).isTrue();
        assertThat(service.getProject("user-1", "project-1").getAssets()).hasSize(1);
        verify(repository, never()).createProject(any(), any(), any());
    }

    @Test
    void 创建项目必须清理输入并保持Seedance项目默认事实() {
        VideoProjectRepository repository = mock(VideoProjectRepository.class);
        when(repository.createProject(
                        eq("user-1"),
                        eq("novel-1"),
                        eq(new VideoProjectCreation("章节影视化", "series", "9:16", "zh-CN"))))
                .thenReturn(project());
        VideoProjectService service = service(repository, mock(VideoAssetStore.class), probe(), true);
        CreateVideoProjectRequest request = new CreateVideoProjectRequest("  章节影视化  ")
                .mode(CreateVideoProjectRequest.ModeEnum.SERIES)
                .targetAspectRatio(CreateVideoProjectRequest.TargetAspectRatioEnum._9_16)
                .targetLanguage(" zh-CN ");

        var response = service.createProject("user-1", "novel-1", request);

        assertThat(response.getProvider()).isEqualTo("seedance_2_5");
        assertThat(response.getMode()).isEqualTo("series");
    }

    @Test
    void 上传必须先校验职责矩阵且数据库失败时回收完整文件() {
        VideoProjectRepository repository = mock(VideoProjectRepository.class);
        VideoAssetStore storage = mock(VideoAssetStore.class);
        MockMultipartFile upload = new MockMultipartFile("file", "人物.png", "image/png", new byte[] {1});
        StoredVideoAsset stored = stored(temporaryDirectory.resolve("asset.png"));
        when(storage.save("project-1", "asset-1", "image", upload)).thenReturn(stored);
        when(repository.createAsset(eq("user-1"), eq("project-1"), any()))
                .thenThrow(new IllegalStateException("数据库失败"));
        VideoProjectService service = service(repository, storage, probe(), true);

        assertCode(
                () -> service.uploadAsset(
                        "user-1", "project-1", upload, "镜头", "image", "camera", null),
                422,
                "VIDEO_ASSET_DUTY_MODALITY_INVALID");
        verify(repository, never()).requireWritableProject("user-1", "project-1");

        assertThatThrownBy(() -> service.uploadAsset(
                        "user-1", "project-1", upload, "  人物参考  ", "image", "identity", null))
                .isInstanceOf(IllegalStateException.class);
        verify(repository).requireWritableProject("user-1", "project-1");
        verify(storage).delete(stored.storageKey());
    }

    @Test
    void 音视频缺少或无法通过ffprobe时必须回收文件且不登记伪时长() {
        VideoProjectRepository repository = mock(VideoProjectRepository.class);
        VideoAssetStore storage = mock(VideoAssetStore.class);
        MockMultipartFile upload = new MockMultipartFile("file", "声音.mp3", "audio/mpeg", new byte[] {1});
        StoredVideoAsset stored = stored(temporaryDirectory.resolve("asset.mp3"));
        when(storage.save("project-1", "asset-1", "audio", upload)).thenReturn(stored);

        VideoMediaProbe unavailable = mock(VideoMediaProbe.class);
        VideoProjectService missing = service(repository, storage, unavailable, true);
        assertCode(
                () -> missing.uploadAsset(
                        "user-1", "project-1", upload, "声音", "audio", "voice", null),
                503,
                "VIDEO_MEDIA_PROBE_UNAVAILABLE");
        verify(storage).delete(stored.storageKey());

        VideoMediaProbe invalidProbe = mock(VideoMediaProbe.class);
        when(invalidProbe.available()).thenReturn(true);
        when(invalidProbe.probeDurationMs(stored.absolutePath()))
                .thenThrow(new VideoMediaProbeException("坏容器"));
        VideoProjectService invalid = service(repository, storage, invalidProbe, true);
        assertCode(
                () -> invalid.uploadAsset(
                        "user-1", "project-1", upload, "声音", "audio", "voice", null),
                422,
                "VIDEO_ASSET_DURATION_INVALID");
        verify(repository, never()).createAsset(any(), any(), any());
    }

    @Test
    void 有效音视频必须登记真实时长来源和清理后的名称() {
        VideoProjectRepository repository = mock(VideoProjectRepository.class);
        VideoAssetStore storage = mock(VideoAssetStore.class);
        VideoMediaProbe probe = mock(VideoMediaProbe.class);
        MockMultipartFile upload = new MockMultipartFile("file", "原名.mp4", "video/mp4", new byte[] {1});
        StoredVideoAsset stored = stored(temporaryDirectory.resolve("asset.mp4"));
        when(storage.save("project-1", "asset-1", "video", upload)).thenReturn(stored);
        when(probe.available()).thenReturn(true);
        when(probe.probeDurationMs(stored.absolutePath())).thenReturn(5_432);
        when(repository.createAsset(eq("user-1"), eq("project-1"), any()))
                .thenReturn(asset());
        VideoProjectService service = service(repository, storage, probe, true);

        service.uploadAsset(
                "user-1", "project-1", upload, "   ", "video", "motion", "authorized_real");

        var creation = org.mockito.ArgumentCaptor.forClass(VideoAssetCreation.class);
        verify(repository).createAsset(eq("user-1"), eq("project-1"), creation.capture());
        assertThat(creation.getValue().name()).isEqualTo("原名.mp4");
        assertThat(creation.getValue().durationMs()).isEqualTo(5_432);
        assertThat(creation.getValue().sourceKind()).isEqualTo("authorized_real");
        verify(storage, never()).delete(stored.storageKey());
    }

    @Test
    void 权利确认委托仓储原子锁定而下载必须同时通过归属和文件存在校验() throws Exception {
        VideoProjectRepository repository = mock(VideoProjectRepository.class);
        VideoAssetStore storage = mock(VideoAssetStore.class);
        when(repository.confirmAsset("user-1", "asset-1", "confirmed")).thenReturn(asset());
        Path path = temporaryDirectory.resolve("asset.png");
        Files.write(path, new byte[] {1});
        when(repository.getAssetFile("user-1", "asset-1"))
                .thenReturn(new VideoAssetFile("project-1/asset-1.png", "image/png", "人物.png"));
        when(storage.resolve("project-1/asset-1.png")).thenReturn(path);
        VideoProjectService service = service(repository, storage, probe(), true);

        service.confirmAsset(
                "user-1",
                "asset-1",
                new ConfirmVideoAssetRequest(ConfirmVideoAssetRequest.RightsStatusEnum.CONFIRMED));
        ResolvedVideoFile file = service.getAssetFile("user-1", "asset-1");

        assertThat(file.path()).isEqualTo(path);
        assertThat(file.mimeType()).isEqualTo("image/png");
        verify(repository).confirmAsset("user-1", "asset-1", "confirmed");

        Files.delete(path);
        assertCode(
                () -> service.getAssetFile("user-1", "asset-1"),
                404,
                "VIDEO_ASSET_FILE_NOT_FOUND");
    }

    private VideoProjectService service(
            VideoProjectRepository repository,
            VideoAssetStore storage,
            VideoMediaProbe probe,
            boolean previewEnabled) {
        return new VideoProjectService(
                repository, storage, probe, () -> "asset-1", previewEnabled, true, false);
    }

    private static VideoMediaProbe probe() {
        VideoMediaProbe probe = mock(VideoMediaProbe.class);
        when(probe.available()).thenReturn(true);
        return probe;
    }

    private static StoredVideoAsset stored(Path path) {
        return new StoredVideoAsset(
                "project-1/asset-1" + extension(path),
                path,
                path.toString().endsWith("mp3") ? "audio/mpeg" : "image/png",
                123,
                "a".repeat(64));
    }

    private static String extension(Path path) {
        String filename = path.getFileName().toString();
        return filename.substring(filename.lastIndexOf('.'));
    }

    private static VideoProjectSnapshot project() {
        return new VideoProjectSnapshot(
                "project-1",
                "novel-1",
                "章节影视化",
                "series",
                "draft",
                "9:16",
                "zh-CN",
                "seedance_2_5",
                1,
                NOW,
                NOW);
    }

    private static VideoAssetSnapshot asset() {
        return new VideoAssetSnapshot(
                "asset-1",
                "project-1",
                "人物",
                "image",
                "identity",
                "image/png",
                123,
                null,
                "a".repeat(64),
                "user_upload",
                "unconfirmed",
                null,
                NOW,
                NOW);
    }

    private static void assertCode(Runnable action, int status, String code) {
        assertThatThrownBy(action::run)
                .isInstanceOfSatisfying(ApiException.class, exception -> {
                    assertThat(exception.statusCode()).isEqualTo(status);
                    assertThat(exception.code()).isEqualTo(code);
                });
    }
}
