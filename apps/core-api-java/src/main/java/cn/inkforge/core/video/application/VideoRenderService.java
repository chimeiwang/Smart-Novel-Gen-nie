package cn.inkforge.core.video.application;

import cn.inkforge.contracts.api.ChapterRenderWorkspaceResponse;
import cn.inkforge.contracts.api.ConfirmShotTakeRequest;
import cn.inkforge.contracts.api.RetryShotRenderRequest;
import cn.inkforge.contracts.api.ShotRenderTaskResponse;
import cn.inkforge.contracts.api.ShotTakeDecisionResponse;
import cn.inkforge.contracts.api.StartShotRenderRequest;
import cn.inkforge.contracts.api.VideoRenderReadinessResponse;
import cn.inkforge.core.platform.http.ApiException;
import java.net.URI;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

/** 逐镜视频生成的公共用例门禁；控制器只负责 HTTP 投影。 */
public final class VideoRenderService {

    private final VideoRenderRepository repository;
    private final VideoAssetStore storage;
    private final boolean configured;
    private final boolean enabled;
    private final String model;
    private final URI providerMediaBaseUrl;
    private final ProviderAssetTokenCodec providerAssetTokens;

    public VideoRenderService(
            VideoRenderRepository repository,
            VideoAssetStore storage,
            boolean configured,
            boolean enabled,
            String model,
            URI providerMediaBaseUrl,
            ProviderAssetTokenCodec providerAssetTokens) {
        this.repository = Objects.requireNonNull(repository);
        this.storage = Objects.requireNonNull(storage);
        this.configured = configured;
        this.enabled = enabled;
        this.model = Objects.requireNonNull(model);
        this.providerMediaBaseUrl = providerMediaBaseUrl;
        this.providerAssetTokens = providerAssetTokens;
    }

    public VideoRenderReadinessResponse readiness() {
        boolean transportConfigured =
                providerMediaBaseUrl != null && providerAssetTokens != null;
        List<String> blockers = new ArrayList<>();
        if (!configured) blockers.add("Seedance 尚未配置");
        if (!enabled) blockers.add("Seedance 真实调用尚未启用");
        if (!transportConfigured) {
            blockers.add("视觉参考图公网短时传输尚未配置；无参考图镜头不受影响");
        }
        return new VideoRenderReadinessResponse(
                        configured, enabled, model, transportConfigured)
                .blockers(List.copyOf(blockers));
    }

    public ShotRenderTaskResponse createTask(
            String userId,
            String adaptationId,
            String shotId,
            StartShotRenderRequest request) {
        requireEnabled();
        return repository.createTask(
                userId,
                adaptationId,
                shotId,
                request,
                model,
                readiness().getReferenceTransportConfigured());
    }

    public ShotRenderTaskResponse retryTask(
            String userId, String taskId, RetryShotRenderRequest request) {
        requireEnabled();
        return repository.retryTask(
                userId,
                taskId,
                request,
                readiness().getReferenceTransportConfigured());
    }

    public ShotRenderTaskResponse getTask(String userId, String taskId) {
        return repository.getTask(userId, taskId);
    }

    public ChapterRenderWorkspaceResponse getWorkspace(String userId, String adaptationId) {
        return repository.getWorkspace(userId, adaptationId, readiness());
    }

    public ShotTakeDecisionResponse confirmTake(
            String userId,
            String adaptationId,
            String shotId,
            String takeId,
            ConfirmShotTakeRequest request) {
        ShotTakeDecisionResponse decision = repository.confirmTake(
                userId, adaptationId, shotId, takeId, request);
        if (decision.getStatus() != ShotTakeDecisionResponse.StatusEnum.SUCCEEDED) {
            throw new ApiException(
                    409,
                    decision.getErrorCode() == null
                            ? "VIDEO_TAKE_CONFIRM_REJECTED"
                            : decision.getErrorCode(),
                    "当前采用的 Take 已经变化，请刷新后重新确认",
                    decision);
        }
        return decision;
    }

    public ResolvedVideoAsset getTakeFile(String userId, String takeId) {
        VideoAssetFile asset = repository.getTakeFile(userId, takeId);
        return new ResolvedVideoAsset(
                storage.resolve(asset.storageKey()), asset.mimeType(), asset.name());
    }

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

    private void requireEnabled() {
        if (!configured) {
            throw new ApiException(503, "SEEDANCE_NOT_CONFIGURED", "当前环境尚未配置 Seedance");
        }
        if (!enabled) {
            throw new ApiException(
                    503, "SEEDANCE_DISABLED", "当前环境尚未启用 Seedance 真实视频生成");
        }
    }
}
