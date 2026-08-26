package cn.inkforge.core.video.application;

import cn.inkforge.contracts.api.ConfirmVideoAssetRequest;
import cn.inkforge.contracts.api.CreateVideoProjectRequest;
import cn.inkforge.contracts.api.VideoAssetResponse;
import cn.inkforge.contracts.api.VideoProjectDetailResponse;
import cn.inkforge.contracts.api.VideoProjectListResponse;
import cn.inkforge.contracts.api.VideoProjectResponse;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.video.domain.VideoAssetRules;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import org.springframework.web.multipart.MultipartFile;

/** 视频项目与真实素材的应用服务；文件和数据库通过补偿式事务保持一致。 */
public final class VideoProjectService {

    private static final Set<String> SOURCE_KINDS = Set.of(
            "user_upload", "authorized_real", "virtual", "model_generated");

    private final VideoProjectRepository repository;
    private final VideoAssetStore storage;
    private final VideoMediaProbe durationProbe;
    private final VideoIdGenerator ids;
    private final boolean previewEnabled;
    private final boolean seedanceConfigured;
    private final boolean seedanceEnabled;

    public VideoProjectService(
            VideoProjectRepository repository,
            VideoAssetStore storage,
            VideoMediaProbe durationProbe,
            VideoIdGenerator ids,
            boolean previewEnabled,
            boolean seedanceConfigured,
            boolean seedanceEnabled) {
        this.repository = Objects.requireNonNull(repository);
        this.storage = Objects.requireNonNull(storage);
        this.durationProbe = Objects.requireNonNull(durationProbe);
        this.ids = Objects.requireNonNull(ids);
        this.previewEnabled = previewEnabled;
        this.seedanceConfigured = seedanceConfigured;
        this.seedanceEnabled = seedanceEnabled;
    }

    public VideoProjectResponse createProject(
            String userId, String novelId, CreateVideoProjectRequest request) {
        requirePreviewEnabled();
        String title = request.getTitle().strip();
        if (title.isEmpty()) {
            throw new ApiException(422, "VIDEO_PROJECT_TITLE_REQUIRED", "视频项目标题不能为空");
        }
        String language = request.getTargetLanguage().strip();
        if (language.isEmpty()) {
            throw new ApiException(422, "VIDEO_PROJECT_LANGUAGE_REQUIRED", "目标语言不能为空");
        }
        VideoProjectCreation creation = new VideoProjectCreation(
                title,
                request.getMode().getValue(),
                request.getTargetAspectRatio().getValue(),
                language);
        return project(repository.createProject(userId, novelId, creation));
    }

    public VideoProjectListResponse listProjects(String userId, String novelId) {
        List<VideoProjectResponse> projects = repository.listProjects(userId, novelId).stream()
                .map(VideoProjectService::project)
                .toList();
        return new VideoProjectListResponse(
                previewEnabled, projects, seedanceConfigured, seedanceEnabled);
    }

    public VideoProjectDetailResponse getProject(String userId, String projectId) {
        VideoProjectAggregate aggregate = repository.getProject(userId, projectId);
        return new VideoProjectDetailResponse(
                aggregate.assets().stream().map(VideoProjectService::asset).toList(),
                previewEnabled,
                project(aggregate.project()),
                seedanceConfigured,
                seedanceEnabled);
    }

    public VideoAssetResponse uploadAsset(
            String userId,
            String projectId,
            MultipartFile upload,
            String name,
            String modality,
            String duty,
            String sourceKind) {
        requirePreviewEnabled();
        String normalizedName = normalizeName(name, upload);
        String normalizedSource = sourceKind == null ? "user_upload" : sourceKind;
        if (!SOURCE_KINDS.contains(normalizedSource)) {
            throw new ApiException(
                    422, "VIDEO_ASSET_SOURCE_INVALID", "素材来源类型无效");
        }
        VideoAssetRules.requireUploadCombination(modality, duty);
        repository.requireWritableProject(userId, projectId);

        String assetId = ids.next();
        StoredVideoAsset stored = storage.save(projectId, assetId, modality, upload);
        try {
            Integer durationMs = duration(stored, modality);
            VideoAssetCreation creation = new VideoAssetCreation(
                    assetId,
                    normalizedName,
                    modality,
                    duty,
                    normalizedSource,
                    durationMs,
                    stored);
            return asset(repository.createAsset(userId, projectId, creation));
        } catch (RuntimeException exception) {
            storage.delete(stored.storageKey());
            throw exception;
        }
    }

    public VideoAssetResponse confirmAsset(
            String userId, String assetId, ConfirmVideoAssetRequest request) {
        requirePreviewEnabled();
        return asset(repository.confirmAsset(
                userId, assetId, request.getRightsStatus().getValue()));
    }

    public ResolvedVideoFile getAssetFile(String userId, String assetId) {
        VideoAssetFile asset = repository.getAssetFile(userId, assetId);
        var path = storage.resolve(asset.storageKey());
        if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) {
            throw new ApiException(
                    404, "VIDEO_ASSET_FILE_NOT_FOUND", "视频素材文件不存在");
        }
        return new ResolvedVideoFile(path, asset.mimeType(), asset.name());
    }

    private Integer duration(StoredVideoAsset stored, String modality) {
        if (!Set.of("audio", "video").contains(modality)) return null;
        if (!durationProbe.available()) {
            throw new ApiException(
                    503,
                    "VIDEO_MEDIA_PROBE_UNAVAILABLE",
                    "当前环境缺少 ffprobe，不能登记音视频素材的真实时长");
        }
        try {
            return durationProbe.probeDurationMs(stored.absolutePath());
        } catch (VideoMediaProbeException exception) {
            throw new ApiException(
                    422,
                    "VIDEO_ASSET_DURATION_INVALID",
                    "无法读取上传音视频的有效时长");
        }
    }

    private static String normalizeName(String name, MultipartFile upload) {
        String normalized = name == null ? "" : name.strip();
        if (normalized.isEmpty() && upload != null && upload.getOriginalFilename() != null) {
            normalized = upload.getOriginalFilename().strip();
        }
        if (normalized.isEmpty()) normalized = "未命名素材";
        if (normalized.length() > 200) {
            throw new ApiException(
                    422, "VIDEO_ASSET_NAME_TOO_LONG", "素材名称不能超过 200 字");
        }
        return normalized;
    }

    private void requirePreviewEnabled() {
        if (!previewEnabled) {
            throw new ApiException(
                    503, "VIDEO_PREVIEW_DISABLED", "长篇视频开发预览暂未启用");
        }
    }

    private static VideoProjectResponse project(VideoProjectSnapshot value) {
        return new VideoProjectResponse(
                value.createdAt(),
                value.id(),
                value.mode(),
                value.novelId(),
                value.provider(),
                value.revision(),
                value.status(),
                value.targetAspectRatio(),
                value.targetLanguage(),
                value.title(),
                value.updatedAt());
    }

    private static VideoAssetResponse asset(VideoAssetSnapshot value) {
        return new VideoAssetResponse(
                value.byteSize(),
                value.createdAt(),
                value.durationMs(),
                VideoAssetResponse.DutyEnum.fromValue(value.duty()),
                value.id(),
                value.lockedAt(),
                value.mimeType(),
                VideoAssetResponse.ModalityEnum.fromValue(value.modality()),
                value.name(),
                value.projectId(),
                value.rightsStatus(),
                value.sha256(),
                value.sourceKind(),
                value.updatedAt());
    }
}
