package cn.inkforge.core.references.domain;

import cn.inkforge.core.platform.patch.PatchField;

/** 参考资料 PATCH 三态字段；只有 sourceUrl 允许显式 null。 */
public record ReferencePatch(
        PatchField<String> title,
        PatchField<String> type,
        PatchField<String> content,
        PatchField<String> sourceUrl) {

    public boolean empty() {
        return !title.present() && !type.present() && !content.present() && !sourceUrl.present();
    }
}
