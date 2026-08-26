package cn.inkforge.core.video.application;

import cn.inkforge.contracts.agent.SeedanceRenderError;
import cn.inkforge.contracts.agent.SeedanceRenderOutput;
import cn.inkforge.contracts.agent.SeedanceRenderQueryRequest;
import cn.inkforge.contracts.agent.SeedanceRenderQueryResponse;
import cn.inkforge.contracts.agent.SeedanceRenderSubmitRequest;
import cn.inkforge.contracts.agent.SeedanceRuntimeReference;
import cn.inkforge.contracts.api.ShotRenderKeyframeManifest;
import cn.inkforge.contracts.api.ShotRenderReferenceManifest;
import cn.inkforge.contracts.api.VideoShotRenderManifest;
import cn.inkforge.core.platform.failure.TransientInfrastructureErrors;
import java.math.RoundingMode;
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
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** PostgreSQL 权威的 Seedance 短提交、短查询与结果归档协调器。 */
public final class VideoRenderReconciler implements AutoCloseable {

    private static final Logger LOGGER = LoggerFactory.getLogger(VideoRenderReconciler.class);

    private final VideoRenderRepository repository;
    private final VideoRenderGateway gateway;
    private final VideoRenderResultArchiver archiver;
    private final VideoAssetStore storage;
    private final URI providerMediaBaseUrl;
    private final ProviderAssetTokenCodec providerAssetTokens;
    private final int batchSize;
    private final Duration interval;
    private final ExecutorService workers;
    private final AtomicBoolean stop = new AtomicBoolean();

    public VideoRenderReconciler(
            VideoRenderRepository repository,
            VideoRenderGateway gateway,
            VideoRenderResultArchiver archiver,
            VideoAssetStore storage,
            URI providerMediaBaseUrl,
            ProviderAssetTokenCodec providerAssetTokens,
            int batchSize,
            Duration interval) {
        this.repository = Objects.requireNonNull(repository);
        this.gateway = Objects.requireNonNull(gateway);
        this.archiver = Objects.requireNonNull(archiver);
        this.storage = Objects.requireNonNull(storage);
        this.providerMediaBaseUrl = providerMediaBaseUrl;
        this.providerAssetTokens = providerAssetTokens;
        if (batchSize < 1 || interval == null || interval.isZero() || interval.isNegative()) {
            throw new IllegalArgumentException("逐镜视频任务协调器配置无效");
        }
        this.batchSize = batchSize;
        this.interval = interval;
        this.workers = Executors.newFixedThreadPool(
                batchSize,
                Thread.ofPlatform().daemon(true).name("video-render-worker-", 0).factory());
    }

