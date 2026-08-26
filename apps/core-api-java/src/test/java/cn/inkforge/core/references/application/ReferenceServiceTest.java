package cn.inkforge.core.references.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import cn.inkforge.contracts.api.CreateReferenceRequest;
import cn.inkforge.contracts.api.ReindexReferenceRequest;
import cn.inkforge.contracts.api.UpdateReferenceRequest;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.references.domain.RagIndexIntent;
import cn.inkforge.core.references.domain.ReferenceCreateResult;
import cn.inkforge.core.references.domain.ReferenceSnapshot;
import cn.inkforge.core.references.domain.ReferenceUpdateResult;
import java.time.OffsetDateTime;
import org.junit.jupiter.api.Test;
import org.openapitools.jackson.nullable.JsonNullable;

class ReferenceServiceTest {

    private static final OffsetDateTime GENERATION =
            OffsetDateTime.parse("2026-08-25T04:00:00.123Z");

    @Test
    void 创建保持正文原样且只有首次有效创建自动投递索引() {
        ReferenceRepository repository = mock(ReferenceRepository.class);
        RagIndexSubmitter submitter = mock(RagIndexSubmitter.class);
        ReferenceSnapshot snapshot = snapshot("  正文\r\n😀  ");
        when(repository.create(anyString(), anyString(), anyString(), any(), any(Boolean.class)))
                .thenReturn(new ReferenceCreateResult(snapshot, true, GENERATION));
        ReferenceService service = new ReferenceService(repository, submitter);
        CreateReferenceRequest request = new CreateReferenceRequest(
                "reference-request-0001",
                "  正文\r\n😀  ",
                "  资料标题  ",
                CreateReferenceRequest.TypeEnum.NOTE);

        var response = service.create("user-1", "novel-1", request);

        assertThat(response.getContent()).isEqualTo("  正文\r\n😀  ");
        assertThat(response.getTitle()).isEqualTo("  资料标题  ");
        assertThat(response.getEffective()).isTrue();
        verify(submitter).submit(
                "user-1", "novel-1", "reference-1", snapshot.contentHash(), GENERATION);
    }

    @Test
    void 自动投递失败不撤销资料但显式重建失败返回503且保留意图() {
        ReferenceRepository repository = mock(ReferenceRepository.class);
        RagIndexSubmitter submitter = mock(RagIndexSubmitter.class);
        ReferenceSnapshot snapshot = snapshot("正文");
        when(repository.create(anyString(), anyString(), anyString(), any(), any(Boolean.class)))
                .thenReturn(new ReferenceCreateResult(snapshot, true, GENERATION));
        doThrow(new IllegalStateException("网络失败"))
                .when(submitter)
                .submit(anyString(), anyString(), anyString(), anyString(), any());
        ReferenceService service = new ReferenceService(repository, submitter);

        assertThat(service.create(
                                "user-1",
                                "novel-1",
                                new CreateReferenceRequest(
                                        "reference-request-0001",
                                        "正文",
                                        "标题",
                                        CreateReferenceRequest.TypeEnum.NOTE))
                        .getId())
                .isEqualTo("reference-1");

        when(repository.prepareReindex(
                        "novel-1", "user-1", "reference-1", snapshot.contentHash()))
                .thenReturn(new RagIndexIntent(snapshot.contentHash(), GENERATION));
        assertCode(
                () -> service.reindex(
                        "user-1",
                        "novel-1",
                        "reference-1",
                        new ReindexReferenceRequest(snapshot.contentHash())),
                503,
                "RAG_INDEX_SUBMIT_FAILED");
        verify(repository).prepareReindex(
                "novel-1", "user-1", "reference-1", snapshot.contentHash());
    }

    @Test
    void 更新保持三态字段并仅在正文真正变化时投递() {
        ReferenceRepository repository = mock(ReferenceRepository.class);
        RagIndexSubmitter submitter = mock(RagIndexSubmitter.class);
        ReferenceSnapshot snapshot = snapshot("新正文");
        when(repository.update(anyString(), anyString(), anyString(), any(), any(), any(Boolean.class)))
                .thenReturn(new ReferenceUpdateResult(snapshot, true, GENERATION));
        ReferenceService service = new ReferenceService(repository, submitter);
        UpdateReferenceRequest request = new UpdateReferenceRequest(GENERATION).content("新正文");
        request.setSourceUrl(JsonNullable.of(null));

        var response = service.update("user-1", "novel-1", "reference-1", request);

        assertThat(response.getContent()).isEqualTo("新正文");
        assertThat(response.getSourceUrl()).isNull();
        verify(submitter).submit(
                "user-1", "novel-1", "reference-1", snapshot.contentHash(), GENERATION);

        UpdateReferenceRequest invalid = new UpdateReferenceRequest(GENERATION);
        invalid.setTitle(JsonNullable.of(null));
        assertCode(
                () -> service.update("user-1", "novel-1", "reference-1", invalid),
                422,
                "REFERENCE_FIELD_REQUIRED");
    }

    @Test
    void 空标题空补丁与未配置索引均明确失败() {
        ReferenceRepository repository = mock(ReferenceRepository.class);
        ReferenceService service = new ReferenceService(repository, null);
        assertCode(
                () -> service.create(
                        "user-1",
                        "novel-1",
                        new CreateReferenceRequest(
                                "reference-request-0001",
                                "正文",
                                "  ",
                                CreateReferenceRequest.TypeEnum.NOTE)),
                422,
                "REFERENCE_TITLE_REQUIRED");
        assertCode(
                () -> service.update(
                        "user-1",
                        "novel-1",
                        "reference-1",
                        new UpdateReferenceRequest(GENERATION)),
                422,
                "EMPTY_UPDATE");
        assertCode(
                () -> service.reindex(
                        "user-1",
                        "novel-1",
                        "reference-1",
                        new ReindexReferenceRequest("a".repeat(64))),
                503,
                "RAG_INDEX_UNAVAILABLE");
        verify(repository, never()).prepareReindex(anyString(), anyString(), anyString(), anyString());
    }

    private static ReferenceSnapshot snapshot(String content) {
        return new ReferenceSnapshot(
                "reference-1",
                "  资料标题  ",
                "note",
                content,
                null,
                "disabled",
                cn.inkforge.core.references.domain.RagRules.sha256(content),
                "等待重新索引",
                GENERATION,
                GENERATION);
    }

    private static void assertCode(Runnable action, int status, String code) {
        assertThatThrownBy(action::run)
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(status);
                    assertThat(error.code()).isEqualTo(code);
                });
    }
}
