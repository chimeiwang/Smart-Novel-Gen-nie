package cn.inkforge.core.lore.domain;

import cn.inkforge.contracts.api.DeleteImpactResponse;

/** 批量设定命令的有类型结果。 */
public record LoreBatchMutationResult(
        MutationAction action,
        LoreEntitySnapshot entity,
        DeleteImpactResponse deletion,
        Boolean effective) {}
