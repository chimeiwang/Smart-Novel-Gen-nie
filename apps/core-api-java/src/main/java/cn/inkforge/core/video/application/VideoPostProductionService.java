package cn.inkforge.core.video.application;

import cn.inkforge.contracts.api.ChapterPostProductionWorkspaceResponse;
import cn.inkforge.contracts.api.EpisodeEditHeadResponse;
import cn.inkforge.contracts.api.EpisodeEditVersionResponse;
import cn.inkforge.contracts.api.EpisodeExportTaskResponse;
import cn.inkforge.contracts.api.EpisodeMixHeadResponse;
import cn.inkforge.contracts.api.EpisodeMixVersionResponse;
import cn.inkforge.contracts.api.ExtractTakeFrameRequest;
import cn.inkforge.contracts.api.PostProductionAssetResponse;
import cn.inkforge.contracts.api.PostProductionReadinessResponse;
import cn.inkforge.contracts.api.RetryEpisodeExportRequest;
import cn.inkforge.contracts.api.SaveEpisodeEditVersionRequest;
import cn.inkforge.contracts.api.SaveEpisodeMixVersionRequest;
import cn.inkforge.contracts.api.SaveShotKeyframeVersionRequest;
import cn.inkforge.contracts.api.ShotKeyframeHeadResponse;
import cn.inkforge.contracts.api.StartEpisodeExportRequest;
import cn.inkforge.core.platform.http.ApiException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.locks.ReentrantLock;

/**
 * 章节影视化 P1–P3 公共用例与媒体能力门禁。
 *
 * <p>FFmpeg/文件系统操作不能加入数据库事务，因此抽帧采用“确定性文件标识 → 登记来源事实 →
 * 不确定结果回读 → 精确补偿”的顺序。这里的进程内锁只减少同实例重复工作，跨实例幂等仍以数据库命令锁为准。
 */
public final class VideoPostProductionService {

    private final VideoPostProductionRepository repository;
    private final VideoAssetStore storage;
    private final VideoPostProductionMediaProcessor media;
    private final ConcurrentHashMap<String, ReentrantLock> extractionLocks =
            new ConcurrentHashMap<>();

    public VideoPostProductionService(
            VideoPostProductionRepository repository,
            VideoAssetStore storage,
            VideoPostProductionMediaProcessor media) {
        this.repository = Objects.requireNonNull(repository);
        this.storage = Objects.requireNonNull(storage);
        this.media = Objects.requireNonNull(media);
    }

    public PostProductionReadinessResponse readiness() {
        MediaToolReadiness tools = media.readiness();
        var blockers = new ArrayList<String>();
        if (!tools.ffmpegAvailable()) blockers.add("当前环境缺少 ffmpeg，不能抽帧或导出");
        if (!tools.ffprobeAvailable()) blockers.add("当前环境缺少 ffprobe，不能检查 Take 音轨");
        return new PostProductionReadinessResponse(
                java.util.List.copyOf(blockers),
                tools.ffmpegAvailable(),
                tools.ffprobeAvailable());
    }

    public ChapterPostProductionWorkspaceResponse getWorkspace(
            String userId, String adaptationId) {
        return repository.getWorkspace(userId, adaptationId, readiness());
    }

    public ShotKeyframeHeadResponse saveKeyframe(
            String userId,
            String adaptationId,
            String shotId,
            SaveShotKeyframeVersionRequest request) {
        return repository.saveKeyframe(userId, adaptationId, shotId, request);
    }

    public PostProductionAssetResponse extractTakeFrame(
            String userId, String takeId, ExtractTakeFrameRequest request) {
        requireMediaReady();
        String requestId = requestId(request.getClientRequestId());
        if (request.getTimestampMs() == null || request.getTimestampMs() < 0) {
            throw new ApiException(422, "VALIDATION_ERROR", "抽帧时间无效");
        }
        String name = request.getName() == null ? "" : request.getName().strip();
        int nameLength = name.codePointCount(0, name.length());
        if (nameLength < 1 || nameLength > 200) {
            throw new ApiException(422, "VALIDATION_ERROR", "抽帧素材名称长度无效");
        }
        String requestHash = sha256(userId
                + "\0" + takeId
                + "\0" + requestId
                + "\0" + request.getTimestampMs()
                + "\0" + name);
        // 同输入共用锁，避免本进程同时启动两个 FFmpeg；它不是持久化正确性的唯一保障。
        ReentrantLock lock = extractionLocks.computeIfAbsent(
                requestHash, ignored -> new ReentrantLock());
        lock.lock();
        try {
            return extractLocked(
                    userId,
                    takeId,
                    requestId,
                    request.getTimestampMs(),
                    name,
                    requestHash);
        } finally {
            lock.unlock();
            extractionLocks.remove(requestHash, lock);
        }
    }

