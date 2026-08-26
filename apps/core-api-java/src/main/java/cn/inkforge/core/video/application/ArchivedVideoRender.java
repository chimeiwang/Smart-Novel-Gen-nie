package cn.inkforge.core.video.application;

/** 已从供应商临时地址完整流入受控存储的渲染结果。 */
public record ArchivedVideoRender(String assetId, StoredVideoAsset stored) {}
