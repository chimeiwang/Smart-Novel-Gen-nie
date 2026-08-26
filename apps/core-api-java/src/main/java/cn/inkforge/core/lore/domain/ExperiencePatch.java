package cn.inkforge.core.lore.domain;

import cn.inkforge.core.platform.patch.PatchField;

/** 人物经历的三态补丁。 */
public record ExperiencePatch(
        PatchField<String> chapterId,
        PatchField<String> content,
        PatchField<Integer> order) {

    public boolean empty() {
        return !chapterId.present() && !content.present() && !order.present();
    }
}
