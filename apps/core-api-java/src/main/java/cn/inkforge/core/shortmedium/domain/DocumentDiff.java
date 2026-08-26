package cn.inkforge.core.shortmedium.domain;

import java.util.List;

/** 不可截断的段落级文档差异以及与确认上下文绑定的摘要。 */
public record DocumentDiff(
        String fromVersionId,
        String toVersionId,
        int fromWordCount,
        int toWordCount,
        int wordCountDelta,
        List<DocumentDiffBlock> blocks,
        String confirmationHash) {

    public DocumentDiff {
        if (fromWordCount < 0 || toWordCount < 0) {
            throw new IllegalArgumentException("差异字数不能为负数");
        }
        if (wordCountDelta != toWordCount - fromWordCount) {
            throw new IllegalArgumentException("差异字数变化不一致");
        }
        blocks = List.copyOf(blocks);
        if (confirmationHash == null || !confirmationHash.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("差异确认哈希无效");
        }
    }

    public DocumentDiff withConfirmationHash(String value) {
        return new DocumentDiff(
                fromVersionId,
                toVersionId,
                fromWordCount,
                toWordCount,
                wordCountDelta,
                blocks,
                value);
    }

    public DocumentDiff withToVersionId(String value) {
        return new DocumentDiff(
                fromVersionId,
                value,
                fromWordCount,
                toWordCount,
                wordCountDelta,
                blocks,
                confirmationHash);
    }
}
