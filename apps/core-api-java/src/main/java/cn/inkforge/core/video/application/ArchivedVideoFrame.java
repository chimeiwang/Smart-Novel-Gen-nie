package cn.inkforge.core.video.application;

/** 已从供应商临时尾帧地址流入受控存储的图片事实。 */
public record ArchivedVideoFrame(String assetId, StoredVideoAsset stored) {}
