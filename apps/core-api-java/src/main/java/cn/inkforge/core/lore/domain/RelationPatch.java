package cn.inkforge.core.lore.domain;

import cn.inkforge.core.platform.patch.PatchField;

/** 人物关系的三态补丁；关系两端在现有公共接口中不可修改。 */
public record RelationPatch(
        PatchField<String> relationType,
        PatchField<Integer> intimacy,
        PatchField<String> description,
        PatchField<String> startDate,
        PatchField<String> endDate) {

    public boolean empty() {
        return !relationType.present()
                && !intimacy.present()
                && !description.present()
                && !startDate.present()
                && !endDate.present();
    }
}
