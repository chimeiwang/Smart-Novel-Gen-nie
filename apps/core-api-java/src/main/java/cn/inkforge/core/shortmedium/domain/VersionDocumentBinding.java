package cn.inkforge.core.shortmedium.domain;

import cn.inkforge.core.platform.http.ApiException;

/** 中短篇版本与唯一大纲或全文章节的绑定。 */
public record VersionDocumentBinding(String documentType, String chapterId) {

    public VersionDocumentBinding {
        boolean valid = ("outline".equals(documentType) && chapterId == null)
                || ("manuscript".equals(documentType) && chapterId != null);
        if (!valid) {
            throw new ApiException(
                    422,
                    "SHORT_MEDIUM_DOCUMENT_BINDING_INVALID",
                    "outline".equals(documentType)
                            ? "大纲版本不能绑定章节"
                            : "正文版本必须绑定全文章节");
        }
    }

    public String artifactKey(String novelId) {
        return "outline".equals(documentType)
                ? "short-medium:outline:" + novelId
                : "short-medium:manuscript:" + chapterId;
    }
}
