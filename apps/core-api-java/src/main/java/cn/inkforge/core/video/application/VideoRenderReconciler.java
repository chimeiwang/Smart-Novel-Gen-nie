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

/** PostgreSQL 权威的 Seedance 短提交、短查询与结果归档协调器。 */
public final class VideoRenderReconciler implements AutoCloseable {

    private static final Logger LOGGER = LoggerFactory.getLogger(VideoRenderReconciler.class);

    private final VideoRenderRepository repository;
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

    public VideoRenderReconciler(
            VideoRenderRepository repository,
            VideoRenderGateway gateway,
            VideoRenderResultArchiver archiver,
            VideoRenderSimulator simulator,
            VideoAssetStore storage,
            URI providerMediaBaseUrl,
            ProviderAssetTokenCodec providerAssetTokens,
            int batchSize,
            Duration interval) {
        this(repository, () -> gateway, archiver, simulator, storage, providerMediaBaseUrl,
                providerAssetTokens, batchSize, interval);
    }

    public VideoRenderReconciler(
            VideoRenderRepository repository, Supplier<VideoRenderGateway> gateways,
            VideoRenderResultArchiver archiver, VideoRenderSimulator simulator, VideoAssetStore storage,
            URI providerMediaBaseUrl, ProviderAssetTokenCodec providerAssetTokens, int batchSize, Duration interval) {
        this.repository = Objects.requireNonNull(repository);
        this.gateways = Objects.requireNonNull(gateways);
        this.archiver = Objects.requireNonNull(archiver);
        this.simulator = Objects.requireNonNull(simulator);
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

    /** 领取一批到期任务并并行推进一次提交、查询或归档。 */
    public int runOnce() {
        VideoRenderGateway gateway = gateways.get();
        if (gateway == null) return 0;
        List<VideoRenderClaim> claims = repository.claimDue(batchSize);
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

    private void process(VideoRenderClaim claim, VideoRenderGateway gateway) {
        try {
            executionMode(claim);
        } catch (IllegalArgumentException exception) {
            // 旧任务未冻结执行模式时失败关闭，绝不能默认成可能计费的 live 调用。
            if (claim.submission()) {
                repository.markSubmissionRejected(claim.taskId(), "VIDEO_RENDER_PROFILE_UNSUPPORTED",
                        "旧任务未冻结执行模式，不能推断为模拟或真实调用");
            } else {
                repository.markProviderTerminal(claim.taskId(), "failed", "VIDEO_RENDER_PROFILE_UNSUPPORTED",
                        "旧任务未冻结执行模式，请核查原任务");
            }
            return;
        }
        if (claim.submission()) {
            submit(claim, gateway);
        } else {
            query(claim, gateway);
        }
    }

    /** 提交一次冻结请求，并区分明确拒绝与结果未知，防止未知提交被自动重试。 */
    private void submit(VideoRenderClaim claim, VideoRenderGateway gateway) {
        String providerTaskId;
        try {
            VideoShotRenderManifest manifest = claim.manifest();
            String prompt = manifest.getProviderPromptText() == null
                    ? manifest.getPromptText()
                    : manifest.getProviderPromptText();
            SeedanceRenderSubmitRequest request = new SeedanceRenderSubmitRequest()
                    .durationSeconds(manifest.getDurationSeconds()).generateAudio(manifest.getGenerateAudio())
                    .inputHash(claim.inputHash()).model(manifest.getModel()).novelId(claim.novelId())
                    .promptText(prompt).taskId(claim.taskId()).watermark(manifest.getWatermark())
                    .ratio(SeedanceRenderSubmitRequest.RatioEnum.fromValue(manifest.getRatio().getValue()))
                    .resolution(manifest.getResolution().getValue())
                    .generationMode("reference")
                    .executionMode(SeedanceRenderSubmitRequest.ExecutionModeEnum.fromValue(executionMode(claim)));
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

    /** 查询同一供应商任务；成功后取得归档租约并落为不可变 Take。 */
    private void query(VideoRenderClaim claim, VideoRenderGateway gateway) {
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
                    .novelId(claim.novelId()).pollCount(Math.max(claim.pollCount(), 1))
                    .providerTaskId(claim.providerTaskId()).taskId(claim.taskId())
                    .executionMode(SeedanceRenderQueryRequest.ExecutionModeEnum.fromValue(executionMode(claim))));
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
        if (output == null || output.getMediaKind() == null) {
            repository.markQueryError(claim.taskId(), "Seedance 成功响应缺少完整媒体来源事实");
            return;
        }
        // 只有归档租约持有者可以下载和登记 Take，避免多 worker 重复保存同一结果。
        if (!repository.beginArchiving(claim.taskId())) return;
        String assetId = claim.taskId();
        String frameAssetId = claim.taskId() + "-last-frame";
        String staleStorageKey = claim.projectId() + "/" + assetId + ".mp4";
        ArchivedVideoFrame frame = null;
        try {
            if (!storage.delete(staleStorageKey)) {
                throw new IllegalStateException("VIDEO_RENDER_STALE_FILE_CLEANUP_FAILED");
            }
            ArchivedVideoRender archived;
            String mediaKind = output.getMediaKind().getValue();
            if ("simulated".equals(executionMode(claim))) {
                if (!"simulated_placeholder".equals(mediaKind)
                        || (output.getUsage() != null && !output.getUsage().isEmpty())
                        || output.getLastFrameUrl() != null
                        || !("simulated-" + claim.taskId()).equals(claim.providerTaskId())
                        || !("inkforge-simulated://" + claim.taskId()).equals(output.getVideoUrl())) {
                    throw new IllegalArgumentException("模拟供应商结果与冻结任务不匹配");
                }
                archived = simulator.render(claim);
            } else {
                if (!"provider_media".equals(mediaKind)) {
                    throw new IllegalArgumentException("真实任务未返回 provider_media");
                }
                archived = archiver.archive(claim.projectId(), assetId, output.getVideoUrl());
                if (output.getLastFrameUrl() != null) {
                    frame = archiver.archiveImage(
                            claim.projectId(), frameAssetId, output.getLastFrameUrl());
                }
            }
            Map<String, Object> metadata = providerMetadata(output, mediaKind, frame);
            metadata.put("executionMode", executionMode(claim));
            metadata.put("simulated", "simulated".equals(executionMode(claim)));
            repository.completeTake(
                    claim.taskId(),
                    new CompletedVideoTake(
                            archived.assetId(),
                            archived.stored(),
                            metadata,
                            archived.durationMs(),
                            frame));
        } catch (RuntimeException exception) {
            boolean recovering = repository.retryArchiving(
                    claim.taskId(),
                    "Seedance 结果归档失败：" + exception.getClass().getSimpleName());
            if (recovering) {
                storage.delete(staleStorageKey);
                if (frame != null) storage.delete(frame.stored().storageKey());
                storage.delete(claim.projectId() + "/" + frameAssetId + ".jpg");
                storage.delete(claim.projectId() + "/" + frameAssetId + ".png");
                storage.delete(claim.projectId() + "/" + frameAssetId + ".webp");
            }
        }
    }

    /** 按首帧、设定参考、过渡帧、尾帧的固定顺序生成供应商图片输入。 */
    private List<SeedanceRuntimeReference> runtimeReferences(VideoRenderClaim claim) {
        List<ShotRenderReferenceManifest> references = list(claim.manifest().getReferences());
        List<ShotRenderKeyframeManifest> keyframes = list(claim.manifest().getKeyframes());
        if (references.isEmpty() && keyframes.isEmpty()) return List.of();
        boolean simulated = "simulated".equals(executionMode(claim));
        if (!simulated && (providerMediaBaseUrl == null || providerAssetTokens == null)) {
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
            String url = simulated ? "urn:inkforge:simulated-asset:" + source.assetId()
                    : providerMediaBaseUrl + "/api/v1/video/provider-assets/"
                            + providerAssetTokens.encode(source.assetId(), source.sha256());
            result.add(new SeedanceRuntimeReference(
                            source.assetId(), source.mimeType(), index + 1, url)
                    .usageRole(SeedanceRuntimeReference.UsageRoleEnum.fromValue(
                            source.usageRole())));
        }
        return List.copyOf(result);
    }

    private static String executionMode(VideoRenderClaim claim) {
        if (claim.manifest().getExecutionMode() == null) {
            throw new IllegalArgumentException("视频任务缺少冻结执行模式，不能推断为真实调用");
        }
        return claim.manifest().getExecutionMode().getValue();
    }

    private static void addKeyframe(
            List<RuntimeReferenceSource> target,
            ShotRenderKeyframeManifest frame,
            String role) {
        if (frame == null) return;
        target.add(new RuntimeReferenceSource(
                frame.getAssetId(), frame.getSha256(), frame.getMimeType(), role));
    }

    private static Map<String, Object> providerMetadata(
            SeedanceRenderOutput output, String mediaKind, ArchivedVideoFrame frame) {
        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("mediaKind", mediaKind);
        metadata.put("durationSeconds", output.getDurationSeconds());
        metadata.put("framesPerSecond", output.getFramesPerSecond());
        metadata.put("generateAudio", output.getGenerateAudio());
        metadata.put("ratio", output.getRatio());
        metadata.put("resolution", output.getResolution());
        metadata.put("usage", output.getUsage());
        metadata.put(
                "lastFrame",
                frame == null
                        ? null
                        : Map.of(
                                "assetId", frame.assetId(),
                                "sha256", frame.stored().sha256(),
                                "mimeType", frame.stored().mimeType(),
                                "byteSize", frame.stored().byteSize()));
        return metadata;
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
