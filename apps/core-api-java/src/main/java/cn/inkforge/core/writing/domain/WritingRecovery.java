package cn.inkforge.core.writing.domain;

import cn.inkforge.contracts.api.WritingTaskSummary;
import cn.inkforge.core.db.generated.enums.Writingtaskphase;
import cn.inkforge.core.db.generated.tables.records.WritingtaskRecord;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Set;
import tools.jackson.databind.ObjectMapper;

/** 从耐久 WritingTask 快照派生会话恢复摘要，不读取 Redis 运行态。 */
public final class WritingRecovery {

    private static final List<Writingtaskphase> RESUMABLE_PHASES = List.of(
            Writingtaskphase.awaiting_user_review,
            Writingtaskphase.active,
            Writingtaskphase.waiting_call);
    private static final Set<Writingtaskphase> HISTORICAL_PHASES =
            Set.of(Writingtaskphase.completed, Writingtaskphase.error);
    private WritingRecovery() {}

    public static RecoveryState select(
            List<WritingtaskRecord> tasks, ObjectMapper json) {
        List<WritingtaskRecord> ordered = new ArrayList<>(tasks);
        ordered.sort(Comparator.comparing(
                        WritingtaskRecord::getUpdatedat,
                        Comparator.nullsFirst(Comparator.naturalOrder()))
                .reversed());
        WritingTaskSummary current = null;
        for (Writingtaskphase phase : RESUMABLE_PHASES) {
            current = ordered.stream()
                    .filter(task -> task.getPhase() == phase)
                    .findFirst()
                    .map(task -> summary(task, json))
                    .orElse(null);
            if (current != null) break;
        }
        WritingTaskSummary last = ordered.stream()
                .filter(task -> HISTORICAL_PHASES.contains(task.getPhase()))
                .findFirst()
                .map(task -> summary(task, json))
                .orElse(null);
        return new RecoveryState(current, last);
    }

    private static WritingTaskSummary summary(
            WritingtaskRecord task, ObjectMapper json) {
        WritingGraphSnapshot.Parsed snapshot = task.getGraphstatejson() == null
                ? null
                : WritingGraphSnapshot.parse(
                        task.getGraphstatejson(), json, task.getId(), null, null, null);
        String activeArtifactId = snapshot == null ? null : snapshot.activeArtifactId();
        if (activeArtifactId == null
                && task.getPhase() == Writingtaskphase.awaiting_user_review) {
            activeArtifactId = task.getGeneratedcontent();
        }
        return new WritingTaskSummary(
                activeArtifactId,
                snapshot == null ? null : snapshot.currentOperation(),
                task.getPhase() == Writingtaskphase.awaiting_user_review
                        && activeArtifactId != null,
                task.getId(),
                snapshot == null ? null : snapshot.operationStage(),
                task.getPhase().getLiteral(),
                DatabaseTimestamp.api(task.getUpdatedat()));
    }

    public record RecoveryState(WritingTaskSummary currentTask, WritingTaskSummary lastTask) {}
}