    public EpisodeEditHeadResponse saveEditVersion(
            String userId,
            String adaptationId,
            int episodeNo,
            SaveEpisodeEditVersionRequest request) {
        return repository.saveEditVersion(userId, adaptationId, episodeNo, request);
    }

    public EpisodeEditVersionResponse getEditVersion(String userId, String versionId) {
        return repository.getEditVersion(userId, versionId);
    }

    public EpisodeMixHeadResponse saveMixVersion(
            String userId,
            String adaptationId,
            int episodeNo,
            SaveEpisodeMixVersionRequest request) {
        return repository.saveMixVersion(userId, adaptationId, episodeNo, request);
    }

    public EpisodeMixVersionResponse getMixVersion(String userId, String versionId) {
        return repository.getMixVersion(userId, versionId);
    }

    public EpisodeExportTaskResponse createExportTask(
            String userId,
            String adaptationId,
            int episodeNo,
            StartEpisodeExportRequest request) {
        requireMediaReady();
        return repository.createExportTask(userId, adaptationId, episodeNo, request);
    }

    public EpisodeExportTaskResponse retryExportTask(
            String userId, String taskId, RetryEpisodeExportRequest request) {
        requireMediaReady();
        return repository.retryExportTask(userId, taskId, request);
    }

    public EpisodeExportTaskResponse getExportTask(String userId, String taskId) {
        return repository.getExportTask(userId, taskId);
    }

    public ResolvedVideoAsset getExportFile(String userId, String exportId) {
        VideoAssetFile asset = repository.getExportFile(userId, exportId);
        return new ResolvedVideoAsset(
                storage.resolve(asset.storageKey()), asset.mimeType(), asset.name());
    }

    private PostProductionAssetResponse extractLocked(
            String userId,
            String takeId,
            String requestId,
            int timestampMs,
            String name,
            String requestHash) {
        String assetId = "frame_" + requestHash.substring(0, 40);
        PostProductionAssetResponse replay =
                repository.getExtractionReplay(userId, requestId, requestHash);
        if (replay != null) return replay;
        TakeFrameSource source = repository.getTakeFrameSource(userId, takeId, timestampMs);
        String staleStorageKey = source.projectId() + "/" + assetId + ".png";
        // assetId 由请求哈希确定；清理的只能是该请求上次中断留下的精确路径，不能扫目录。
        storage.delete(staleStorageKey);
        StoredVideoAsset stored;
        try {
            stored = media.extractFrame(
                    storage.resolve(source.storageKey()),
                    source.sha256(),
                    timestampMs,
                    storage,
                    source.projectId(),
                    assetId);
        } catch (VideoMediaProcessingException exception) {
            throw mediaError(exception);
        }
        try {
            return repository.completeExtractedFrame(new CompletedTakeFrameExtraction(
                    userId,
                    source,
                    assetId,
                    name,
                    timestampMs,
                    requestId,
                    requestHash,
                    stored));
        } catch (RuntimeException exception) {
            // 数据库提交响应可能丢失。只有确认没有可重放来源事实时才补偿删除文件。
            PostProductionAssetResponse committed =
                    repository.getExtractionReplay(userId, requestId, requestHash);
            if (committed != null) return committed;
            storage.delete(stored.storageKey());
            throw exception;
        }
    }

    private void requireMediaReady() {
        if (!media.readiness().ready()) {
            throw new ApiException(
                    503,
                    "VIDEO_MEDIA_TOOLS_UNAVAILABLE",
                    "当前环境缺少 ffmpeg 或 ffprobe，不能执行抽帧或整集导出");
        }
    }

    private static ApiException mediaError(VideoMediaProcessingException error) {
        return new ApiException(
                "VIDEO_MEDIA_TOOLS_UNAVAILABLE".equals(error.code()) ? 503 : 422,
                error.code(),
                error.getMessage());
    }

    private static String requestId(String value) {
        String normalized = value == null ? "" : value.strip();
        int length = normalized.codePointCount(0, normalized.length());
        if (length < 16 || length > 128) {
            throw new ApiException(422, "VALIDATION_ERROR", "请求标识长度无效");
        }
        return normalized;
    }

    private static String sha256(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("JVM 不支持 SHA-256", exception);
        }
    }
}
