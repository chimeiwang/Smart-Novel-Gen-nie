package cn.inkforge.core.lore.domain;

/** 创建人物关系的快照及本次请求是否真正落库。 */
public record RelationMutationResult(RelationSnapshot relation, boolean effective) {}
