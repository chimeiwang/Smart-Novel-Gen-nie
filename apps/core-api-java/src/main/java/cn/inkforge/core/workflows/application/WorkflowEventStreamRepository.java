package cn.inkforge.core.workflows.application;

import cn.inkforge.contracts.api.RunSnapshot;
import cn.inkforge.contracts.api.WorkflowEventEnvelope;
import cn.inkforge.core.platform.db.DatabaseQueryCancellation;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/** V2 Workflow 的 PostgreSQL 权威 snapshot 与耐久事件只读端口。 */
public interface WorkflowEventStreamRepository {

    /**
     * 在同一只读事务中读取 Run snapshot 与其 baseSequence。
     *
     * <p>返回空只表示该 ID 不是 V2 Run；若 ID 命中 V2 但不属于当前用户，必须明确拒绝，不能回退 V1。
     */
    Optional<SnapshotRead> readSnapshot(String userId, String runId);

    /** 一次读取当前进程全部已订阅 Run 的关闭状态和事件高水位。 */
    Map<RunKey, TailState> readTails(List<RunKey> runs);

    /** 与 {@link #readTails(List)} 同形，但必须把当前 JDBC 语句和连接注册到取消句柄。 */
    default Map<RunKey, TailState> readTails(
            List<RunKey> runs, DatabaseQueryCancellation cancellation) {
        return readTails(runs);
    }

    /**
     * 一次公平读取多个 Run 的 PostgreSQL 耐久事件；每个 Run 最多返回 {@code limitPerRun} 条。
     *
     * <p>{@code throughSequence} 来自同一轮高水位读取，避免查询期间新提交的事件越过本轮关闭边界。
     */
    Map<RunKey, List<WorkflowEventEnvelope>> readEventTails(
            List<EventTailRequest> requests, int limitPerRun);

    /** 与批量 Event tail 读取同形，但必须支持 observer 的分阶段显式取消。 */
    default Map<RunKey, List<WorkflowEventEnvelope>> readEventTails(
            List<EventTailRequest> requests,
            int limitPerRun,
            DatabaseQueryCancellation cancellation) {
        return readEventTails(requests, limitPerRun);
    }

    record RunKey(String userId, String runId) {
        public RunKey {
            if (userId == null || userId.isBlank() || runId == null || runId.isBlank()) {
                throw new IllegalArgumentException("Workflow SSE 订阅身份不能为空");
            }
        }
    }

    record EventTailRequest(RunKey key, long afterSequence, long throughSequence) {
        public EventTailRequest {
            if (key == null
                    || afterSequence < 0
                    || throughSequence < afterSequence) {
                throw new IllegalArgumentException("WorkflowEvent tail 范围无效");
            }
        }
    }

    record SnapshotRead(RunSnapshot frame) {
        public SnapshotRead {
            if (frame == null) throw new IllegalArgumentException("Run snapshot 不能为空");
        }
    }

    record TailState(String status, long lastEventSequence) {
        public TailState {
            if (status == null || status.isBlank()) {
                throw new IllegalArgumentException("Workflow Run 状态不能为空");
            }
            if (lastEventSequence < 0) {
                throw new IllegalArgumentException("Workflow Run 事件序号不能为负数");
            }
        }

        public boolean streamShouldClose() {
            return switch (status) {
                case "waiting_user", "completed", "failed", "cancelled" -> true;
                default -> false;
            };
        }
    }
}
