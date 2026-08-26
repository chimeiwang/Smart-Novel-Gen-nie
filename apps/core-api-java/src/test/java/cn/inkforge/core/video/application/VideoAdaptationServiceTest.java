package cn.inkforge.core.video.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import cn.inkforge.contracts.api.CreateChapterAdaptationRequest;
import cn.inkforge.core.platform.http.ApiException;
import java.time.OffsetDateTime;
import java.util.List;
import org.junit.jupiter.api.Test;

class VideoAdaptationServiceTest {

    private static final OffsetDateTime NOW =
            OffsetDateTime.parse("2026-08-25T05:00:00.123Z");

    @Test
    void 创建受开发门禁控制而列表和历史读取不受影响() {
        VideoAdaptationRepository repository = mock(VideoAdaptationRepository.class);
        VideoAdaptationDecisionStore decisions = mock(VideoAdaptationDecisionStore.class);
        VideoAdaptationTaskStore tasks = mock(VideoAdaptationTaskStore.class);
        var request = new CreateChapterAdaptationRequest("chapter-1", "request-12345678", NOW);
        when(repository.getDetail("user-1", "adaptation-1"))
                .thenReturn(VideoAdaptationService.emptyResponse(snapshot()));
        when(repository.listDetails("user-1", "project-1"))
                .thenReturn(new cn.inkforge.contracts.api.ChapterAdaptationListResponse(
                        List.of(VideoAdaptationService.emptyResponse(snapshot()))));
        VideoAdaptationService service =
                new VideoAdaptationService(repository, decisions, tasks, false);

        assertThatThrownBy(() -> service.create("user-1", "project-1", request))
                .isInstanceOfSatisfying(ApiException.class, exception -> {
                    assertThat(exception.statusCode()).isEqualTo(503);
                    assertThat(exception.code()).isEqualTo("VIDEO_PREVIEW_DISABLED");
                });
        verify(repository, never()).create("user-1", "project-1", request);
        assertThat(service.get("user-1", "adaptation-1").getSourceText()).isEqualTo("完整章节");
        assertThat(service.list("user-1", "project-1").getAdaptations()).hasSize(1);
    }

    @Test
    void 空改编必须显式返回空状态和全部非空集合() {
        VideoAdaptationRepository repository = mock(VideoAdaptationRepository.class);
        VideoAdaptationDecisionStore decisions = mock(VideoAdaptationDecisionStore.class);
        VideoAdaptationTaskStore tasks = mock(VideoAdaptationTaskStore.class);
        var request = new CreateChapterAdaptationRequest("chapter-1", "request-12345678", NOW);
        when(repository.create("user-1", "project-1", request)).thenReturn(snapshot());
        when(repository.getDetail("user-1", "adaptation-1"))
                .thenReturn(VideoAdaptationService.emptyResponse(snapshot()));
        VideoAdaptationService service =
                new VideoAdaptationService(repository, decisions, tasks, true);

        var response = service.create("user-1", "project-1", request);

        assertThat(response.getState().getValue()).isEqualTo("empty");
        assertThat(response.getHeadRevision()).isOne();
        assertThat(response.getCurrentPlan()).isNull();
        assertThat(response.getPromptVersions()).isEmpty();
        assertThat(response.getPromptCandidates()).isEmpty();
        assertThat(response.getVisualReferenceSets()).isEmpty();
    }

    private static VideoAdaptationSnapshot snapshot() {
        return new VideoAdaptationSnapshot(
                "adaptation-1",
                "project-1",
                "novel-1",
                "chapter-1",
                "第一章",
                NOW,
                "完整章节",
                "a".repeat(64),
                "active",
                1,
                NOW);
    }
}
