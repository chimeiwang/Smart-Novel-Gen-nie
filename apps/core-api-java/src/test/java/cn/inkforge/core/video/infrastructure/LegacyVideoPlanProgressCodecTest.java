package cn.inkforge.core.video.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.SceneAssetsStageArguments;
import cn.inkforge.contracts.api.VideoPlanAttemptState;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.video.application.LegacyVideoPlanProgress;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.openapitools.jackson.nullable.JsonNullable;
import tools.jackson.databind.ObjectMapper;

class LegacyVideoPlanProgressCodecTest {

    private final ObjectMapper json = new ObjectMapper();
    private final LegacyVideoPlanProgressCodec codec = new LegacyVideoPlanProgressCodec(json);

    @Test
    void 进度与终态信封必须保持Python规范JSON和完整预留账本() {
        SceneAssetsStageArguments assets = new SceneAssetsStageArguments(
                List.of(),
                "建立威胁",
                "动作由声音触发",
                List.of("禁止无动机移动"),
                "沈砚在雨夜确认威胁",
                "雨夜对峙",
                "冷峻现实主义");
        VideoPlanAttemptState attempt = new VideoPlanAttemptState(null, 1);
        attempt.setPendingStage(JsonNullable.of(null));
        attempt.setInheritedCalls(0);
        LegacyVideoPlanProgress progress = new LegacyVideoPlanProgress(
                "scene_assets",
                assets,
                null,
                attempt,
                List.of(new LegacyVideoPlanProgress.Reservation(
                        "reserve-assets-1", "empty", "scene_assets", 0)),
                null,
                null);

        String encoded = codec.encodeProgress(progress);
        LegacyVideoPlanProgress decoded = codec.decodeActiveProgress(encoded);

        assertThat(decoded).isEqualTo(progress);
        assertThat(encoded).isEqualTo(new String(
                CommandIdempotency.canonicalJsonBytes(
                        json.readValue(encoded, Object.class), json),
                StandardCharsets.UTF_8));

        String terminal = codec.encodeTerminal(
                encoded,
                "failed",
                "failure-event-1",
                Map.of(
                        "code", "VIDEO_PLAN_FAILED",
                        "message", "完整失败详情",
                        "recoverable", true));
        LegacyVideoPlanProgressCodec.TerminalResult result = codec.decodeTerminal(terminal);

        assertThat(result.status()).isEqualTo("failed");
        assertThat(result.eventId()).isEqualTo("failure-event-1");
        assertThat(result.progress()).isEqualTo(json.readTree(encoded));
        assertThat(codec.terminalAttemptState(terminal).getReservedCalls()).isEqualTo(1);
        assertThat(codec.terminalAttemptState(terminal).getPendingStage().orElse(null)).isNull();
    }

    @Test
    void 损坏或不连续的调用账本不能退化为空进度() {
        String damaged = """
                {
                  "kind":"video_plan_progress_checkpoint",
                  "schemaVersion":"2.0",
                  "checkpointStage":"empty",
                  "sceneAssetsPlan":null,
                  "storyPlan":null,
                  "attemptState":{"reservedCalls":1,"inheritedCalls":0,"pendingStage":"scene_assets"},
                  "inheritedFromTaskId":null,
                  "inheritedInputFingerprint":null,
                  "reservations":[{
                    "eventId":"event-1",
                    "checkpointStage":"empty",
                    "stage":"scene_assets",
                    "reservedCallsBefore":1
                  }]
                }
                """;

        assertThatThrownBy(() -> codec.decodeActiveProgress(damaged))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("计数不连续");
    }

    @Test
    void 冻结任务载荷必须补齐旧默认值并生成跨服务指纹() {
        String emptySettingsHash = CommandIdempotency.sha256("[]".getBytes(StandardCharsets.UTF_8));
        String payload = """
                {
                  "projectId":"project-1",
                  "sceneId":"scene-1",
                  "chapterId":"chapter-1",
                  "title":"雨夜对峙",
                  "sourceText":"沈砚听见门外异响。",
                  "durationSeconds":15,
                  "ratio":"16:9",
                  "settingSnapshot":{"fingerprint":"%s","entries":[]}
                }
                """.formatted(emptySettingsHash);

        LegacyVideoPlanProgressCodec.FrozenPayload frozen = codec.parseFrozenPayload(payload);

        assertThat(frozen.agentPayload())
                .containsEntry("planningRoute", "legacy_strict_tool_v1")
                .containsEntry("planningModel", "deepseek-v4-flash")
                .containsEntry("directorDraftVersion", "1.0")
                .containsEntry("revisionInstruction", null)
                .containsEntry("revisionBaseline", null);
        assertThat(frozen.inputFingerprint()).matches("[0-9a-f]{64}");
        assertThat(frozen.inputFingerprint())
                .isEqualTo("6a5e4254e3878720161bc6c03ec783b4212cf638899f6a17b8b5280fba3a14d7");
        assertThat(frozen.projectId()).isEqualTo("project-1");
    }
}
