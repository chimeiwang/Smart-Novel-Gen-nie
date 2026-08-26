package cn.inkforge.core.shortmedium.domain;

import java.util.Set;

/** 完整文档差异中的一个非 equal 自然段块；位置统一使用 Unicode code point。 */
public record DocumentDiffBlock(
        String type,
        int oldStart,
        int oldEnd,
        int newStart,
        int newEnd,
        String oldText,
        String newText) {

    private static final Set<String> TYPES = Set.of("insert", "delete", "replace");

    public DocumentDiffBlock {
        if (!TYPES.contains(type)) {
            throw new IllegalArgumentException("差异块类型无效");
        }
        if (oldStart < 0 || oldEnd < oldStart || newStart < 0 || newEnd < newStart) {
            throw new IllegalArgumentException("差异块范围无效");
        }
        if (("insert".equals(type) && oldText != null)
                || ("delete".equals(type) && newText != null)) {
            throw new IllegalArgumentException("差异块正文与类型不匹配");
        }
    }
}
