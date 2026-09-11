package cn.inkforge.core.video.application;

import cn.inkforge.contracts.agent.SeedanceRenderError;
import cn.inkforge.contracts.agent.SeedanceRenderOutput;
import cn.inkforge.contracts.agent.SeedanceRenderQueryRequest;
import cn.inkforge.contracts.agent.SeedanceRenderQueryResponse;
import cn.inkforge.contracts.agent.SeedanceRenderSubmitRequest;
import cn.inkforge.contracts.agent.SeedanceRenderSubmitResponse;
import cn.inkforge.contracts.agent.SeedanceRuntimeReference;
import cn.inkforge.core.platform.failure.TransientInfrastructureErrors;
import java.net.URI;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Supplier;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** PostgreSQL 权威的独立剧集 Seedance 短提交、短查询和受控归档循环。 */
public final class VideoEpisodeRenderReconciler implements AutoCloseable {

    private static final Logger LOGGER =
            LoggerFactory.getLogger(VideoEpisodeRenderReconciler.class);

    private final VideoEpisodeRenderRepository repository;
    private final Supplier<VideoRenderGateway> gateways;
    private final VideoRenderResultArchiver archiver;
    private final VideoRenderSimulator simulator;
    private final VideoAssetStore storage;
    private final URI providerMediaBaseUrl;
    private final ProviderAssetTokenCodec providerAssetTokens;
    private final int batchSize;
    private final Duration interval;
    private final ExecutorService workers;
    private final AtomicBoolean stop = new AtomicBoolean();

    public VideoEpisodeRenderReconciler(
            VideoEpisodeRenderRepository repository,
            Supplier<VideoRenderGateway> gateways,
            VideoRenderResultArchiver archiver,
            VideoRenderSimulator simulator,
            VideoAssetStore storage,
            URI providerMediaBaseUrl,
            ProviderAssetTokenCodec providerAssetTokens,
            int batchSize,
            Duration interval) {
        this.repository = Objects.requireNonNull(repository);
        this.gateways = Objects.requireNonNull(gateways);
        this.archiver = Objects.requireNonNull(archiver);
        this.simulator = Objects.requireNonNull(simulator);
        this.storage = Objects.requireNonNull(storage);
        this.providerMediaBaseUrl = providerMediaBaseUrl;
        this.providerAssetTokens = providerAssetTokens;
        if (batchSize < 1 || interval == null || interval.isZero() || interval.isNegative()) {
            throw new IllegalArgumentException("独立剧集逐镜协调器配置无效");
        }
        this.batchSize = batchSize;
        this.interval = interval;
        this.workers = Executors.newFixedThreadPool(
                batchSize,
                Thread.ofPlatform()
                        .daemon(true)
                        .name("video-episode-render-worker-", 0)
                        .factory());
    }

    /** 领取一批 episode-native 任务；每条任务本轮只执行 submit 或 query。 */
    public int runOnce() {
        VideoRenderGateway gateway = gateways.get();
        if (gateway == null) return 0;
        List<VideoEpisodeRenderClaim> claims = repository.claimDue(batchSize);
        List<CompletableFuture<Void>> operations = claims.stream()
                .map(claim -> CompletableFuture.runAsync(() -> process(claim, gateway), workers))
                .toList();
        try {
            CompletableFuture.allOf(operations.toArray(CompletableFuture[]::new)).join();
        } catch (CompletionException exception) {
            Throwable cause = exception.getCause();
            if (cause instanceof RuntimeException runtime) throw runtime;
            throw exception;
        }
        return claims.size();
    }

    public void run() throws InterruptedException {
        while (!stop.get()) {
            try {
                runOnce();
            } catch (RuntimeException exception) {
                if (!TransientInfrastructureErrors.isTransient(exception)) throw exception;
                LOGGER.warn(
                        "独立剧集逐镜后台协调暂时失败 errorCode={}",
                        exception.getClass().getSimpleName());
            }
            synchronized (stop) {
                if (!stop.get()) stop.wait(interval.toMillis());
            }
        }
    }

    public void requestStop() {
        stop.set(true);
        synchronized (stop) {
            stop.notifyAll();
        }
        workers.shutdownNow();
    }

    @Override
    public void close() {
        requestStop();
    }

    private void process(VideoEpisodeRenderClaim claim, VideoRenderGateway gateway) {
        if (claim.submission()) submit(claim, gateway);
        else query(claim, gateway);
    }

