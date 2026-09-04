package cn.inkforge.cli.commands;

/** 自然输入只校验统一 Unicode 空白，不归一化原文。 */
final class WorkflowInputText {
    private WorkflowInputText() {}

    static boolean hasCompleteText(String value) {
        return value != null && value.codePoints().anyMatch(code -> !(
                (code >= 0x0009 && code <= 0x000d) || code == 0x0020 || code == 0x0085
                        || code == 0x00a0 || code == 0x1680 || (code >= 0x2000 && code <= 0x200a)
                        || code == 0x2028 || code == 0x2029 || code == 0x202f || code == 0x205f
                        || code == 0x3000 || code == 0xfeff));
    }
}
