package cn.inkforge.core.references.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import cn.inkforge.core.references.domain.RagDispatchRecord;
import cn.inkforge.core.references.domain.RagDispatchStatus;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.List;
import org.junit.jupiter.api.Test;

class RagIndexDispatcherTest {

    private static final RagDispatchRecord RECORD = new RagDispatchRecord(
            "user-1",
            "novel-1",
            "reference-1",
            "a".repeat(64),
            OffsetDateTime.parse("2026-08-25T04:00:00.123Z"));

    @Test
    void 已接受状态不落终态而已终止状态由仓储绑定代次() {
        ReferenceRepository repository = mock(ReferenceRepository.class);
        RagIndexSubmitter submitter = mock(RagIndexSubmitter.class);
        when(repository.listPending(20)).thenReturn(List.of(RECORD));
        when(submitter.submit(
                        RECORD.userId(),
                        RECORD.novelId(),
                        RECORD.referenceId(),
                        RECORD.contentHash(),
                        RECORD.generation()))
                .thenReturn(RagDispatchStatus.QUEUED, RagDispatchStatus.FAILED);
        RagIndexDispatcher dispatcher =
                new RagIndexDispatcher(repository, submitter, 20, Duration.ofSeconds(5));

        assertThat(dispatcher.runOnce()).isEqualTo(1);
        verify(repository, never()).markDispatchTerminal(RECORD, RagDispatchStatus.QUEUED);
        assertThat(dispatcher.runOnce()).isEqualTo(1);
        verify(repository).markDispatchTerminal(RECORD, RagDispatchStatus.FAILED);
    }

    @Test
    void 网关暂时失败必须保留待处理意图等待下一轮() {
        ReferenceRepository repository = mock(ReferenceRepository.class);
        RagIndexSubmitter submitter = mock(RagIndexSubmitter.class);
        when(repository.listPending(20)).thenReturn(List.of(RECORD));
        doThrow(new RagSubmissionException("AGENT_RUN_SUBMIT_FAILED"))
                .when(submitter)
                .submit(
                        RECORD.userId(),
                        RECORD.novelId(),
                        RECORD.referenceId(),
                        RECORD.contentHash(),
                        RECORD.generation());
        RagIndexDispatcher dispatcher =
                new RagIndexDispatcher(repository, submitter, 20, Duration.ofSeconds(5));

        assertThat(dispatcher.runOnce()).isZero();
        verify(repository, never()).markDispatchTerminal(
                org.mockito.ArgumentMatchers.any(),
                org.mockito.ArgumentMatchers.any());
    }
}