    /** 创建结果未知时只收敛原任务，绝不在协调循环中再次 POST。 */
    private void submit(VideoEpisodeRenderClaim claim, VideoRenderGateway gateway) {
        SeedanceRenderSubmitRequest request;
        try {
            VideoEpisodeRenderInput input = claim.input();
            request = new SeedanceRenderSubmitRequest()
                    .durationSeconds(input.durationSeconds())
                    .generateAudio(input.generateAudio())
                    .generationMode("reference")
                    .inputHash(claim.inputHash())
                    .model(input.model())
                    .novelId(claim.novelId())
                    .promptText(input.prompt())
                    .ratio(SeedanceRenderSubmitRequest.RatioEnum.fromValue(input.ratio()))
                    .resolution(input.resolution())
                    .taskId(claim.taskId())
                    .watermark(input.watermark())
                    .executionMode(SeedanceRenderSubmitRequest.ExecutionModeEnum.fromValue(
                            input.executionMode()));
            request.setReferences(runtimeReferences(claim));
        } catch (RuntimeException exception) {
            repository.markSubmissionRejected(
                    claim.taskId(), "SEEDANCE_SUBMIT_INPUT_INVALID", safeMessage(exception));
            return;
        }

        String providerTaskId;
        try {
            SeedanceRenderSubmitResponse response = gateway.submit(request);
            providerTaskId = response == null ? null : response.getProviderTaskId();
            if (providerTaskId == null || providerTaskId.isBlank()) {
                repository.markSubmissionUnknown(
                        claim.taskId(),
                        "Seedance 创建响应缺少任务标识；未自动重提，以免重复计费");
                return;
            }
        } catch (VideoRenderSubmissionRejectedException exception) {
            repository.markSubmissionRejected(
                    claim.taskId(), "SEEDANCE_SUBMIT_REJECTED", safeMessage(exception));
            return;
        } catch (VideoRenderSubmissionUnknownException exception) {
            repository.markSubmissionUnknown(
                    claim.taskId(),
                    "Seedance 创建请求返回前连接中断；未自动重提，以免重复计费");
            return;
        } catch (RuntimeException exception) {
            // gateway 已进入可能发出 POST 的边界，未分类异常不能按普通失败重试。
            repository.markSubmissionUnknown(
                    claim.taskId(),
                    "Seedance 创建结果无法确认；未自动重提，以免重复计费");
            return;
        }
        repository.markSubmitted(claim.taskId(), providerTaskId);
    }

    private void query(VideoEpisodeRenderClaim claim, VideoRenderGateway gateway) {
        if (claim.providerTaskId() == null) {
            repository.markProviderTerminal(
                    claim.taskId(),
                    "failed",
                    "SEEDANCE_PROVIDER_TASK_ID_MISSING",
                    "耐久任务缺少供应商任务标识");
            return;
        }
        SeedanceRenderQueryResponse response;
        try {
            response = gateway.query(new SeedanceRenderQueryRequest()
                    .executionMode(SeedanceRenderQueryRequest.ExecutionModeEnum.fromValue(
                            claim.input().executionMode()))
                    .novelId(claim.novelId())
                    .pollCount(Math.max(claim.pollCount(), 1))
                    .providerTaskId(claim.providerTaskId())
                    .taskId(claim.taskId()));
        } catch (VideoRenderQueryException exception) {
            repository.markQueryError(
                    claim.taskId(), "Seedance 状态查询暂时失败，稍后继续查询同一任务");
            return;
        }
        String status = response.getStatus().getValue();
        if ("queued".equals(status) || "running".equals(status)) {
            repository.markQueryProgress(claim.taskId(), status);
            return;
        }
        if ("failed".equals(status) || "expired".equals(status) || "cancelled".equals(status)) {
            SeedanceRenderError error = response.getError();
            repository.markProviderTerminal(
                    claim.taskId(),
                    status,
                    error == null ? "SEEDANCE_" + status.toUpperCase() : error.getCode(),
                    error == null ? "Seedance 任务状态为 " + status : error.getMessage());
            return;
        }
        SeedanceRenderOutput output = response.getOutput();
        if (output == null || output.getMediaKind() == null) {
            repository.markQueryError(claim.taskId(), "Seedance 成功响应缺少完整媒体来源事实");
            return;
        }
        if (!repository.beginArchiving(claim.taskId())) return;
        archive(claim, output);
    }

    private void archive(VideoEpisodeRenderClaim claim, SeedanceRenderOutput output) {
        String frameAssetId = claim.taskId() + "-last-frame";
        clearStaleFiles(claim.projectId(), claim.taskId(), frameAssetId);
        ArchivedVideoRender video = null;
        ArchivedVideoFrame frame = null;
        try {
            String mode = claim.input().executionMode();
            String mediaKind = output.getMediaKind().getValue();
            Map<String, Object> usage = output.getUsage() == null
                    ? Map.of()
                    : new LinkedHashMap<>(output.getUsage());
            if ("simulated".equals(mode)) {
                if (!"simulated_placeholder".equals(mediaKind)
                        || !usage.isEmpty()
                        || output.getLastFrameUrl() != null
                        || !("simulated-" + claim.taskId()).equals(claim.providerTaskId())
                        || !("inkforge-simulated://" + claim.taskId())
                                .equals(output.getVideoUrl())) {
                    throw new IllegalArgumentException("模拟结果与冻结任务身份不匹配");
                }
                video = simulator.render(claim);
            } else {
                if (!"provider_media".equals(mediaKind)) {
                    throw new IllegalArgumentException("真实任务未返回 provider_media");
                }
                video = archiver.archive(
                        claim.projectId(), claim.taskId(), output.getVideoUrl());
                if (output.getLastFrameUrl() != null) {
                    frame = archiver.archiveImage(
                            claim.projectId(), frameAssetId, output.getLastFrameUrl());
                }
            }
            Map<String, Object> metadata = providerMetadata(output, mode, mediaKind, usage, frame);
            repository.completeTake(
                    claim.taskId(),
                    new CompletedEpisodeVideoTake(
                            video.assetId(), video.stored(), metadata, video.durationMs(), frame));
        } catch (RuntimeException exception) {
            boolean recovering = repository.retryArchiving(
                    claim.taskId(),
                    "Seedance 结果归档失败：" + exception.getClass().getSimpleName());
            if (recovering) {
                if (video != null) storage.delete(video.stored().storageKey());
                if (frame != null) storage.delete(frame.stored().storageKey());
                clearStaleFiles(claim.projectId(), claim.taskId(), frameAssetId);
            }
        }
    }

