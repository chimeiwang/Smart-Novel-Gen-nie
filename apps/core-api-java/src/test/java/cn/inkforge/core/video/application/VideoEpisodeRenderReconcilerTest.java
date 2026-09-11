package cn.inkforge.core.video.application;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.contracts.agent.SeedanceRenderOutput;
import cn.inkforge.contracts.agent.SeedanceRenderQueryRequest;
import cn.inkforge.contracts.agent.SeedanceRenderQueryResponse;
import cn.inkforge.contracts.agent.SeedanceRenderSubmitRequest;
import cn.inkforge.contracts.agent.SeedanceRenderSubmitResponse;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

class VideoEpisodeRenderReconcilerTest {

    @Test
    void 提交时按首帧视觉参考转折帧和尾帧排序冻结图片() {
        FakeRepository repository = new FakeRepository();
        repository.claims.add(claim(
                "submitting",
                null,
                "simulated",
                List.of(
                        keyframe(1, "initial_state"),
                        keyframe(2, "transition_anchor"),
                        keyframe(3, "end_state"))));
        List<SeedanceRenderSubmitRequest> requests = new ArrayList<>();
        VideoRenderGateway gateway = new VideoRenderGateway() {
            @Override
            public SeedanceRenderSubmitResponse submit(SeedanceRenderSubmitRequest request) {
                requests.add(request);
                return new SeedanceRenderSubmitResponse("simulated-task-1", "task-1");
            }

            @Override
            public SeedanceRenderQueryResponse query(SeedanceRenderQueryRequest request) {
                throw new AssertionError("提交阶段不能查询");
            }
        };

        try (VideoEpisodeRenderReconciler reconciler = reconciler(
                repository, gateway, unavailableSimulator(), rejectingArchiver())) {
            assertThat(reconciler.runOnce()).isEqualTo(1);
        }

        assertThat(requests).singleElement();
        assertThat(requests.get(0).getReferences())
                .extracting(reference -> reference.getUsageRole().getValue())
                .containsExactly(
                        "initial_state", "visual_reference", "transition_anchor", "end_state");
        assertThat(requests.get(0).getReferences())
                .extracting(reference -> reference.getOrdinal())
                .containsExactly(1, 2, 3, 4);
    }

    @Test
    void 模拟任务生成明确占位Take且没有供应商用量() {
        FakeRepository repository = new FakeRepository();
        repository.claims.add(claim("running", "simulated-task-1", "simulated"));
        VideoRenderGateway gateway = new VideoRenderGateway() {
            @Override
            public SeedanceRenderSubmitResponse submit(SeedanceRenderSubmitRequest request) {
                throw new AssertionError("查询阶段不能再次提交");
            }

            @Override
            public SeedanceRenderQueryResponse query(SeedanceRenderQueryRequest request) {
                return new SeedanceRenderQueryResponse()
                        .taskId("task-1")
                        .providerTaskId("simulated-task-1")
                        .status(SeedanceRenderQueryResponse.StatusEnum.SUCCEEDED)
                        .output(new SeedanceRenderOutput()
                                .videoUrl("inkforge-simulated://task-1")
                                .mediaKind(SeedanceRenderOutput.MediaKindEnum.SIMULATED_PLACEHOLDER)
                                .usage(Map.of()));
            }
        };
        VideoRenderSimulator simulator = new VideoRenderSimulator() {
            @Override
            public boolean available() {
                return true;
            }

            @Override
            public ArchivedVideoRender render(VideoRenderClaim claim) {
                throw new AssertionError("不能构造旧 adaptation claim");
            }

            @Override
            public ArchivedVideoRender render(VideoEpisodeRenderClaim claim) {
                return new ArchivedVideoRender(
                        claim.taskId(),
                        stored("project-1/task-1.mp4", "video/mp4"),
                        6_000);
            }
        };
        try (VideoEpisodeRenderReconciler reconciler = reconciler(
                repository, gateway, simulator, rejectingArchiver())) {
            assertThat(reconciler.runOnce()).isEqualTo(1);
        }

        assertThat(repository.completed).isNotNull();
        assertThat(repository.completed.providerMetadata())
                .containsEntry("mediaKind", "simulated_placeholder")
                .containsEntry("executionMode", "simulated")
                .containsEntry("usage", Map.of());
        assertThat(repository.completed.lastFrame()).isNull();
    }

