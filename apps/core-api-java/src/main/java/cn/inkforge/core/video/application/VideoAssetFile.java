package cn.inkforge.core.video.application;

/** 通过用户归属校验后才可用于解析文件的最小数据库事实。 */
public record VideoAssetFile(String storageKey, String mimeType, String name) {}
