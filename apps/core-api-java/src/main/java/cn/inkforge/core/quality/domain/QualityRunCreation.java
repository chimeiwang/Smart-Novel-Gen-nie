package cn.inkforge.core.quality.domain;

/** 创建或幂等重放质量运行的结果；重放不得再次投递。 */
public record QualityRunCreation(QualityDispatchRecord record, boolean created) {}
