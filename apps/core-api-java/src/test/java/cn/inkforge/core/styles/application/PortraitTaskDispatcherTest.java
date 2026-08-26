package cn.inkforge.core.styles.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import cn.inkforge.core.styles.domain.PortraitDispatchRecord;
import cn.inkforge.core.styles.domain.PortraitDispatchStatus;
import cn.inkforge.core.styles.domain.PortraitSection;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import org.junit.jupiter.api.Test;

class PortraitTaskDispatcherTest {

    @Test
    void 必须以十分钟前为界复用taskId且只收敛Agent终态() {
        StyleRepository repository = mock(StyleRepository.class);
        PortraitRunSubmitter submitter = mock(PortraitRunSubmitter.class);
        Clock clock = Clock.fixed(Instant.parse("2026-08-25T05:30:00Z"), ZoneOffset.UTC);
        PortraitDispatchRecord record = new PortraitDispatchRecord(
                "task-1", "style-1", "user-1", PortraitSection.STYLE_TRAITS,
                "processing", OffsetDateTime.parse("2026-08-25T05:00:00Z"));
        when(repository.listReconcilable(
                        20, OffsetDateTime.parse("2026-08-25T05:20:00Z")))
                .thenReturn(List.of(record));
        when(submitter.submit(
                        "user-1", "style-1", "task-1", "task-1", PortraitSection.STYLE_TRAITS))
                .thenReturn(PortraitDispatchStatus.QUEUED, PortraitDispatchStatus.FAILED);
        PortraitTaskDispatcher dispatcher = new PortraitTaskDispatcher(
                repository,
                submitter,
                clock,
                20,
                Duration.ofSeconds(5),
                Duration.ofMinutes(10));

        assertThat(dispatcher.runOnce()).isEqualTo(1);
        verify(repository, never()).markDispatchTerminal(
                "style-1", "task-1", PortraitDispatchStatus.QUEUED);
        assertThat(dispatcher.runOnce()).isEqualTo(1);
        verify(repository).markDispatchTerminal(
                "style-1", "task-1", PortraitDispatchStatus.FAILED);
    }

    @Test
    void Agent端口暂不可用时必须保留pending事实供后续重试() {
        StyleRepository repository = mock(StyleRepository.class);
        PortraitRunSubmitter submitter = mock(PortraitRunSubmitter.class);
        Clock clock = Clock.fixed(Instant.parse("2026-08-25T05:30:00Z"), ZoneOffset.UTC);
        PortraitDispatchRecord record = new PortraitDispatchRecord(
                "task-1", "style-1", "user-1", null,
                "pending", OffsetDateTime.parse("2026-08-25T05:29:00Z"));
        when(repository.listReconcilable(
                        20, OffsetDateTime.parse("2026-08-25T05:20:00Z")))
                .thenReturn(List.of(record));
        when(submitter.submit("user-1", "style-1", "task-1", "task-1", null))
                .thenThrow(new PortraitSubmissionException("AGENT_SERVICE_UNAVAILABLE"));
        PortraitTaskDispatcher dispatcher = new PortraitTaskDispatcher(
                repository,
                submitter,
                clock,
                20,
                Duration.ofSeconds(5),
                Duration.ofMinutes(10));

        assertThat(dispatcher.runOnce()).isZero();
        verify(repository, never()).markDispatchTerminal(
                "style-1", "task-1", PortraitDispatchStatus.FAILED);
    }
}
