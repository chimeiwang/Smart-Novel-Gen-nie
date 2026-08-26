package cn.inkforge.core.outlines.domain;

import cn.inkforge.core.platform.patch.PatchField;
import java.util.List;

/** 更新节点的三态字段集合。 */
public record OutlineNodePatch(
        PatchField<String> title,
        PatchField<String> content,
        PatchField<String> kind,
        PatchField<String> status,
        PatchField<Integer> order,
        PatchField<String> parentId,
        PatchField<String> linkedChapterId,
        PatchField<Integer> estimatedWordCount,
        PatchField<Integer> actualWordCount,
        PatchField<Integer> chapterStartOrder,
        PatchField<Integer> chapterEndOrder) {

    public boolean empty() {
        return fields().stream().noneMatch(PatchField::present);
    }

    private List<PatchField<?>> fields() {
        return List.of(
                title,
                content,
                kind,
                status,
                order,
                parentId,
                linkedChapterId,
                estimatedWordCount,
                actualWordCount,
                chapterStartOrder,
                chapterEndOrder);
    }
}
