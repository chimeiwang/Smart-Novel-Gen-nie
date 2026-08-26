package cn.inkforge.core.lore.domain;

import cn.inkforge.contracts.api.DeleteImpactResponse;

/** 批量人物经历命令的有类型结果。 */
public record ExperienceBatchMutationResult(
        MutationAction action,
        ExperienceSnapshot experience,
        DeleteImpactResponse deletion,
        Boolean effective) {}
