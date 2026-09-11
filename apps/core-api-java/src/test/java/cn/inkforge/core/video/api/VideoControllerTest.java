package cn.inkforge.core.video.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import cn.inkforge.contracts.api.CreateVideoProjectRequest;
import cn.inkforge.contracts.api.VideoProjectResponse;
import cn.inkforge.contracts.api.VisualCanonLibraryResponse;
import cn.inkforge.core.generated.api.VideoApi;
import cn.inkforge.core.identity.application.AuthenticatedUser;
import cn.inkforge.core.identity.application.CurrentUserAccess;
import cn.inkforge.core.video.application.ResolvedVideoAsset;
import cn.inkforge.core.video.application.ResolvedVideoFile;
import cn.inkforge.core.video.application.VideoEpisodeRenderService;
import cn.inkforge.core.video.application.VideoProjectService;
import cn.inkforge.core.video.application.VideoVisualCanonService;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Optional;
import java.util.Set;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;
import org.springframework.http.ResponseEntity;

class VideoControllerTest {

    private final VideoProjectService projects = mock(VideoProjectService.class);
    private final VideoVisualCanonService canons = mock(VideoVisualCanonService.class);
    private final VideoEpisodeRenderService renders = mock(VideoEpisodeRenderService.class);
    private final CurrentUserAccess users =
            token -> new AuthenticatedUser("user-1", "测试用户");
    private final VideoController controller = new VideoController(
            Optional.of(projects),
            Optional.of(canons),
            Optional.of(renders),
            Optional.of(users));

    @Test
    void 控制器只实现共享视频契约中的十一个入口() {
        Set<String> apiMethods = Arrays.stream(VideoApi.class.getDeclaredMethods())
                .filter(method -> ResponseEntity.class.isAssignableFrom(method.getReturnType()))
                .map(method -> method.getName())
                .collect(Collectors.toSet());
        Set<String> implemented = Arrays.stream(VideoController.class.getDeclaredMethods())
                .map(method -> method.getName())
                .collect(Collectors.toSet());

        assertThat(apiMethods).hasSize(11);
        assertThat(implemented).containsAll(apiMethods);
    }

    @Test
    void 浏览器项目创建只能使用Cookie当前用户并返回201() {
        CreateVideoProjectRequest request = mock(CreateVideoProjectRequest.class);
        VideoProjectResponse expected = mock(VideoProjectResponse.class);
        when(projects.createProject("user-1", "novel-1", request)).thenReturn(expected);

        var response = controller.createProjectApiV1VideoNovelsNovelIdProjectsPost(
                "novel-1", request, "session-token");

        assertThat(response.getStatusCode().value()).isEqualTo(201);
        assertThat(response.getBody()).isSameAs(expected);
    }

    @Test
    void 视觉设定读取继续使用当前用户() {
        VisualCanonLibraryResponse expected = mock(VisualCanonLibraryResponse.class);
        when(canons.list("user-1", "project-1")).thenReturn(expected);

        var response = controller.listVisualCanonsApiV1VideoProjectsProjectIdVisualCanonsGet(
                "project-1", "session-token");

        assertThat(response.getBody()).isSameAs(expected);
    }

    @Test
    void 文件下载必须流式返回完整字节和UTF8文件名() throws Exception {
        Path file = Files.createTempFile("inkforge-video-controller-", ".bin");
        byte[] content = "完整视频字节😀".repeat(1_000).getBytes(StandardCharsets.UTF_8);
        Files.write(file, content);
        try {
            when(projects.getAssetFile("user-1", "asset-1"))
                    .thenReturn(new ResolvedVideoFile(file, "application/octet-stream", "镜头😀.bin"));

            var response = controller.downloadAssetApiV1VideoAssetsAssetIdContentGet(
                    "asset-1", "session-token");
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            response.getBody().writeTo(output);

            assertThat(output.toByteArray()).isEqualTo(content);
            assertThat(response.getHeaders().getContentLength()).isEqualTo(content.length);
            assertThat(response.getHeaders().getFirst("Content-Disposition"))
                    .contains("attachment")
                    .contains("UTF-8");
        } finally {
            Files.deleteIfExists(file);
        }
    }

    @Test
    void 供应商素材读取使用新EpisodeRender边界且不要求浏览器Cookie() throws Exception {
        Path file = Files.createTempFile("inkforge-provider-asset-", ".png");
        byte[] content = "受控参考图".getBytes(StandardCharsets.UTF_8);
        Files.write(file, content);
        try {
            when(renders.getProviderAssetFile("signed-grant"))
                    .thenReturn(new ResolvedVideoAsset(file, "image/png", "参考图.png"));

            var response = controller.getProviderAssetApiV1VideoProviderAssetsTokenGet(
                    "signed-grant");
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            response.getBody().writeTo(output);

            assertThat(output.toByteArray()).isEqualTo(content);
            assertThat(response.getHeaders().getContentType().toString()).isEqualTo("image/png");
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
