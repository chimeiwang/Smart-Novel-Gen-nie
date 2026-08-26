package cn.inkforge.core.lore.domain;

import java.util.Objects;

/** 创建设定实体的快照及本次请求是否真正落库。 */
public record LoreEntityMutationResult(LoreEntitySnapshot entity, boolean effective) {

    public LoreEntityMutationResult {
        Objects.requireNonNull(entity);
    }
}
