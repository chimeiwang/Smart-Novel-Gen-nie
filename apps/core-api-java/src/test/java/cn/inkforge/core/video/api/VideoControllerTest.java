package cn.inkforge.core.video.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import cn.inkforge.contracts.api.CreateVideoProjectRequest;
import cn.inkforge.contracts.api.VideoPlanProgressQuery;
import cn.inkforge.contracts.api.VideoPlanProgressResponse;
import cn.inkforge.contracts.api.VideoProjectResponse;
import cn.inkforge.core.generated.api.VideoApi;
import cn.inkforge.core.identity.application.AuthenticatedUser;
import cn.inkforge.core.identity.application.CurrentUserAccess;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.http.InternalServiceAuthenticator;
import cn.inkforge.core.video.application.LegacyVideoPlanService;
import cn.inkforge.core.video.application.ResolvedVideoFile;
import cn.inkforge.core.video.application.VideoAdaptationService;
import cn.inkforge.core.video.application.VideoPostProductionService;
import cn.inkforge.core.video.application.VideoProjectService;
import cn.inkforge.core.video.application.VideoRenderService;
import cn.inkforge.core.video.application.VideoVisualCanonService;
import cn.inkforge.serviceauth.ServiceScope;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Optional;
import java.util.Set;
import java.util.stream.Collectors;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.ResponseEntity;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

class VideoControllerTest {

    private final VideoProjectService projects = mock(VideoProjectService.class);
    private final VideoAdaptationService adaptations = mock(VideoAdaptationService.class);
    private final VideoVisualCanonService canons = mock(VideoVisualCanonService.class);
    private final VideoRenderService renders = mock(VideoRenderService.class);
    private final VideoPostProductionService postProduction =
            mock(VideoPostProductionService.class);
    private final LegacyVideoPlanService legacy = mock(LegacyVideoPlanService.class);
    private final InternalServiceAuthenticator authenticator =
            mock(InternalServiceAuthenticator.class);
    private final CurrentUserAccess users =
            token -> new AuthenticatedUser("user-1", "测试用户");
    private final VideoController controller = new VideoController(
            Optional.of(projects),
            Optional.of(adaptations),
            Optional.of(canons),
            Optional.of(renders),
            Optional.of(postProduction),
            Optional.of(legacy),
            Optional.of(users),
            Optional.of(authenticator));

    @AfterEach
    void clearRequest() {
        RequestContextHolder.resetRequestAttributes();
    }

    @Test
    void 控制器必须显式实现冻结契约中的全部四十八个入口() {
        Set<String> apiMethods = Arrays.stream(VideoApi.class.getDeclaredMethods())
                .filter(method -> ResponseEntity.class.isAssignableFrom(method.getReturnType()))
                .map(method -> method.getName())
                .collect(Collectors.toSet());
        Set<String> implemented = Arrays.stream(VideoController.class.getDeclaredMethods())
                .map(method -> method.getName())
                .collect(Collectors.toSet());

        assertThat(apiMethods).hasSize(48);
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
    void 历史回调路径不一致必须在验签和仓储前拒绝() {
        VideoPlanProgressQuery query = new VideoPlanProgressQuery(
                "job-1", "novel-1", "project-1", "1.0", "task-1", "scene-body", "task-1");

        assertThatThrownBy(() ->
                        controller.getPlanProgressInternalV1VideoScenesSceneIdProgressPost(
                                "scene-path", query))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(403);
                    assertThat(error.code()).isEqualTo("VIDEO_CALLBACK_RESOURCE_MISMATCH");
                });
        verifyNoInteractions(authenticator, legacy);
    }

    @Test
    void 历史进度必须绑定原始正文和VideoWrite权限后读取() {
        bindRequest(
                "POST",
                "/internal/v1/video/scenes/scene-1/progress",
                "{\"protocolVersion\":\"1.0\"}");
        VideoPlanProgressQuery query = new VideoPlanProgressQuery(
                "job-1", "novel-1", "project-1", "1.0", "task-1", "scene-1", "task-1");
        VideoPlanProgressResponse expected = mock(VideoPlanProgressResponse.class);
        when(legacy.progress(query)).thenReturn(expected);

        var response = controller.getPlanProgressInternalV1VideoScenesSceneIdProgressPost(
                "scene-1", query);

        assertThat(response.getBody()).isSameAs(expected);
        verify(authenticator).authenticate(
                any(),
                eq("{\"protocolVersion\":\"1.0\"}".getBytes(StandardCharsets.UTF_8)),
                eq(ServiceScope.VIDEO_WRITE),
                eq("task-1"),
                eq("task-1"),
                eq("novel-1"),
                anyString(),
                anyString());
        verify(legacy).progress(query);
    }

    private static void bindRequest(String method, String path, String body) {
        MockHttpServletRequest request = new MockHttpServletRequest(method, path);
        request.setAttribute(
                "cn.inkforge.core.platform.http.RawRequestBody.bytes",
                body.getBytes(StandardCharsets.UTF_8));
        RequestContextHolder.setRequestAttributes(new ServletRequestAttributes(request));
    }
}
