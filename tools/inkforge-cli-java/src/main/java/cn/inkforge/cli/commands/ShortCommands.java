package cn.inkforge.cli.commands;

import cn.inkforge.cli.runtime.CommandHandler;
import java.util.Map;

/** 中短篇命令域的唯一注册入口。 */
public final class ShortCommands {

    private ShortCommands() {}

    public static void register(Map<String, CommandHandler> handlers) {
        ShortDocumentCommands.register(handlers);
        ShortVersionCommands.register(handlers);
        ShortAgentCommands.register(handlers);
    }
}
