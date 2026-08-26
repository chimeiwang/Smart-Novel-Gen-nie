package cn.inkforge.core.outlines.domain;

import cn.inkforge.core.platform.patch.PatchField;
import java.util.List;

/** 更新伏笔的三态字段集合。 */
public record ForeshadowingPatch(
        PatchField<String> name,
        PatchField<String> plantedAt,
        PatchField<String> plantedContent,
        PatchField<String> expectedPayoff,
        PatchField<String> payoffAt,
        PatchField<String> status) {

    public boolean empty() {
        return List.of(name, plantedAt, plantedContent, expectedPayoff, payoffAt, status)
                .stream()
                .noneMatch(PatchField::present);
    }
}
