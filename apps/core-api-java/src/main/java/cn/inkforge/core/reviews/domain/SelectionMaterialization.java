package cn.inkforge.core.reviews.domain;

import java.util.Map;

/** Core 冻结后的完整选区候选和可审核差异。 */
public record SelectionMaterialization(
        Map<String, Object> payload, Map<String, Object> diff) {}
