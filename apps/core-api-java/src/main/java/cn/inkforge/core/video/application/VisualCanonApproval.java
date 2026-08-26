package cn.inkforge.core.video.application;

/** 将当前候选物化为不可变视觉设定版本的 CAS 命令。 */
public record VisualCanonApproval(int expectedRevision, String candidateAssetId) {}
