package cn.inkforge.core.writing.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.writing.domain.WritingReconciliationTask;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class WritingRunReconcilerTest {

    @Test
    void 必须先持久化对账命令再触发即时投递() {
        List<String> order = new ArrayList<>();
        WritingReconciliationTask task = task("task-1");
        WritingReconciliationRepository repository = new WritingReconciliationRepository() {
            @Override
            public List<WritingReconciliationTask> listReconcilable(int limit) {
                assertThat(limit).isEqualTo(10);
                return List.of(task);
            }

            @Override
            public boolean createCommand(WritingReconciliationTask current) {
                assertThat(current).isEqualTo(task);
                order.add("database");
                return true;
            }
        };
        WritingRunCommandDispatcher dispatcher = dispatcher(() -> order.add("dispatch"));

        int created = new WritingRunReconciler(
                        repository, dispatcher, 10, Duration.ofSeconds(30))
                .runOnce();

        assertThat(created).isEqualTo(1);
        assertThat(order).containsExactly("database", "dispatch");
    }

    @Test
    void 单个暂时性数据库失败不阻断同批其他任务() {
        List<String> created = new ArrayList<>();
        int[] dispatches = {0};
        WritingReconciliationRepository repository = new WritingReconciliationRepository() {
            @Override
            public List<WritingReconciliationTask> listReconcilable(int limit) {
                return List.of(task("bad"), task("good"));
            }

            @Override
            public boolean createCommand(WritingReconciliationTask task) {
                if ("bad".equals(task.id())) {
                    throw new RuntimeException(
                            new java.sql.SQLTransientConnectionException("数据库暂时不可用"));
                }
                created.add(task.id());
                return true;
            }
        };

        int count = new WritingRunReconciler(
                        repository,
                        dispatcher(() -> dispatches[0]++),
                        10,
                        Duration.ofSeconds(30))
                .runOnce();

        assertThat(count).isEqualTo(1);
        assertThat(created).containsExactly("good");
        assertThat(dispatches[0]).isEqualTo(1);
    }

    @Test
    void 确定性契约错误必须上抛且未创建命令时不得投递() {
        int[] dispatches = {0};
        WritingReconciliationRepository invalid = new WritingReconciliationRepository() {
            @Override
            public List<WritingReconciliationTask> listReconcilable(int limit) {
                return List.of(task("invalid"));
            }

            @Override
            public boolean createCommand(WritingReconciliationTask task) {
                throw new IllegalArgumentException("对账命令契约错误");
            }
        };
        WritingRunReconciler reconciler = new WritingRunReconciler(
                invalid,
                dispatcher(() -> dispatches[0]++),
                10,
                Duration.ofSeconds(30));

        assertThatThrownBy(reconciler::runOnce)
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("对账命令契约错误");
        assertThat(dispatches[0]).isZero();

        WritingReconciliationRepository existing = new WritingReconciliationRepository() {
            @Override
            public List<WritingReconciliationTask> listReconcilable(int limit) {
                return List.of(task("existing"));
            }

            @Override
            public boolean createCommand(WritingReconciliationTask task) {
                return false;
            }
        };
        assertThat(new WritingRunReconciler(
                                existing,
                                dispatcher(() -> dispatches[0]++),
                                10,
                                Duration.ofSeconds(30))
                        .runOnce())
                .isZero();
        assertThat(dispatches[0]).isZero();
    }

    private static WritingRunCommandDispatcher dispatcher(Runnable dispatched) {
        WritingCommandDispatchRepository commands = new WritingCommandDispatchRepository() {
            @Override
            public List<cn.inkforge.core.writing.domain.WritingDispatchRecord> claimDue(
                    int limit, java.time.LocalDateTime staleBefore) {
                dispatched.run();
                return List.of();
            }

            @Override
            public cn.inkforge.core.writing.domain.WritingDispatchRecord markAgentActive(String id) {
                throw new UnsupportedOperationException();
            }

            @Override
            public cn.inkforge.core.writing.domain.WritingDispatchRecord recordDispatchFailure(
                    String id, String errorCode) {
                throw new UnsupportedOperationException();
            }

            @Override
            public cn.inkforge.core.writing.domain.WritingDispatchRecord settleDispatchTerminal(
                    String id,
                    cn.inkforge.core.writing.domain.WritingAgentJobStatus status) {
                throw new UnsupportedOperationException();
            }

            @Override
            public cn.inkforge.core.writing.domain.WritingDispatchRecord settleCancelDispatch(
                    String id) {
                throw new UnsupportedOperationException();
            }
        };
        WritingCommandSubmitter submitter = new WritingCommandSubmitter() {
            @Override
            public cn.inkforge.core.writing.domain.WritingAgentJobStatus submit(
                    cn.inkforge.core.writing.domain.WritingDispatchRecord command) {
                return cn.inkforge.core.writing.domain.WritingAgentJobStatus.QUEUED;
            }

            @Override
            public void cancel(cn.inkforge.core.writing.domain.WritingDispatchRecord command) {}
        };
        return new WritingRunCommandDispatcher(
                commands,
                submitter,
                java.time.Clock.systemUTC(),
                1,
                Duration.ofSeconds(1),
                Duration.ofMinutes(10));
    }

    private static WritingReconciliationTask task(String id) {
        return new WritingReconciliationTask(
                id, "user-1", "novel-1", "chapter-1", null, "active", "{}");
    }
}
