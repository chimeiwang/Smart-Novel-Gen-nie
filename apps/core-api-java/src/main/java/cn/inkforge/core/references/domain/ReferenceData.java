package cn.inkforge.core.references.domain;

/** 新建参考资料的完整业务字段；正文与 URL 均按原始输入保存。 */
public record ReferenceData(String title, String type, String content, String sourceUrl) {}
