package cn.inkforge.core.workflows.domain;

/** 可观测且可告警的 Step 预算维度。 */
public enum WorkflowBudgetDimension {
    MODEL_CALLS,
    INPUT_TOKENS,
    PROMPT_CACHE_MISS_TOKENS,
    COMPLETION_TOKENS,
    REASONING_TOKENS,
    VISIBLE_OUTPUT_TOKENS,
    COST_MICROS,
    PROVIDER_ATTEMPTS,
    PROTOCOL_CORRECTIONS,
    WALL_TIME
}
