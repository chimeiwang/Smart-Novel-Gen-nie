package cn.inkforge.core.video.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import cn.inkforge.contracts.agent.SeedanceRenderOutput;
import cn.inkforge.contracts.agent.SeedanceRenderQueryResponse;
import cn.inkforge.contracts.agent.SeedanceRenderSubmitRequest;
import cn.inkforge.contracts.agent.SeedanceRenderSubmitResponse;
import cn.inkforge.contracts.api.ShotRenderKeyframeManifest;
import cn.inkforge.contracts.api.ShotRenderReferenceManifest;
import cn.inkforge.contracts.api.VideoShotRenderManifest;
import java.math.BigDecimal;
import java.net.URI;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import tools.jackson.databind.ObjectMapper;

class VideoRenderReconcilerTest {

    private final VideoRenderRepository repository = mock(VideoRenderRepository.class);
    private final VideoRenderGateway gateway = mock(VideoRenderGateway.class);
    private final VideoRenderResultArchiver archiver = mock(VideoRenderResultArchiver.class);
    private final VideoAssetStore storage = mock(VideoAssetStore.class);

    @Test
    void 提交沿用数据库冻结哈希并按关键帧语义排序参考图() {
        VideoShotRenderManifest manifest = manifest();
        VideoRenderClaim claim = new VideoRenderClaim(
                "task",
                "project",
                "novel",
                "submitting",
                null,
                0,
                "database-frozen-input-hash",
                manifest);
        when(repository.claimDue(3)).thenReturn(List.of(claim));
        when(gateway.submit(any()))
                .thenReturn(new SeedanceRenderSubmitResponse("provider-task", "task"));

        try (VideoRenderReconciler reconciler = reconciler()) {
            assertThat(reconciler.runOnce()).isEqualTo(1);
        }

        ArgumentCaptor<SeedanceRenderSubmitRequest> request =
                ArgumentCaptor.forClass(SeedanceRenderSubmitRequest.class);
        verify(gateway).submit(request.capture());
        assertThat(request.getValue().getInputHash()).isEqualTo("database-frozen-input-hash");
        assertThat(request.getValue().getPromptText()).isEqualTo("关键帧版供应商提示词");
        assertThat(request.getValue().getReferences())
                .extracting(reference -> reference.getUsageRole().getValue())
                .containsExactly("initial_state", "visual_reference", "end_state");
        verify(repository).markSubmitted("task", "provider-task");
    }

    @Test
    void 成功查询先取得归档所有权再原子完成不可变Take() {
        VideoRenderClaim claim = new VideoRenderClaim(
                "task",
                "project",
                "novel",
                "running",
                "provider-task",
                2,
                "input-hash",
                manifest());
        when(repository.claimDue(3)).thenReturn(List.of(claim));
        SeedanceRenderOutput output = new SeedanceRenderOutput(
                        "https://media.example.volces.com/result.mp4")
                .durationSeconds(new BigDecimal("5.250"))
                .framesPerSecond(24)
                .ratio("16:9")
                .resolution("720p");
        when(gateway.query(any()))
                .thenReturn(new SeedanceRenderQueryResponse(
                                "provider-task",
                                SeedanceRenderQueryResponse.StatusEnum.SUCCEEDED,
                                "task")
                        .output(output));
        when(repository.beginArchiving("task")).thenReturn(true);
        StoredVideoAsset stored = new StoredVideoAsset(
                "project/task.mp4",
                Path.of("/safe/project/task.mp4"),
                "video/mp4",
                128,
                "b".repeat(64));
        when(archiver.archive(
                        "project", "task", "https://media.example.volces.com/result.mp4"))
                .thenReturn(new ArchivedVideoRender("task", stored));

        try (VideoRenderReconciler reconciler = reconciler()) {
            assertThat(reconciler.runOnce()).isEqualTo(1);
        }

        ArgumentCaptor<CompletedVideoTake> take =
                ArgumentCaptor.forClass(CompletedVideoTake.class);
        verify(repository).completeTake(org.mockito.ArgumentMatchers.eq("task"), take.capture());
        assertThat(take.getValue().assetId()).isEqualTo("task");
        assertThat(take.getValue().durationMs()).isEqualTo(5_250);
        assertThat(take.getValue().providerMetadata())
                .containsEntry("framesPerSecond", 24)
                .containsEntry("ratio", "16:9")
                .doesNotContainKey("videoUrl");
    }

    private VideoRenderReconciler reconciler() {
        ProviderAssetTokenCodec tokens = new ProviderAssetTokenCodec(
                "0123456789abcdef0123456789abcdef",
                Duration.ofMinutes(10),
                Clock.fixed(Instant.parse("2026-08-25T05:20:00Z"), ZoneOffset.UTC),
                new ObjectMapper());
        return new VideoRenderReconciler(
                repository,
                gateway,
                archiver,
                storage,
                URI.create("https://inkforge.example"),
                tokens,
                3,
                Duration.ofSeconds(3));
    }

    private static VideoShotRenderManifest manifest() {
        VideoShotRenderManifest manifest = new VideoShotRenderManifest(
                "adaptation",
                5,
                "seedance-model",
                "novel",
                "project",
                "prompt-hash",
                "用户确认提示词",
                "prompt-version",
                VideoShotRenderManifest.RatioEnum.fromValue("16:9"),
                "shot",
                "S01",
                "plan-version",
                5_000);
        manifest.setProviderPromptText("关键帧版供应商提示词");
        manifest.setReferences(List.of(new ShotRenderReferenceManifest(
                "visual-asset",
                "canon-version",
                ShotRenderReferenceManifest.DutyEnum.fromValue("identity"),
                "image/png",
                1,
                "1".repeat(64),
                90)));
        manifest.setKeyframes(List.of(
                new ShotRenderKeyframeManifest(
                        "initial-asset",
                        ShotRenderKeyframeManifest.DutyEnum.fromValue("keyframe"),
                        "initial-version",
                        "image/png",
                        1,
                        ShotRenderKeyframeManifest.RoleEnum.fromValue("initial_state"),
                        "2".repeat(64)),
                new ShotRenderKeyframeManifest(
                        "end-asset",
                        ShotRenderKeyframeManifest.DutyEnum.fromValue("keyframe"),
                        "end-version",
                        "image/png",
                        2,
                        ShotRenderKeyframeManifest.RoleEnum.fromValue("end_state"),
                        "3".repeat(64))));
        return manifest;
    }
}
