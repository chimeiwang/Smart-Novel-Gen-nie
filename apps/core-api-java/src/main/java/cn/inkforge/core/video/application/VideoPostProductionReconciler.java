package cn.inkforge.core.video.application;

import cn.inkforge.core.platform.failure.TransientInfrastructureErrors;
import java.time.Duration;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** 单机串行执行整集 FFmpeg 导出，PostgreSQL 任务是唯一权威状态。 */
public final class VideoPostProductionReconciler {

    private static final Logger LOGGER =
            LoggerFactory.getLogger(VideoPostProductionReconciler.class);
    private static final Map<String, String> PUBLIC_MEDIA_ERRORS = Map.of(
            "VIDEO_MEDIA_TOOLS_UNAVAILABLE", "当前环境缺少媒体处理工具",
            "VIDEO_EXPORT_ASSET_MISSING", "导出引用的受控素材文件不存在",
            "VIDEO_EXPORT_ASSET_HASH_MISMATCH", "导出引用的素材哈希已经变化",
            "VIDEO_KEYFRAME_SOURCE_HASH_MISMATCH", "来源 Take 文件与冻结哈希不一致",
            "VIDEO_EXPORT_PLACEHOLDER_REMAINING", "粗剪仍包含占位镜头",
            "VIDEO_EXPORT_PROBE_FAILED", "无法读取某个 Take 的音轨信息");

    private final VideoPostProductionRepository repository;
    private final VideoPostProductionMediaProcessor media;
    private final VideoAssetStore storage;
    private final int batchSize;
    private final Duration interval;
    private final AtomicBoolean stop = new AtomicBoolean();

    public VideoPostProductionReconciler(
            VideoPostProductionRepository repository,
            VideoPostProductionMediaProcessor media,
            VideoAssetStore storage,
            int batchSize,
            Duration interval) {
        this.repository = Objects.requireNonNull(repository);
        this.media = Objects.requireNonNull(media);
        this.storage = Objects.requireNonNull(storage);
        if (batchSize < 1 || interval == null || interval.isZero() || interval.isNegative()) {
            throw new IllegalArgumentException("整集导出协调器配置无效");
        }
        this.batchSize = batchSize;
        this.interval = interval;
    }

    public int runOnce() {
        var claims = repository.claimDueExportTasks(batchSize);
        // 2 核部署默认串行 FFmpeg，避免与 Agent 模型任务争抢内存和 CPU。
        claims.forEach(this::process);
        return claims.size();
    }

    public void run() throws InterruptedException {
        while (!stop.get()) {
            try {
                runOnce();
            } catch (RuntimeException exception) {
                if (!TransientInfrastructureErrors.isTransient(exception)) throw exception;
                LOGGER.warn(
                        "整集导出后台协调暂时失败 errorCode={}",
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
    }

    private void process(EpisodeExportClaim claim) {
        String assetId = "export_" + claim.taskId();
        String staleStorageKey = claim.projectId() + "/" + assetId + ".mp4";
        storage.delete(staleStorageKey);
        StoredVideoAsset stored;
        try {
            stored = media.renderEpisode(claim.manifest(), storage, assetId);
        } catch (VideoMediaProcessingException exception) {
            LOGGER.warn(
                    "整集媒体导出失败 taskId={} errorCode={}",
                    claim.taskId(),
                    exception.code());
            repository.failExport(
                    claim.taskId(),
                    exception.code(),
                    PUBLIC_MEDIA_ERRORS.getOrDefault(
                            exception.code(),
                            "FFmpeg 无法处理当前素材编码或时间范围"));
            return;
        } catch (RuntimeException exception) {
            LOGGER.error(
                    "整集导出发生未预期错误 taskId={} errorCode={}",
                    claim.taskId(),
                    exception.getClass().getSimpleName());
            repository.failExport(
                    claim.taskId(),
                    "VIDEO_EPISODE_EXPORT_INTERNAL_ERROR",
                    "整集导出发生内部错误，请重试同一冻结输入");
            return;
        }
        try {
            repository.completeExport(new CompletedEpisodeExport(
                    claim.taskId(),
                    assetId,
                    stored,
                    claim.manifest().totalDurationMs()));
        } catch (RuntimeException exception) {
            LOGGER.error(
                    "整集成片登记发生未预期错误 taskId={} errorCode={}",
                    claim.taskId(),
                    exception.getClass().getSimpleName());
            boolean failed = repository.failExport(
                    claim.taskId(),
                    "VIDEO_EPISODE_EXPORT_INTERNAL_ERROR",
                    "整集成片登记发生内部错误，请重试同一冻结输入");
            if (failed) storage.delete(stored.storageKey());
        }
    }
}
