package cn.inkforge.cli.commands;

import cn.inkforge.cli.runtime.CommandHandler;
import java.util.Map;

/** 视频生产命令域的唯一注册入口。 */
public final class VideoCommands {

    private VideoCommands() {}

    public static void register(Map<String, CommandHandler> handlers) {
        VideoProjectCommands.register(handlers);
        VideoAdaptationCommands.register(handlers);
        VideoVisualCommands.register(handlers);
        VideoRenderCommands.register(handlers);
        VideoPostProductionCommands.register(handlers);
        VideoWatchCommands.register(handlers);
    }
}
