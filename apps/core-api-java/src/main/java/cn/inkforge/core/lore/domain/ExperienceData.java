package cn.inkforge.core.lore.domain;

/** 人物经历创建字段；order 为空时由仓储在角色范围内顺序分配。 */
public record ExperienceData(String chapterId, String content, Integer order) {}