    @Test
    void 真实结果归档尾帧并完整保存供应商用量() {
        FakeRepository repository = new FakeRepository();
        repository.claims.add(claim("running", "provider-1", "live"));
        VideoRenderGateway gateway = new VideoRenderGateway() {
            @Override
            public SeedanceRenderSubmitResponse submit(SeedanceRenderSubmitRequest request) {
                throw new AssertionError("查询阶段不能再次提交");
            }

            @Override
            public SeedanceRenderQueryResponse query(SeedanceRenderQueryRequest request) {
                return new SeedanceRenderQueryResponse()
                        .taskId("task-1")
                        .providerTaskId("provider-1")
                        .status(SeedanceRenderQueryResponse.StatusEnum.SUCCEEDED)
                        .output(new SeedanceRenderOutput()
                                .videoUrl("https://result.example/video.mp4")
                                .lastFrameUrl("https://result.example/last-frame.png")
                                .mediaKind(SeedanceRenderOutput.MediaKindEnum.PROVIDER_MEDIA)
                                .usage(Map.of(
                                        "completion_tokens", 140,
                                        "total_tokens", 140)));
            }
        };
        VideoRenderResultArchiver archiver = new VideoRenderResultArchiver() {
            @Override
            public ArchivedVideoRender archive(
                    String projectId, String assetId, String videoUrl) {
                return new ArchivedVideoRender(
                        assetId,
                        stored("project-1/task-1.mp4", "video/mp4"),
                        6_000);
            }

            @Override
            public ArchivedVideoFrame archiveImage(
                    String projectId, String assetId, String imageUrl) {
                return new ArchivedVideoFrame(
                        assetId,
                        stored("project-1/task-1-last-frame.png", "image/png"));
            }
        };
        try (VideoEpisodeRenderReconciler reconciler = reconciler(
                repository, gateway, unavailableSimulator(), archiver)) {
            assertThat(reconciler.runOnce()).isEqualTo(1);
        }

        assertThat(repository.completed).isNotNull();
        assertThat(repository.completed.providerMetadata().get("usage"))
                .isEqualTo(Map.of("completion_tokens", 140, "total_tokens", 140));
        assertThat(repository.completed.providerMetadata())
                .doesNotContainKeys("videoUrl", "lastFrameUrl");
        assertThat(repository.completed.lastFrame().assetId())
                .isEqualTo("task-1-last-frame");
    }

    @Test
    void 提交结果未知只标记原任务且不做第二次提交() {
        FakeRepository repository = new FakeRepository();
        repository.claims.add(claim("submitting", null, "live"));
        int[] calls = {0};
        VideoRenderGateway gateway = new VideoRenderGateway() {
            @Override
            public SeedanceRenderSubmitResponse submit(SeedanceRenderSubmitRequest request) {
                calls[0]++;
                throw new VideoRenderSubmissionUnknownException();
            }

            @Override
            public SeedanceRenderQueryResponse query(SeedanceRenderQueryRequest request) {
                throw new AssertionError("提交阶段不能查询");
            }
        };
        try (VideoEpisodeRenderReconciler reconciler = reconciler(
                repository, gateway, unavailableSimulator(), rejectingArchiver())) {
            assertThat(reconciler.runOnce()).isEqualTo(1);
        }

        assertThat(calls[0]).isEqualTo(1);
        assertThat(repository.submissionUnknown).isEqualTo("task-1");
        assertThat(repository.completed).isNull();
    }

