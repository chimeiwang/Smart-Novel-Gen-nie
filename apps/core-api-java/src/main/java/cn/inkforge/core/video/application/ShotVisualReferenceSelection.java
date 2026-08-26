package cn.inkforge.core.video.application;

/** 镜头引用一个精确视觉设定版本及其参考强度。 */
public record ShotVisualReferenceSelection(String canonVersionId, int strength) {}
