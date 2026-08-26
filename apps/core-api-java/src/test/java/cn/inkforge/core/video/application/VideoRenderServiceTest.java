package cn.inkforge.core.video.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import cn.inkforge.contracts.api.ConfirmShotTakeRequest;
import cn.inkforge.contracts.api.ShotRenderTaskResponse;
import cn.inkforge.contracts.api.ShotTakeDecisionResponse;
import cn.inkforge.contracts.api.StartShotRenderRequest;
import cn.inkforge.core.platform.http.ApiException;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;

class VideoRenderServiceTest {

    private final VideoRenderRepository repository = mock(VideoRenderRepository.class);
    private final VideoAssetStore storage = mock(VideoAssetStore.class);

    @Test
    void 就绪信息与真实调用门禁互相独立() {
        VideoRenderService service = new VideoRenderService(
                repository, storage, false, false, "seedance-model", null, null);

        assertThat(service.readiness().getBlockers())
                .containsExactly(
                        "Seedance 尚未配置",
                        "Seedance 真实调用尚未启用",
                        "视觉参考图公网短时传输尚未配置；无参考图镜头不受影响");
        assertCode(
                () -> service.createTask(
                        "user", "adaptation", "shot", new StartShotRenderRequest("request", 5, 1)),
                "SEEDANCE_NOT_CONFIGURED");
    }

    @Test
    void 确认冲突携带完整决策且文件必须经过受控存储解析() {
        VideoRenderService service = new VideoRenderService(
                repository, storage, true, true, "seedance-model", null, null);
        ConfirmShotTakeRequest request = new ConfirmShotTakeRequest("request", 1);
        ShotTakeDecisionResponse conflict = new ShotTakeDecisionResponse(
                "command",
                "old-take",
                "VIDEO_TAKE_REVISION_CONFLICT",
                2,
                "shot",
                ShotTakeDecisionResponse.StatusEnum.CONFLICT,
                "new-take");
        when(repository.confirmTake(
                        "user", "adaptation", "shot", "new-take", request))
                .thenReturn(conflict);

        assertThatThrownBy(() -> service.confirmTake(
                        "user", "adaptation", "shot", "new-take", request))
                .isInstanceOfSatisfying(ApiException.class, exception -> {
                    assertThat(exception.statusCode()).isEqualTo(409);
                    assertThat(exception.code()).isEqualTo("VIDEO_TAKE_REVISION_CONFLICT");
                    assertThat(exception.details()).isSameAs(conflict);
                });

        when(repository.getTakeFile("user", "take"))
                .thenReturn(new VideoAssetFile("project/take.mp4", "video/mp4", "S01 · Take 1"));
        when(storage.resolve("project/take.mp4")).thenReturn(Path.of("/safe/take.mp4"));
        assertThat(service.getTakeFile("user", "take"))
                .isEqualTo(new ResolvedVideoAsset(
                        Path.of("/safe/take.mp4"), "video/mp4", "S01 · Take 1"));
    }

    @Test
    void 创建任务冻结服务端模型与参考图传输能力() {
        VideoRenderService service = new VideoRenderService(
                repository, storage, true, true, "seedance-model", null, null);
        StartShotRenderRequest request = new StartShotRenderRequest("request", 5, 1);
        ShotRenderTaskResponse expected = mock(ShotRenderTaskResponse.class);
        when(repository.createTask(
                        "user", "adaptation", "shot", request, "seedance-model", false))
                .thenReturn(expected);

        assertThat(service.createTask("user", "adaptation", "shot", request))
                .isSameAs(expected);
        verify(repository).createTask(
                "user", "adaptation", "shot", request, "seedance-model", false);
    }

    private static void assertCode(Runnable action, String code) {
        assertThatThrownBy(action::run)
                .isInstanceOfSatisfying(ApiException.class, exception ->
                        assertThat(exception.code()).isEqualTo(code));
    }
}
