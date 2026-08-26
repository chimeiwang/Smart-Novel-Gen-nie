package cn.inkforge.cli.runtime;

import tools.jackson.databind.node.ObjectNode;

@FunctionalInterface
public interface CommandHandler {

    CommandResult handle(CommandContext context, ObjectNode payload);
}
