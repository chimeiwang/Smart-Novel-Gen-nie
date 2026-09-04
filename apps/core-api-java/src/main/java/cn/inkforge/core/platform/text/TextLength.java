package cn.inkforge.core.platform.text;

/** 与 Web/Python 同一排除集合；按 Unicode 码点计数，不扩大为空白分类全集。 */
public final class TextLength {
    private TextLength() {}
    public static int count(String text) {
        return (int) text.codePoints().filter(value -> !ignored(value)).count();
    }
    private static boolean ignored(int value) {
        return (value >= 0x0009 && value <= 0x000D)
                || value == 0x0020 || value == 0x0085 || value == 0x00A0 || value == 0x1680
                || (value >= 0x2000 && value <= 0x200A) || value == 0x2028 || value == 0x2029
                || value == 0x202F || value == 0x205F || value == 0x3000 || value == 0xFEFF;
    }
}
