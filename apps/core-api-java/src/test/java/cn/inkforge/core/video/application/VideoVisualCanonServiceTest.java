package cn.inkforge.core.video.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import cn.inkforge.contracts.api.ApproveVisualCanonRequest;
import cn.inkforge.contracts.api.CreateVisualCanonCandidateRequest;
import cn.inkforge.contracts.api.SaveShotVisualReferencesRequest;
import cn.inkforge.contracts.api.ShotVisualReferenceSelectionRequest;
import cn.inkforge.contracts.api.VisualCanonLibraryResponse;
import cn.inkforge.contracts.api.VisualCanonResponse;
import cn.inkforge.core.platform.http.ApiException;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class VideoVisualCanonServiceTest {

    @Test
    void 读操作不受预览门禁而候选与批准写入受控() {
        VideoVisualCanonRepository repository = mock(VideoVisualCanonRepository.class);
        when(repository.list("user-1", "project-1"))
                .thenReturn(new VisualCanonLibraryResponse(List.of()));
        VideoVisualCanonService service = new VideoVisualCanonService(repository, false);
        var request = candidate();

        assertThat(service.list("user-1", "project-1").getCanons()).isEmpty();
        assertCode(
                () -> service.setCandidate("user-1", "project-1", request),
                "VIDEO_PREVIEW_DISABLED");
        assertCode(
                () -> service.approve(
                        "user-1",
                        "canon-1",
                        new ApproveVisualCanonRequest("asset-1", "request-12345678", 1)),
                "VIDEO_PREVIEW_DISABLED");
        verify(repository, never()).setCandidate(
                org.mockito.ArgumentMatchers.any(),
                org.mockito.ArgumentMatchers.any(),
                org.mockito.ArgumentMatchers.any());
    }

    @Test
    void 职责类型与去空白后的特征集合必须在应用边界严格校验() {
        VideoVisualCanonRepository repository = mock(VideoVisualCanonRepository.class);
        VideoVisualCanonService service = new VideoVisualCanonService(repository, true);
        var mismatch = candidate();
        mismatch.setSettingKind(CreateVisualCanonCandidateRequest.SettingKindEnum.LOCATION);
        assertCode(
                () -> service.setCandidate("user-1", "project-1", mismatch),
                "VALIDATION_ERROR");

        var duplicate = candidate();
        duplicate.setIncludeFeatures(List.of(" 正脸 ", "正脸"));
        assertCode(
                () -> service.setCandidate("user-1", "project-1", duplicate),
                "VALIDATION_ERROR");
    }

    @Test
    void 候选命令必须传递清理后的标签特征与默认强度() {
        VideoVisualCanonRepository repository = mock(VideoVisualCanonRepository.class);
        when(repository.setCandidate(
                        org.mockito.ArgumentMatchers.any(),
                        org.mockito.ArgumentMatchers.any(),
                        org.mockito.ArgumentMatchers.any()))
                .thenReturn(new VisualCanonResponse());
        VideoVisualCanonService service = new VideoVisualCanonService(repository, true);
        var request = candidate();
        request.setLabel("  默认形象  ");
        request.setIncludeFeatures(List.of("  正脸  ", "黑发"));
        request.setExcludeFeatures(List.of("  现代服装 "));
        request.setDefaultStrength(85);

        service.setCandidate("user-1", "project-1", request);

        ArgumentCaptor<VisualCanonCandidateCommand> command =
                ArgumentCaptor.forClass(VisualCanonCandidateCommand.class);
        verify(repository).setCandidate(
                org.mockito.ArgumentMatchers.eq("user-1"),
                org.mockito.ArgumentMatchers.eq("project-1"),
                command.capture());
        assertThat(command.getValue().label()).isEqualTo("默认形象");
        assertThat(command.getValue().includeFeatures()).containsExactly("正脸", "黑发");
        assertThat(command.getValue().excludeFeatures()).containsExactly("现代服装");
        assertThat(command.getValue().defaultStrength()).isEqualTo(85);
    }

    @Test
    void 逐镜视觉参考不能重复绑定同一正式版本() {
        VideoVisualCanonRepository repository = mock(VideoVisualCanonRepository.class);
        VideoVisualCanonService service = new VideoVisualCanonService(repository, true);
        SaveShotVisualReferencesRequest request = new SaveShotVisualReferencesRequest(0)
                .references(List.of(
                        new ShotVisualReferenceSelectionRequest("version-1", 70),
                        new ShotVisualReferenceSelectionRequest("version-1", 80)));

        assertCode(
                () -> service.saveShotReferences(
                        "user-1", "adaptation-1", "shot-1", request),
                "VALIDATION_ERROR");
        verify(repository, never()).saveShotReferences(
                org.mockito.ArgumentMatchers.any(),
                org.mockito.ArgumentMatchers.any(),
                org.mockito.ArgumentMatchers.any(),
                org.mockito.ArgumentMatchers.any());
    }

    private static CreateVisualCanonCandidateRequest candidate() {
        return new CreateVisualCanonCandidateRequest(
                "asset-1",
                "request-12345678",
                CreateVisualCanonCandidateRequest.DutyEnum.IDENTITY,
                "默认形象",
                "character-1",
                CreateVisualCanonCandidateRequest.SettingKindEnum.CHARACTER,
                "default");
    }

    private static void assertCode(Runnable action, String code) {
        assertThatThrownBy(action::run)
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo(code));
    }
}
