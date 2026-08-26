package cn.inkforge.core.writing.domain;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.contracts.api.WritingRunOutcome;
import cn.inkforge.core.db.generated.enums.Reviewartifactkind;
import cn.inkforge.core.db.generated.enums.Reviewartifactstatus;
import cn.inkforge.core.db.generated.enums.Writingtaskphase;
import cn.inkforge.core.db.generated.tables.records.ReviewartifactRecord;
import cn.inkforge.core.db.generated.tables.records.WritingruncommandRecord;
import cn.inkforge.core.db.generated.tables.records.WritingtaskRecord;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class WritingRunStatusProjectorTest {

    private static final LocalDateTime NOW = LocalDateTime.of(2026, 8, 5, 12, 30);
    private WritingRunStatusProjector projector;

    @BeforeEach
    void setUp() {
        projector = new WritingRunStatusProjector(
                new ObjectMapper(),
                new WritingRunOutcomeProjector(),
                Clock.fixed(Instant.parse("2026-08-05T12:35:00Z"), ZoneOffset.UTC));
    }

    @Test
    void 完整复审报告不得被截断且只在终态成功后公开() {
        String report = "完整复审报告".repeat(14_001);
        WritingruncommandRecord succeeded = command(
                "start-1",
                "start",
                "review_chapter",
                "succeeded",
                Map.of("_inkforgeTerminalCallbackResult", Map.of("finalResponse", report)),
                NOW);

        var status = projector.project(task("completed", null), List.of(succeeded), List.of());

        assertThat(status.getReviewReport()).isEqualTo(report);
        assertThat(status.getReviewReport().length()).isGreaterThan(80_000);
        assertThat(status.getOutcome().getState()).isEqualTo(WritingRunOutcome.StateEnum.SUCCEEDED);
        assertThat(status.getOutcome().getResult().getKind().getValue())
                .isEqualTo("final_message");

        succeeded.setStatus("processing");
        var active = projector.project(task("active", null), List.of(succeeded), List.of());
        assertThat(active.getReviewReport()).isNull();
        assertThat(active.getOutcome().getResult().getReady()).isFalse();
    }

    @Test
    void 检查点只公开四个白名单字段() {
        String graph = json(Map.of(
                "eventSequence", 8,
                "phase", "writing",
                "operationStage", "drafting",
                "operationStep", "scene-2",
                "messages", List.of("不应公开"),
                "toolResults", Map.of("secret", true)));
        WritingruncommandRecord command = command(
                "start-1", "start", "review_chapter", "processing", null, NOW);

        var status = projector.project(task("active", graph), List.of(command), List.of());

        assertThat(status.getCheckpoint()).isNotNull();
        assertThat(status.getCheckpoint().getEventSequence()).isEqualTo(8);
        assertThat(status.getCheckpoint().getPhase()).isEqualTo("writing");
        assertThat(status.getCheckpoint().getOperationStage()).isEqualTo("drafting");
        assertThat(status.getCheckpoint().getOperationStep()).isEqualTo("scene-2");
    }

    @Test
    void 长篇草案必须与任务操作身份和生命周期一致() {
        var waiting = projector.project(
                task("awaiting_user_review", null),
                List.of(command("start-1", "start", "plan_chapter", "succeeded", null, NOW)),
                List.of(artifact("artifact-1", "beat_plan", "awaiting_user", 1, NOW)));

        assertThat(waiting.getOutcome().getState())
                .isEqualTo(WritingRunOutcome.StateEnum.WAITING_USER);
        assertThat(waiting.getActiveArtifactId()).isEqualTo("artifact-1");

        var wrongLifecycle = projector.project(
                task("completed", null),
                List.of(command("start-1", "start", "plan_chapter", "succeeded", null, NOW)),
                List.of(artifact("artifact-1", "beat_plan", "applied", 1, NOW)));
        assertThat(wrongLifecycle.getOutcome().getState())
                .isEqualTo(WritingRunOutcome.StateEnum.INCONSISTENT);
        assertThat(wrongLifecycle.getOutcome().getResult().getReady()).isFalse();
    }

    @Test
    void 自然语言长篇启动使用受信回调持久化的操作身份() {
        WritingruncommandRecord natural = command(
                "start-1", "start", "review_chapter", "succeeded", null, NOW);
        natural.setPayloadjson(json(Map.of(
                "version", 1,
                "chapterId", "chapter-1",
                "writingSessionId", "session-1",
                "sourceBindings", List.of(),
                "resume", false)));
        String graph = json(Map.of(
                "currentOperation", Map.of("kind", "write_chapter"),
                "activeArtifactId", "artifact-1"));

        var status = projector.project(
                task("awaiting_user_review", graph),
                List.of(natural),
                List.of(artifact("artifact-1", "chapter_draft", "awaiting_user", 1, NOW)));

        assertThat(status.getOperation().getValue()).isEqualTo("write_chapter");
        assertThat(status.getOutcome().getState())
                .isEqualTo(WritingRunOutcome.StateEnum.WAITING_USER);
        assertThat(status.getActiveArtifactId()).isEqualTo("artifact-1");
    }

    @Test
    void 审核批准必须有完整持久身份才能使长篇结果成功() {
        WritingruncommandRecord start =
                command("start-1", "start", "write_chapter", "succeeded", null, NOW);
        WritingruncommandRecord decision = decision("approve", Map.of(
                "artifactId", "artifact-1",
                "taskId", "task-1",
                "commandId", "decision-approve",
                "decision", "approve",
                "status", "pending",
                "savedCount", 1,
                "deleted", false));
        var status = projector.project(
                task("completed", null),
                List.of(start, decision),
                List.of(artifact("artifact-1", "chapter_draft", "applied", 1, NOW)));

        assertThat(status.getOutcome().getState()).isEqualTo(WritingRunOutcome.StateEnum.SUCCEEDED);
        assertThat(status.getOutcome().getResult().getReady()).isTrue();

        decision.setResultjson(json(Map.of(
                "artifactId", "artifact-1",
                "taskId", "task-other",
                "commandId", "decision-approve",
                "decision", "approve",
                "status", "pending")));
        var mismatch = projector.project(
                task("completed", null),
                List.of(start, decision),
                List.of(artifact("artifact-1", "chapter_draft", "applied", 1, NOW)));
        assertThat(mismatch.getOutcome().getState())
                .isEqualTo(WritingRunOutcome.StateEnum.INCONSISTENT);
    }

    @Test
    void 丢弃决定在草案删除后仍能从命令事实收敛() {
        WritingruncommandRecord start =
                command("start-1", "start", "plan_chapter", "succeeded", null, NOW);
        WritingruncommandRecord discard = decision("discard", Map.of(
                "artifactId", "artifact-1",
                "taskId", "task-1",
                "commandId", "decision-discard",
                "decision", "discard",
                "status", "pending",
                "deleted", true));

        var status = projector.project(
                task("completed", null), List.of(start, discard), List.of());

        assertThat(status.getOutcome().getState()).isEqualTo(WritingRunOutcome.StateEnum.SUCCEEDED);
        assertThat(status.getOutcome().getResult().getId()).isEqualTo("artifact-1");
        assertThat(status.getOutcome().getResult().getReady()).isTrue();
    }

    @Test
    void 多个草案时必须由检查点给出唯一活动身份() {
        WritingruncommandRecord start =
                command("start-1", "start", "plan_chapter", "succeeded", null, NOW);
        ReviewartifactRecord first = artifact("artifact-1", "beat_plan", "awaiting_user", 1, NOW);
        ReviewartifactRecord second = artifact("artifact-2", "beat_plan", "awaiting_user", 1, NOW);
        var ambiguous = projector.project(
                task("awaiting_user_review", null), List.of(start), List.of(first, second));
        assertThat(ambiguous.getOutcome().getState())
                .isEqualTo(WritingRunOutcome.StateEnum.INCONSISTENT);

        String graph = json(Map.of(
                "eventSequence", 3,
                "phase", "waiting_user",
                "artifactReview", Map.of("activeArtifactId", "artifact-1")));
        var selected = projector.project(
                task("awaiting_user_review", graph), List.of(start), List.of(first, second));
        assertThat(selected.getOutcome().getState())
                .isEqualTo(WritingRunOutcome.StateEnum.WAITING_USER);
        assertThat(selected.getActiveArtifactId()).isEqualTo("artifact-1");
    }

    @Test
    void 中短篇候选和全文检查分别验证真实成功产品() {
        WritingruncommandRecord generate = shortCommand(
                "short-1",
                "generate_manuscript",
                "manuscript",
                Map.of("candidateVersionId", "candidate-1"));
        ReviewartifactRecord candidate =
                artifact("candidate-1", "chapter_draft", "awaiting_user", 1, NOW);
        var generated = projector.project(
                task("completed", null), List.of(generate), List.of(candidate));
        assertThat(generated.getOutcome().getState())
                .isEqualTo(WritingRunOutcome.StateEnum.SUCCEEDED);
        assertThat(generated.getCandidateVersionId()).isEqualTo("candidate-1");

        WritingruncommandRecord check = shortCommand(
                "check-1", "full_check", "manuscript", Map.of("checkReport", Map.of("ok", true)));
        var checked = projector.project(task("completed", null), List.of(check), List.of());
        assertThat(checked.getOutcome().getState()).isEqualTo(WritingRunOutcome.StateEnum.SUCCEEDED);
        assertThat(checked.getCheckReport()).containsEntry("ok", true);
    }

    @Test
    void 空操作取消链保留前序成功或失败结果并展示当前命令() {
        WritingruncommandRecord start = command(
                "start-1",
                "start",
                "review_chapter",
                "succeeded",
                Map.of("_inkforgeTerminalCallbackResult", Map.of("finalResponse", "复审结论")),
                NOW);
        WritingruncommandRecord cancel1 = cancel(
                "cancel-1", "start-1", NOW.plusSeconds(1));
        WritingruncommandRecord cancel2 = cancel(
                "cancel-2", "cancel-1", NOW.plusSeconds(2));

        var status = projector.project(
                task("completed", null), List.of(start, cancel1, cancel2), List.of());

        assertThat(status.getReviewReport()).isEqualTo("复审结论");
        assertThat(status.getOutcome().getState()).isEqualTo(WritingRunOutcome.StateEnum.SUCCEEDED);
        assertThat(status.getOutcome().getCurrentCommand().getId()).isEqualTo("cancel-2");
    }

    @Test
    void 失败结果只公开稳定错误对象() {
        WritingruncommandRecord failed = command(
                "start-1",
                "start",
                "review_chapter",
                "failed",
                Map.of("code", "MODEL_FAILED", "message", "模型调用失败"),
                NOW);
        failed.setLasterror("MODEL_FAILED");

        var status = projector.project(task("error", null), List.of(failed), List.of());

        assertThat(status.getOutcome().getState()).isEqualTo(WritingRunOutcome.StateEnum.FAILED);
        assertThat(status.getError())
                .containsExactlyInAnyOrderEntriesOf(Map.of(
                        "code", "MODEL_FAILED", "message", "模型调用失败"));
    }

    private static WritingtaskRecord task(String phase, String graph) {
        WritingtaskRecord task = new WritingtaskRecord();
        task.setId("task-1");
        task.setNovelid("novel-1");
        task.setChapterid("chapter-1");
        task.setWritingsessionid("session-1");
        task.setPhase(Writingtaskphase.lookupLiteral(phase));
        task.setTargetwordcount(4000);
        task.setSelectedagents("写作,编辑");
        task.setGraphstatejson(graph);
        task.setCreatedat(NOW);
        task.setUpdatedat(NOW);
        return task;
    }

    private static WritingruncommandRecord command(
            String id,
            String kind,
            String operation,
            String status,
            Map<String, ?> result,
            LocalDateTime createdAt) {
        WritingruncommandRecord command = new WritingruncommandRecord();
        command.setId(id);
        command.setTaskid("task-1");
        command.setKind(kind);
        command.setPayloadjson(json(Map.of(
                "_inkforgeCommand", Map.of("schemaVersion", 1),
                "job", Map.of(
                        "workflow", "long_serial",
                        "operation", operation,
                        "target", Map.of("type", "chapter", "id", "chapter-1"),
                        "scope", Map.of("kind", "chapter", "chapterId", "chapter-1")))));
        command.setResultjson(result == null ? null : json(result));
        command.setIdempotencykey("key-" + id);
        command.setStatus(status);
        command.setAttemptcount(0);
        command.setNextattemptat(createdAt);
        command.setCreatedat(createdAt);
        command.setUpdatedat(createdAt);
        return command;
    }

    private static WritingruncommandRecord decision(String decision, Map<String, ?> result) {
        String id = "decision-" + decision;
        WritingruncommandRecord command = command(
                id, "artifact_decision", "write_chapter", "succeeded", result, NOW.plusSeconds(1));
        command.setArtifactid("artifact-1");
        command.setDecision(decision);
        command.setPayloadjson(json(Map.of(
                "_inkforgeCommand", Map.of(
                        "schemaVersion", 1,
                        "clientRequestId", "request-" + decision,
                        "commandKind", "artifact_decision",
                        "resourceIdentity", Map.of("artifactId", "artifact-1"),
                        "normalizedBody", Map.of(),
                        "requestFingerprint", "a".repeat(64)),
                "job", Map.of(
                        "workflow", "long_serial",
                        "operation", "write_chapter",
                        "resume", true,
                        "resumeInput", Map.of(
                                "artifactId", "artifact-1", "decision", decision)))));
        return command;
    }

    private static WritingruncommandRecord shortCommand(
            String id, String operation, String documentType, Map<String, ?> result) {
        WritingruncommandRecord command = command(
                id, "start", operation, "succeeded", result, NOW);
        command.setArtifactid(result.get("candidateVersionId") instanceof String value ? value : null);
        command.setPayloadjson(json(Map.of(
                "workflow", "short_medium",
                "operation", operation,
                "documentType", documentType,
                "chapterId", "chapter-1")));
        return command;
    }

    private static WritingruncommandRecord cancel(
            String id, String priorCommandId, LocalDateTime createdAt) {
        WritingruncommandRecord command = command(
                id,
                "resume",
                "review_chapter",
                "succeeded",
                Map.of(
                        "effective", false,
                        "priorOutcome", Map.of("currentCommand", Map.of("id", priorCommandId))),
                createdAt);
        command.setPayloadjson(json(Map.of(
                "_inkforgeCommand", Map.of(
                        "schemaVersion", 1,
                        "commandKind", "cancel"),
                "job", Map.of())));
        return command;
    }

    private static ReviewartifactRecord artifact(
            String id, String kind, String status, int revision, LocalDateTime updatedAt) {
        ReviewartifactRecord artifact = new ReviewartifactRecord();
        artifact.setId(id);
        artifact.setTaskid("task-1");
        artifact.setNovelid("novel-1");
        artifact.setChapterid("chapter-1");
        artifact.setArtifactkey("artifact-key-" + id);
        artifact.setKind(Reviewartifactkind.lookupLiteral(kind));
        artifact.setStatus(Reviewartifactstatus.lookupLiteral(status));
        artifact.setPayloadjson("{}");
        artifact.setRevision(revision);
        artifact.setCreatedat(NOW);
        artifact.setUpdatedat(updatedAt);
        return artifact;
    }

    private static String json(Object value) {
        return new ObjectMapper().writeValueAsString(value);
    }
}
