package cn.inkforge.core.shortmedium.domain;

import java.util.Set;

/** ReviewArtifact 中持久化的不可变中短篇版本载荷。 */
public record ShortMediumVersionPayload(
        String kind,
        String documentType,
        int versionNumber,
        String baseVersionId,
        String clientRequestId,
        String source,
        String content,
        String contentHash,
        String sourceTaskId,
        String sourceJobId,
        String sourceOutlineVersionId,
        String userInstruction,
        String sourceKind,
        String sourceText,
        String restoredFromVersionId,
        boolean createdFromSelection,
        Integer selectionStart,
        Integer selectionEnd,
        String selectedTextHash) {

    private static final Set<String> SOURCES = Set.of("agent", "manual", "restore");
    private static final Set<String> SOURCE_KINDS =
            Set.of("idea", "opening", "ending", "outline", "mixed");

    public ShortMediumVersionPayload {
        if (versionNumber < 1 || content == null) {
            throw new IllegalArgumentException("版本号或正文无效");
        }
        if (contentHash == null
                || !contentHash.matches("[0-9a-f]{64}")
                || !contentHash.equals(ShortMediumText.sha256(content))) {
            throw new IllegalArgumentException("contentHash 必须匹配完整 content");
        }
        if ("outline".equals(documentType)) {
            if (!"outline_draft".equals(kind) || sourceOutlineVersionId != null) {
                throw new IllegalArgumentException("大纲版本身份无效");
            }
        } else if ("manuscript".equals(documentType)) {
            if (!"chapter_draft".equals(kind) || sourceOutlineVersionId == null) {
                throw new IllegalArgumentException("正文版本必须绑定 sourceOutlineVersionId");
            }
        } else {
            throw new IllegalArgumentException("文档类型无效");
        }
        if (!SOURCES.contains(source)) {
            throw new IllegalArgumentException("版本来源无效");
        }
        if ("agent".equals(source)) {
            if (sourceTaskId == null
                    || sourceJobId == null
                    || clientRequestId != null
                    || restoredFromVersionId != null) {
                throw new IllegalArgumentException("Agent 版本来源身份无效");
            }
        } else {
            requireClientRequestId(clientRequestId);
            if (sourceTaskId != null || sourceJobId != null) {
                throw new IllegalArgumentException("人工或恢复版本不能绑定 Agent 任务");
            }
        }
        if ("restore".equals(source) != (restoredFromVersionId != null)) {
            throw new IllegalArgumentException("恢复版本必须绑定 restoredFromVersionId");
        }
        if (sourceKind != null && !SOURCE_KINDS.contains(sourceKind)) {
            throw new IllegalArgumentException("起始素材类型无效");
        }
        boolean hasSelectionField = selectionStart != null
                || selectionEnd != null
                || selectedTextHash != null;
        if (createdFromSelection) {
            if (selectionStart == null
                    || selectionEnd == null
                    || selectionStart < 0
                    || selectionStart >= selectionEnd
                    || selectedTextHash == null
                    || !selectedTextHash.matches("[0-9a-f]{64}")) {
                throw new IllegalArgumentException("选区版本身份无效");
            }
        } else if (hasSelectionField) {
            throw new IllegalArgumentException("非选区版本不能携带选区字段");
        }
    }

    public static void requireClientRequestId(String value) {
        int length = value == null ? 0 : ShortMediumText.codePointLength(value);
        if (length < 16 || length > 128) {
            throw new IllegalArgumentException("clientRequestId 长度必须为 16..128");
        }
    }
}