    @Test
    void 网关未分类运行时异常必须收敛为提交未知() {
        FakeRepository repository = new FakeRepository();
        repository.claims.add(claim("submitting", null, "live"));
        VideoRenderGateway gateway = new VideoRenderGateway() {
            @Override
            public SeedanceRenderSubmitResponse submit(SeedanceRenderSubmitRequest request) {
                throw new IllegalStateException("POST 送达状态未知");
            }

            @Override
            public SeedanceRenderQueryResponse query(SeedanceRenderQueryRequest request) {
                throw new AssertionError("提交阶段不能查询");
            }
        };
        try (VideoEpisodeRenderReconciler reconciler = reconciler(
                repository, gateway, unavailableSimulator(), rejectingArchiver())) {
            assertThat(reconciler.runOnce()).isEqualTo(1);
        }

        assertThat(repository.submissionUnknown).isEqualTo("task-1");
        assertThat(repository.submissionRejected).isNull();
    }

    @Test
    void 本地请求构造非法可在发送前明确拒绝() {
        FakeRepository repository = new FakeRepository();
        repository.claims.add(claim("submitting", null, "unsupported-mode"));
        int[] calls = {0};
        VideoRenderGateway gateway = new VideoRenderGateway() {
            @Override
            public SeedanceRenderSubmitResponse submit(SeedanceRenderSubmitRequest request) {
                calls[0]++;
                throw new AssertionError("非法本地输入不能进入网关");
            }

            @Override
            public SeedanceRenderQueryResponse query(SeedanceRenderQueryRequest request) {
                throw new AssertionError("提交阶段不能查询");
            }
        };
        try (VideoEpisodeRenderReconciler reconciler = reconciler(
                repository, gateway, unavailableSimulator(), rejectingArchiver())) {
            assertThat(reconciler.runOnce()).isEqualTo(1);
        }

        assertThat(calls[0]).isZero();
        assertThat(repository.submissionRejected).isEqualTo("task-1");
        assertThat(repository.submissionRejectedCode)
                .isEqualTo("SEEDANCE_SUBMIT_INPUT_INVALID");
        assertThat(repository.submissionUnknown).isNull();
    }

    private static VideoEpisodeRenderReconciler reconciler(
            FakeRepository repository,
            VideoRenderGateway gateway,
            VideoRenderSimulator simulator,
            VideoRenderResultArchiver archiver) {
        return new VideoEpisodeRenderReconciler(
                repository,
                () -> gateway,
                archiver,
                simulator,
                new FakeStorage(),
                java.net.URI.create("https://media.example"),
                new ProviderAssetTokenCodec(
                        "0123456789abcdef0123456789abcdef",
                        Duration.ofMinutes(10),
                        Clock.fixed(Instant.parse("2026-09-10T00:00:00Z"), ZoneOffset.UTC),
                        new ObjectMapper()),
                1,
                Duration.ofSeconds(1));
    }

    private static VideoEpisodeRenderClaim claim(
            String status, String providerTaskId, String executionMode) {
        return claim(status, providerTaskId, executionMode, List.of());
    }

    private static VideoEpisodeRenderClaim claim(
            String status,
            String providerTaskId,
            String executionMode,
            List<VideoEpisodeRenderKeyframe> keyframes) {
        VideoEpisodeRenderInput input = new VideoEpisodeRenderInput(
                keyframes.isEmpty()
                        ? "video-production-shot-input/1.0"
                        : "video-production-shot-input/1.1",
                "shot-1",
                "shot-version-1",
                1,
                "a".repeat(64),
                "scene-1",
                List.of("line-1"),
                "seedance",
                "seedance-test",
                "reference",
                executionMode,
                "live".equals(executionMode),
                "prompt-1",
                "冻结提示词",
                "9:16",
                6,
                "720p",
                true,
                false,
                "mp4",
                List.of(new VideoEpisodeRenderReference(
                        1,
                        "canon-1",
                        "b".repeat(64),
                        "reference-1",
                        "c".repeat(64),
                        "image/png",
                        "identity",
                        70)),
                keyframes,
                Map.of(
                        "schemaVersion",
                        keyframes.isEmpty()
                                ? "video-production-shot-input/1.0"
                                : "video-production-shot-input/1.1"));
        return new VideoEpisodeRenderClaim(
                "task-1",
                "episode-1",
                "baseline-1",
                "project-1",
                "novel-1",
                "shot-1",
                "shot-version-1",
                status,
                providerTaskId,
                1,
                "d".repeat(64),
                input);
    }

