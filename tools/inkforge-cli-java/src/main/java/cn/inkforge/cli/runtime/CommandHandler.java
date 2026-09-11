package cn.inkforge.cli.runtime;

import tools.jackson.databind.node.ObjectNode;

/** 把已校验为 JSON 对象的标准输入映射为命令结果。 */
@FunctionalInterface
public interface CommandHandler {

    CommandResult handle(CommandContext context, ObjectNode payload);
}
