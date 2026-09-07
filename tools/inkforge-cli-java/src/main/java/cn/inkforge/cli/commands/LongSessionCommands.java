package cn.inkforge.cli.commands;

import cn.inkforge.cli.runtime.CliInputException;
import cn.inkforge.cli.runtime.CommandContext;
import cn.inkforge.cli.runtime.CommandHandler;
import cn.inkforge.cli.runtime.CommandResult;
import java.util.List;
import java.util.Map;
import java.util.Set;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** 只补齐现有公共会话创建接口，不隐式创建任务或调用模型。 */
final class LongSessionCommands {
    private LongSessionCommands() {}

    static void register(Map<String, CommandHandler> handlers) {
        handlers.put("long.session.create", LongSessionCommands::create);
    }

    private static CommandResult create(CommandContext context, ObjectNode payload) {
        MutationPayloads.requireFields(payload, Set.of("novelId", "chapterId"), Set.of("title"));
        ObjectNode body = context.dependencies().json().createObjectNode();
        for (String name : List.of("novelId", "chapterId", "title")) {
            if (!payload.has(name)) continue;
            JsonNode value = payload.get(name);
            boolean nullable = name.equals("title");
            int maximum = nullable ? 500 : 256;
            if (!(nullable && value.isNull())) {
                int length = value.isTextual()
                        ? value.textValue().codePointCount(0, value.textValue().length()) : 0;
                if (length < 1 || length > maximum) {
                    throw new CliInputException("INVALID_FIELD",
                            name + " 必须是长度 1 到 " + maximum + " 的字符串" + (nullable ? "或 null" : ""));
                }
            }
            body.set(name, value);
        }
        // 原公共接口无幂等字段；连接结果不确定交调用方回读核对，不自动重试。
        return CommandResult.json(context.requireApi().request("POST", "/api/v1/writing/sessions", body));
    }
}
