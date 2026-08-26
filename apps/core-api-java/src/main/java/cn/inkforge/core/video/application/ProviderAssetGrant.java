package cn.inkforge.core.video.application;

import java.time.Instant;

/** 供应商短时素材令牌中已经验签、尚未过期的最小授权。 */
public record ProviderAssetGrant(String assetId, String sha256, Instant expiresAt) {}