    private List<SeedanceRuntimeReference> runtimeReferences(VideoEpisodeRenderClaim claim) {
        boolean simulated = "simulated".equals(claim.input().executionMode());
        if (!simulated && (providerMediaBaseUrl == null || providerAssetTokens == null)) {
            throw new IllegalArgumentException("VIDEO_RENDER_REFERENCE_TRANSPORT_NOT_CONFIGURED");
        }
        List<SeedanceRuntimeReference> result = new ArrayList<>();
        int ordinal = 1;
        ordinal = addKeyframes(
                result, claim, simulated, "initial_state", ordinal);
        for (VideoEpisodeRenderReference reference : claim.input().references()) {
            result.add(new SeedanceRuntimeReference(
                            reference.assetId(),
                            reference.mimeType(),
                            ordinal++,
                            providerReferenceUrl(
                                    simulated, reference.assetId(), reference.sha256()))
                    .usageRole(SeedanceRuntimeReference.UsageRoleEnum.VISUAL_REFERENCE));
        }
        ordinal = addKeyframes(
                result, claim, simulated, "transition_anchor", ordinal);
        addKeyframes(result, claim, simulated, "end_state", ordinal);
        return List.copyOf(result);
    }

    private int addKeyframes(
            List<SeedanceRuntimeReference> result,
            VideoEpisodeRenderClaim claim,
            boolean simulated,
            String role,
            int ordinal) {
        for (VideoEpisodeRenderKeyframe keyframe : claim.input().keyframes()) {
            if (!role.equals(keyframe.role())) continue;
            result.add(new SeedanceRuntimeReference(
                            keyframe.assetId(),
                            keyframe.mimeType(),
                            ordinal++,
                            providerReferenceUrl(
                                    simulated, keyframe.assetId(), keyframe.sha256()))
                    .usageRole(SeedanceRuntimeReference.UsageRoleEnum.fromValue(role)));
        }
        return ordinal;
    }

    private String providerReferenceUrl(boolean simulated, String assetId, String sha256) {
        return simulated
                ? "urn:inkforge:simulated-asset:" + assetId
                : providerMediaBaseUrl
                        + "/api/v1/video/provider-assets/"
                        + providerAssetTokens.encode(assetId, sha256);
    }

    private static Map<String, Object> providerMetadata(
            SeedanceRenderOutput output,
            String executionMode,
            String mediaKind,
            Map<String, Object> usage,
            ArchivedVideoFrame frame) {
        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("mediaKind", mediaKind);
        metadata.put("executionMode", executionMode);
        metadata.put("simulated", "simulated".equals(executionMode));
        metadata.put("durationSeconds", output.getDurationSeconds());
        metadata.put("framesPerSecond", output.getFramesPerSecond());
        metadata.put("generateAudio", output.getGenerateAudio());
        metadata.put("ratio", output.getRatio());
        metadata.put("resolution", output.getResolution());
        metadata.put("usage", new LinkedHashMap<>(usage));
        if (frame == null) {
            metadata.put("lastFrame", null);
        } else {
            metadata.put(
                    "lastFrame",
                    Map.of(
                            "assetId", frame.assetId(),
                            "sha256", frame.stored().sha256(),
                            "mimeType", frame.stored().mimeType(),
                            "byteSize", frame.stored().byteSize()));
        }
        return metadata;
    }

    private void clearStaleFiles(String projectId, String taskId, String frameAssetId) {
        storage.delete(projectId + "/" + taskId + ".mp4");
        storage.delete(projectId + "/" + frameAssetId + ".jpg");
        storage.delete(projectId + "/" + frameAssetId + ".png");
        storage.delete(projectId + "/" + frameAssetId + ".webp");
    }

    private static String safeMessage(RuntimeException exception) {
        return exception.getMessage() == null || exception.getMessage().isBlank()
                ? exception.getClass().getSimpleName()
                : exception.getMessage();
    }
}
