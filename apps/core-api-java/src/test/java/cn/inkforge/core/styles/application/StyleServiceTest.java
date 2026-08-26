package cn.inkforge.core.styles.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import cn.inkforge.contracts.api.ApplyStyleRequest;
import cn.inkforge.contracts.api.CreateStyleRequest;
import cn.inkforge.contracts.api.FullPortraitSuccessRequest;
import cn.inkforge.contracts.api.PortraitProcessingRequest;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.styles.domain.ApplyStyleResult;
import cn.inkforge.core.styles.domain.PortraitDispatchStatus;
import cn.inkforge.core.styles.domain.PortraitSection;
import cn.inkforge.core.styles.domain.PortraitSource;
import cn.inkforge.core.styles.domain.PortraitTaskSnapshot;
import cn.inkforge.core.styles.domain.StyleSnapshot;
import java.time.OffsetDateTime;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.openapitools.jackson.nullable.JsonNullable;
import org.springframework.mock.web.MockMultipartFile;

class StyleServiceTest {

    private static final OffsetDateTime NOW =
            OffsetDateTime.parse("2026-08-25T05:00:00.123Z");

    @Test
    void 创建清理名称且上传数据库失败必须回收已经写成的文件() {
        StyleRepository repository = mock(StyleRepository.class);
        StyleFileStorage storage = mock(StyleFileStorage.class);
        StyleSnapshot style = style();
        when(repository.create("user-1", "新文风")).thenReturn(style);
        when(repository.reserveReference("user-1", "style-1")).thenReturn("ref-1");
        StoredStyleFile stored = new StoredStyleFile(
                "作品.txt", java.nio.file.Path.of("/tmp/ref"),
                "/app/uploads/styles/style-1/ref-1_作品.txt", 2);
        when(storage.save(anyString(), anyString(), any())).thenReturn(stored);
        when(repository.createReference("user-1", "style-1", "ref-1", stored))
                .thenThrow(new IllegalStateException("数据库失败"));
        StyleService service = new StyleService(repository, storage, null);

        assertThat(service.create("user-1", new CreateStyleRequest("  新文风  ")).getName())
                .isEqualTo("新文风");
        assertThatThrownBy(() -> service.uploadReference(
                        "user-1",
                        "style-1",
                        new MockMultipartFile("file", "作品.txt", "text/plain", "正文".getBytes())))
                .isInstanceOf(IllegalStateException.class);
        verify(storage).delete(stored.databasePath());
    }

    @Test
    void 未配置画像器不得创建任务而投递失败必须保留pending任务() {
        StyleRepository repository = mock(StyleRepository.class);
        StyleFileStorage storage = mock(StyleFileStorage.class);
        StyleService unavailable = new StyleService(repository, storage, null);
        assertCode(
                () -> unavailable.createPortrait("user-1", "style-1", null),
                503,
                "PORTRAIT_SERVICE_UNAVAILABLE");
        verify(repository, never()).createPortraitTask(anyString(), anyString(), any());

        PortraitRunSubmitter submitter = mock(PortraitRunSubmitter.class);
        PortraitTaskSnapshot task = task("pending", null);
        when(repository.createPortraitTask("user-1", "style-1", null)).thenReturn(task);
        doThrow(new PortraitSubmissionException("AGENT_RUN_SUBMIT_FAILED"))
                .when(submitter)
                .submit("user-1", "style-1", "task-1", "task-1", null);
        StyleService available = new StyleService(repository, storage, submitter);

        var accepted = available.createPortrait("user-1", "style-1", null);

        assertThat(accepted.getTaskId()).isEqualTo("task-1");
        assertThat(accepted.getStatus()).isEqualTo("pending");
    }

    @Test
    void 画像上下文必须读取全部来源不截断并保持稳定格式() {
        StyleRepository repository = mock(StyleRepository.class);
        StyleFileStorage storage = mock(StyleFileStorage.class);
        when(repository.portraitSources("style-1", "task-1")).thenReturn(List.of(
                new PortraitSource("path-1", "甲.txt", 2),
                new PortraitSource("path-2", "乙.txt", 3)));
        when(storage.read("path-1")).thenReturn("甲 乙");
        when(storage.read("path-2")).thenReturn("😀全文");
        StyleService service = new StyleService(repository, storage, null);

        var context = service.portraitContext("style-1", "task-1");

        assertThat(context.getSourceText())
                .isEqualTo("参考资料：甲.txt\n\n甲 乙\n\n参考资料：乙.txt\n\n😀全文");
        assertThat(context.getOriginalCharCount()).isEqualTo(5);
    }

    @Test
    void 回调必须绑定任务运行并把全量五节原子转换为固定Markdown() {
        StyleRepository repository = mock(StyleRepository.class);
        StyleFileStorage storage = mock(StyleFileStorage.class);
        when(repository.transitionPortraitTask(
                        anyString(), anyString(), anyString(), any(), any(), any(Boolean.class)))
                .thenReturn(task("success", null));
        StyleService service = new StyleService(repository, storage, null);
        assertCode(
                () -> service.markProcessing(
                        "style-1", "task-1", new PortraitProcessingRequest("other-run")),
                409,
                "PORTRAIT_RUN_MISMATCH");

        FullPortraitSuccessRequest success = new FullPortraitSuccessRequest(
                "方法", "表达", "生成", "full", 10, "task-1", "特质", false, "标记", 10);
        service.completePortrait("style-1", "task-1", success);

        ArgumentCaptor<cn.inkforge.core.styles.domain.PortraitSuccessData> fields =
                ArgumentCaptor.forClass(cn.inkforge.core.styles.domain.PortraitSuccessData.class);
        verify(repository).transitionPortraitTask(
                org.mockito.ArgumentMatchers.eq("style-1"),
                org.mockito.ArgumentMatchers.eq("task-1"),
                org.mockito.ArgumentMatchers.eq("success"),
                fields.capture(),
                org.mockito.ArgumentMatchers.isNull(),
                org.mockito.ArgumentMatchers.eq(true));
        assertThat(fields.getValue().fields().get("portraitMarkdown"))
                .isEqualTo("创作方法论\n方法\n\n独特标记\n标记\n\n生成风格\n生成\n\n"
                        + "表达特征\n表达\n\n风格特质\n特质");
        assertThat(fields.getValue().fields().get("truncated")).isEqualTo(false);
    }

    @Test
    void 应用文风必须保留显式nullable的CAS语义() {
        StyleRepository repository = mock(StyleRepository.class);
        when(repository.applyStyle("novel-1", "user-1", null, null))
                .thenReturn(new ApplyStyleResult(null, false));
        StyleService service = new StyleService(repository, mock(StyleFileStorage.class), null);
        ApplyStyleRequest request = new ApplyStyleRequest();
        request.setStyleId(JsonNullable.of(null));
        request.setExpectedStyleId(JsonNullable.of(null));

        var result = service.applyStyle("user-1", "novel-1", request);

        assertThat(result.getStyleId()).isNull();
        assertThat(result.getEffective()).isFalse();
    }

    private static StyleSnapshot style() {
        return new StyleSnapshot(
                "style-1", "新文风", "agent",
                null, null, null, null, null, null,
                0, 0, false, null, NOW, NOW, List.of(), List.of());
    }

    private static PortraitTaskSnapshot task(String status, PortraitSection section) {
        return new PortraitTaskSnapshot(
                "task-1", "style-1", section, status, null, NOW, NOW);
    }

    private static void assertCode(Runnable action, int status, String code) {
        assertThatThrownBy(action::run)
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(status);
                    assertThat(error.code()).isEqualTo(code);
                });
    }
}