    private static VideoEpisodeRenderKeyframe keyframe(int ordinal, String role) {
        return new VideoEpisodeRenderKeyframe(
                ordinal,
                "keyframe-version-" + ordinal,
                role,
                "keyframe-asset-" + ordinal,
                Integer.toString(ordinal).repeat(64),
                "image/png",
                "keyframe",
                "f".repeat(64));
    }

    private static StoredVideoAsset stored(String key, String mimeType) {
        return new StoredVideoAsset(
                key,
                Path.of(key),
                mimeType,
                100,
                "e".repeat(64));
    }

    private static VideoRenderResultArchiver rejectingArchiver() {
        return (projectId, assetId, videoUrl) -> {
            throw new AssertionError("模拟任务不能访问供应商归档器");
        };
    }

    private static VideoRenderSimulator unavailableSimulator() {
        return new VideoRenderSimulator() {
            @Override
            public boolean available() {
                return false;
            }

            @Override
            public ArchivedVideoRender render(VideoRenderClaim claim) {
                throw new AssertionError("真实任务不能使用模拟器");
            }
        };
    }

    private static final class FakeRepository implements VideoEpisodeRenderRepository {
        final List<VideoEpisodeRenderClaim> claims = new ArrayList<>();
        CompletedEpisodeVideoTake completed;
        String submissionUnknown;
        String submissionRejected;
        String submissionRejectedCode;

        @Override
        public VideoAssetFile getProviderAssetFile(String assetId, String sha256) {
            throw new UnsupportedOperationException("该协调器测试不读取供应商参考素材");
        }

        @Override
        public List<VideoEpisodeRenderClaim> claimDue(int limit) {
            List<VideoEpisodeRenderClaim> result = List.copyOf(claims);
            claims.clear();
            return result;
        }

        @Override
        public void markSubmitted(String taskId, String providerTaskId) {}

        @Override
        public void markSubmissionUnknown(String taskId, String message) {
            submissionUnknown = taskId;
        }

        @Override
        public void markSubmissionRejected(String taskId, String code, String message) {
            submissionRejected = taskId;
            submissionRejectedCode = code;
        }

        @Override
        public void markQueryProgress(String taskId, String status) {}

        @Override
        public void markQueryError(String taskId, String message) {}

        @Override
        public boolean beginArchiving(String taskId) {
            return true;
        }

        @Override
        public void markProviderTerminal(
                String taskId, String status, String code, String message) {}

        @Override
        public boolean retryArchiving(String taskId, String message) {
            return true;
        }

        @Override
        public void completeTake(String taskId, CompletedEpisodeVideoTake take) {
            completed = take;
        }

        @Override
        public ObjectNode createTask(
                String userId,
                String episodeId,
                String baselineId,
                String shotId,
                JsonNode request,
                String executionMode,
                boolean referenceTransportConfigured) {
            throw new UnsupportedOperationException();
        }

        @Override
        public ObjectNode retryTask(
                String userId,
                String episodeId,
                String taskId,
                JsonNode request,
                String executionMode,
                boolean referenceTransportConfigured) {
            throw new UnsupportedOperationException();
        }

        @Override
        public ObjectNode getTask(String userId, String episodeId, String taskId) {
            throw new UnsupportedOperationException();
        }

        @Override
        public VideoAssetFile getTakeFile(String userId, String episodeId, String takeId) {
            throw new UnsupportedOperationException();
        }
    }

    private static final class FakeStorage implements VideoAssetStore {
        @Override
        public StoredVideoAsset save(
                String projectId,
                String assetId,
                String modality,
                org.springframework.web.multipart.MultipartFile upload) {
            throw new UnsupportedOperationException();
        }

        @Override
        public StoredVideoAsset saveStream(
                String projectId,
                String assetId,
                String modality,
                java.io.InputStream input,
                long maximumBytes) {
            throw new UnsupportedOperationException();
        }

        @Override
        public Path resolve(String storageKey) {
            return Path.of(storageKey);
        }

        @Override
        public boolean delete(String storageKey) {
            return true;
        }
    }
}
