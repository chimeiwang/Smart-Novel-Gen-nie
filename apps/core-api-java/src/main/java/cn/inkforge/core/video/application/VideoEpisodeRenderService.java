package cn.inkforge.core.video.application;

import cn.inkforge.core.platform.http.ApiException;
import java.net.URI;
import java.util.Objects;
import java.util.function.BooleanSupplier;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** 独立剧集逐镜生成用例；所有生成参数均由制作基线决定。 */
public final class VideoEpisodeRenderService {

    private final VideoEpisodeRenderRepository repository;
    private final VideoAssetStore storage;
    private final boolean previewEnabled;
    private final boolean configured;
    private final boolean enabled;
    private final URI providerMediaBaseUrl;
    private final ProviderAssetTokenCodec providerAssetTokens;
    private final String executionMode;
    private final boolean simulationAvailable;
    private final BooleanSupplier gatewayAvailable;

    public VideoEpisodeRenderService(
            VideoEpisodeRenderRepository repository,
            VideoAssetStore storage,
            boolean previewEnabled,
            boolean configured,
            boolean enabled,
            URI providerMediaBaseUrl,
            ProviderAssetTokenCodec providerAssetTokens,
            String executionMode,
            boolean simulationAvailable,
            BooleanSupplier gatewayAvailable) {
        this.repository = Objects.requireNonNull(repository);
        this.storage = Objects.requireNonNull(storage);
        this.previewEnabled = previewEnabled;
        this.configured = configured;
        this.enabled = enabled;
        this.providerMediaBaseUrl = providerMediaBaseUrl;
        this.providerAssetTokens = providerAssetTokens;
        this.executionMode = Objects.requireNonNull(executionMode);
        this.simulationAvailable = simulationAvailable;
        this.gatewayAvailable = Objects.requireNonNull(gatewayAvailable);
    }

    /** 从指定制作基线镜头冻结事实创建任务，调用方不能覆盖模型参数。 */
    public ObjectNode createTask(
            String userId,
            String episodeId,
            String baselineId,
            String shotId,
            JsonNode request) {
        requireWritable();
        return repository.createTask(
                userId,
                episodeId,
                baselineId,
                shotId,
                request,
                executionMode,
                referenceTransportConfigured());
    }

    /** 只复制原任务输入；提交未知永远不能进入此入口。 */
    public ObjectNode retryTask(
            String userId, String episodeId, String taskId, JsonNode request) {
        requireWritable();
        return repository.retryTask(
                userId,
                episodeId,
                taskId,
                request,
                executionMode,
                referenceTransportConfigured());
    }

    public ObjectNode getTask(String userId, String episodeId, String taskId) {
        requirePreview();
        return repository.getTask(userId, episodeId, taskId);
    }

    public ResolvedVideoAsset getTakeFile(String userId, String episodeId, String takeId) {
        requirePreview();
        VideoAssetFile asset = repository.getTakeFile(userId, episodeId, takeId);
        return new ResolvedVideoAsset(
                storage.resolve(asset.storageKey()), asset.mimeType(), asset.name());
    }

    /** 校验短时传输令牌后，只从新链共享的受控素材库返回参考图。 */
    public ResolvedVideoAsset getProviderAssetFile(String token) {
        if (providerAssetTokens == null) {
            throw new ApiException(
                    404,
                    "VIDEO_PROVIDER_ASSET_TRANSPORT_DISABLED",
                    "供应商素材传输未启用");
        }
        ProviderAssetGrant grant = providerAssetTokens.decode(token);
        VideoAssetFile asset =
                repository.getProviderAssetFile(grant.assetId(), grant.sha256());
        return new ResolvedVideoAsset(
                storage.resolve(asset.storageKey()), asset.mimeType(), asset.name());
    }

    private void requireWritable() {
        requirePreview();
        if (!gatewayAvailable.getAsBoolean()) {
            throw new ApiException(
                    503, "VIDEO_RENDER_GATEWAY_UNAVAILABLE", "视频任务服务尚未配置");
        }
        if ("simulated".equals(executionMode)) {
            if (!simulationAvailable) {
                throw new ApiException(
                        503,
                        "VIDEO_SIMULATION_MEDIA_TOOLS_UNAVAILABLE",
                        "当前环境缺少模拟视频所需的 FFmpeg 或 ffprobe");
            }
            return;
        }
        if (!"live".equals(executionMode)) {
            throw new ApiException(
                    503, "VIDEO_RENDER_EXECUTION_MODE_INVALID", "视频生成执行模式无效");
        }
        if (!configured) {
            throw new ApiException(503, "SEEDANCE_NOT_CONFIGURED", "当前环境尚未配置 Seedance");
        }
        if (!enabled) {
            throw new ApiException(503, "SEEDANCE_DISABLED", "当前环境尚未启用 Seedance 真实生成");
        }
    }

    private boolean referenceTransportConfigured() {
        return providerMediaBaseUrl != null && providerAssetTokens != null;
    }

    private void requirePreview() {
        if (!previewEnabled) {
            throw new ApiException(503, "VIDEO_PREVIEW_DISABLED", "长篇视频开发预览暂未启用");
        }
    }
}
