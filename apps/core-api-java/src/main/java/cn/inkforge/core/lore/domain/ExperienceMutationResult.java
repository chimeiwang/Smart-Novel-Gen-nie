package cn.inkforge.core.lore.domain;

/** 创建人物经历的快照及本次请求是否真正落库。 */
public record ExperienceMutationResult(ExperienceSnapshot experience, boolean effective) {}
