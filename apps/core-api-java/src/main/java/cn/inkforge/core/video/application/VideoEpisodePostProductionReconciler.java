package cn.inkforge.core.video.application;

import cn.inkforge.core.platform.failure.TransientInfrastructureErrors;
import java.time.Duration;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** 单机串行执行独立分集 FFmpeg 导出；PostgreSQL 任务是唯一权威状态。 */
public final class VideoEpisodePostProductionReconciler {
    private static final Logger LOGGER =
            LoggerFactory.getLogger(VideoEpisodePostProductionReconciler.class);
    private static final Map<String, String> PUBLIC_MEDIA_ERRORS =
            Map.of(
                    "VIDEO_MEDIA_TOOLS_UNAVAILABLE", "当前环境缺少媒体处理工具",
                    "VIDEO_EXPORT_ASSET_MISSING", "导出引用的受控素材文件不存在",
                    "VIDEO_EXPORT_ASSET_HASH_MISMATCH", "导出引用的素材哈希已经变化",
                    "VIDEO_EXPORT_PLACEHOLDER_REMAINING", "粗剪仍包含无媒体片段",
                    "VIDEO_EXPORT_PROBE_FAILED", "无法读取某个 Take 的音轨信息");

    private final VideoEpisodePostProductionRepository repository;
    private final VideoPostProductionMediaProcessor media;
    private final VideoAssetStore storage;
    private final int batchSize;
    private final Duration interval;
    private final AtomicBoolean stop = new AtomicBoolean();

    public VideoEpisodePostProductionReconciler(
            VideoEpisodePostProductionRepository repository,
            VideoPostProductionMediaProcessor media,
            VideoAssetStore storage,
            int batchSize,
            Duration interval) {
        this.repository = Objects.requireNonNull(repository);
        this.media = Objects.requireNonNull(media);
        this.storage = Objects.requireNonNull(storage);
        if (batchSize < 1 || interval == null || interval.isZero() || interval.isNegative()) {
            throw new IllegalArgumentException("独立分集导出协调器配置无效");
        }
        this.batchSize = batchSize;
        this.interval = interval;
    }

    public int runOnce() {
        var claims = repository.claimDueExportTasks(batchSize);
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
                        "独立分集导出后台协调暂时失败 errorCode={}",
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
                    "独立分集媒体导出失败 taskId={} errorCode={}",
                    claim.taskId(),
                    exception.code());
            repository.failExport(
                    claim.taskId(),
                    exception.code(),
                    PUBLIC_MEDIA_ERRORS.getOrDefault(
                            exception.code(), "FFmpeg 无法处理当前素材编码或时间范围"));
            return;
        } catch (RuntimeException exception) {
            LOGGER.error(
                    "独立分集导出发生未预期错误 taskId={} errorCode={}",
                    claim.taskId(),
                    exception.getClass().getSimpleName());
            repository.failExport(
                    claim.taskId(),
                    "VIDEO_EPISODE_EXPORT_INTERNAL_ERROR",
                    "整集导出发生内部错误，请重试同一冻结输入");
            return;
        }
        try {
            repository.completeExport(
                    new CompletedEpisodeExport(
                            claim.taskId(),
                            assetId,
                            stored,
                            claim.manifest().totalDurationMs()));
        } catch (RuntimeException exception) {
            LOGGER.error(
                    "独立分集成片登记失败 taskId={} errorCode={}",
                    claim.taskId(),
                    exception.getClass().getSimpleName());
            boolean failed =
                    repository.failExport(
                            claim.taskId(),
                            "VIDEO_EPISODE_EXPORT_INTERNAL_ERROR",
                            "成片登记发生内部错误，请重试同一冻结输入");
            if (failed) storage.delete(stored.storageKey());
        }
    }
}