    public int runOnce() {
        List<VideoRenderClaim> claims = repository.claimDue(batchSize);
        List<CompletableFuture<Void>> operations = claims.stream()
                .map(claim -> CompletableFuture.runAsync(() -> process(claim), workers))
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
                        "逐镜视频任务后台协调暂时失败 errorCode={}",
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

    private void process(VideoRenderClaim claim) {
        if (claim.submission()) {
            submit(claim);
        } else {
            query(claim);
        }
    }

    private void submit(VideoRenderClaim claim) {
        String providerTaskId;
        try {
            VideoShotRenderManifest manifest = claim.manifest();
            String prompt = manifest.getProviderPromptText() == null
                    ? manifest.getPromptText()
                    : manifest.getProviderPromptText();
            SeedanceRenderSubmitRequest request = new SeedanceRenderSubmitRequest(
                    manifest.getDurationSeconds(),
                    manifest.getGenerateAudio(),
                    claim.inputHash(),
                    manifest.getModel(),
                    claim.novelId(),
                    prompt,
                    SeedanceRenderSubmitRequest.RatioEnum.fromValue(
                            manifest.getRatio().getValue()),
                    SeedanceRenderSubmitRequest.ResolutionEnum.fromValue(
                            manifest.getResolution().getValue()),
                    claim.taskId(),
                    manifest.getWatermark());
            request.setReferences(runtimeReferences(claim));
            providerTaskId = gateway.submit(request).getProviderTaskId();
        } catch (VideoRenderSubmissionUnknownException exception) {
            repository.markSubmissionUnknown(
                    claim.taskId(),
                    "Seedance 创建请求返回前连接中断；未自动重提，以免重复计费");
            return;
        } catch (VideoRenderSubmissionRejectedException exception) {
            repository.markSubmissionRejected(
                    claim.taskId(), "SEEDANCE_SUBMIT_REJECTED", exception.getMessage());
            return;
        } catch (RuntimeException exception) {
            repository.markSubmissionRejected(
                    claim.taskId(),
                    "SEEDANCE_SUBMIT_INPUT_INVALID",
                    message(exception));
            return;
        }
        // 供应商已经明确返回 taskId 后，数据库写失败不能被误判为“未送达”。陈旧
        // submitting 租约会进入 submission_unknown，阻止可能重复计费的自动重提。
        repository.markSubmitted(claim.taskId(), providerTaskId);
    }

    private void query(VideoRenderClaim claim) {
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
            response = gateway.query(new SeedanceRenderQueryRequest(
                    claim.novelId(),
                    Math.max(claim.pollCount(), 1),
                    claim.providerTaskId(),
                    claim.taskId()));
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
        if ("failed".equals(status)
                || "expired".equals(status)
                || "cancelled".equals(status)) {
            SeedanceRenderError error = response.getError();
            repository.markProviderTerminal(
                    claim.taskId(),
                    status,
                    error == null ? "SEEDANCE_" + status.toUpperCase() : error.getCode(),
                    error == null
                            ? "Seedance 任务状态为 " + status
                            : error.getMessage());
            return;
        }
        SeedanceRenderOutput output = response.getOutput();
        if (output == null) {
            repository.markQueryError(claim.taskId(), "Seedance 成功响应缺少视频结果");
            return;
        }
        if (!repository.beginArchiving(claim.taskId())) return;
        String assetId = claim.taskId();
        String staleStorageKey = claim.projectId() + "/" + assetId + ".mp4";
        storage.delete(staleStorageKey);
        try {
            ArchivedVideoRender archived =
                    archiver.archive(claim.projectId(), assetId, output.getVideoUrl());
            repository.completeTake(
                    claim.taskId(),
                    new CompletedVideoTake(
                            archived.assetId(),
                            archived.stored(),
                            providerMetadata(output),
                            durationMs(output, claim.manifest())));
        } catch (RuntimeException exception) {
            boolean failed = repository.failArchiving(
                    claim.taskId(),
                    "Seedance 结果归档失败：" + exception.getClass().getSimpleName());
            if (failed) storage.delete(staleStorageKey);
        }
    }

    private List<SeedanceRuntimeReference> runtimeReferences(VideoRenderClaim claim) {
        List<ShotRenderReferenceManifest> references = list(claim.manifest().getReferences());
        List<ShotRenderKeyframeManifest> keyframes = list(claim.manifest().getKeyframes());
        if (references.isEmpty() && keyframes.isEmpty()) return List.of();
        if (providerMediaBaseUrl == null || providerAssetTokens == null) {
            throw new IllegalArgumentException("VIDEO_RENDER_REFERENCE_TRANSPORT_NOT_CONFIGURED");
        }
        Map<ShotRenderKeyframeManifest.RoleEnum, ShotRenderKeyframeManifest> byRole =
                new LinkedHashMap<>();
        keyframes.forEach(frame -> byRole.put(frame.getRole(), frame));
        List<RuntimeReferenceSource> ordered = new ArrayList<>();
        addKeyframe(
                ordered,
                byRole.get(ShotRenderKeyframeManifest.RoleEnum.INITIAL_STATE),
                "initial_state");
        references.forEach(reference -> ordered.add(new RuntimeReferenceSource(
                reference.getAssetId(),
                reference.getSha256(),
                reference.getMimeType(),
                "visual_reference")));
        addKeyframe(
                ordered,
                byRole.get(ShotRenderKeyframeManifest.RoleEnum.TRANSITION_ANCHOR),
                "transition_anchor");
        addKeyframe(
                ordered,
                byRole.get(ShotRenderKeyframeManifest.RoleEnum.END_STATE),
                "end_state");
        List<SeedanceRuntimeReference> result = new ArrayList<>(ordered.size());
        for (int index = 0; index < ordered.size(); index++) {
            RuntimeReferenceSource source = ordered.get(index);
            String url = providerMediaBaseUrl
                    + "/api/v1/video/provider-assets/"
                    + providerAssetTokens.encode(source.assetId(), source.sha256());
            result.add(new SeedanceRuntimeReference(
                            source.assetId(), source.mimeType(), index + 1, url)
                    .usageRole(SeedanceRuntimeReference.UsageRoleEnum.fromValue(
                            source.usageRole())));
        }
        return List.copyOf(result);
    }

    private static void addKeyframe(
            List<RuntimeReferenceSource> target,
            ShotRenderKeyframeManifest frame,
            String role) {
        if (frame == null) return;
        target.add(new RuntimeReferenceSource(
                frame.getAssetId(), frame.getSha256(), frame.getMimeType(), role));
    }

    private static Map<String, Object> providerMetadata(SeedanceRenderOutput output) {
        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("durationSeconds", output.getDurationSeconds());
        metadata.put("framesPerSecond", output.getFramesPerSecond());
        metadata.put("generateAudio", output.getGenerateAudio());
        metadata.put("ratio", output.getRatio());
        metadata.put("resolution", output.getResolution());
        metadata.put("usage", output.getUsage());
        return metadata;
    }

    private static int durationMs(
            SeedanceRenderOutput output, VideoShotRenderManifest manifest) {
        if (output.getDurationSeconds() == null) {
            return Math.multiplyExact(manifest.getDurationSeconds(), 1_000);
        }
        return output.getDurationSeconds()
                .movePointRight(3)
                .setScale(0, RoundingMode.HALF_EVEN)
                .intValueExact();
    }

    private static String message(RuntimeException exception) {
        return exception.getMessage() == null || exception.getMessage().isBlank()
                ? exception.getClass().getSimpleName()
                : exception.getMessage();
    }

    private static <T> List<T> list(List<T> value) {
        return value == null ? List.of() : value;
    }

    private record RuntimeReferenceSource(
            String assetId, String sha256, String mimeType, String usageRole) {}
}
