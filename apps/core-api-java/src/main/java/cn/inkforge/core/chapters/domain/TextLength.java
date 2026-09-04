package cn.inkforge.core.chapters.domain;

/** 与 Web/Python 一致：删除指定 Unicode 空白和 BOM 后按 Unicode 码点计数。 */
public final class TextLength {

    private TextLength() {}

    public static int count(String text) {
        return cn.inkforge.core.platform.text.TextLength.count(text);
    }
}
