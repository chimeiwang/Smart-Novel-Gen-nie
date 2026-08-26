package cn.inkforge.cli.runtime;

import tools.jackson.core.util.DefaultIndenter;
import tools.jackson.core.util.DefaultPrettyPrinter;
import tools.jackson.core.util.Separators;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/** 生成与既有 CLI 一致的 UTF-8 JSON 文件文本，避免迁移改变文件哈希。 */
public final class StableJson {

    private static final DefaultPrettyPrinter PRETTY_PRINTER = new DefaultPrettyPrinter(
                    Separators.createDefaultInstance()
                            .withObjectNameValueSpacing(Separators.Spacing.AFTER)
                            .withObjectEntrySpacing(Separators.Spacing.NONE)
                            .withArrayElementSpacing(Separators.Spacing.NONE))
            .withObjectIndenter(new DefaultIndenter("  ", "\n"))
            .withArrayIndenter(new DefaultIndenter("  ", "\n"));

    private StableJson() {}

    public static String pretty(ObjectMapper json, JsonNode value) {
        return json.writer().with(PRETTY_PRINTER).writeValueAsString(value) + "\n";
    }
}
