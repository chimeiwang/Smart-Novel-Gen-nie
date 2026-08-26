package cn.inkforge.cli.commands;

import cn.inkforge.cli.runtime.CliInputException;
import cn.inkforge.cli.runtime.CommandContext;
import cn.inkforge.cli.runtime.CommandHandler;
import cn.inkforge.cli.runtime.CommandResult;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** 质量检查运行与人工状态转换命令。 */
final class LongQualityCommands {

    private LongQualityCommands() {}

    static void register(Map<String, CommandHandler> handlers) {
        handlers.put("long.quality.run", LongQualityCommands::run);
        handlers.put("long.quality.skip", (context, payload) ->
                update(context, payload, "skipped", false));
        handlers.put("long.quality.reset", (context, payload) ->
                update(context, payload, "pending", true));
    }

    private static CommandResult run(CommandContext context, ObjectNode payload) {
        rejectUnexpectedFields(
                payload, Set.of("profile", "checkId", "clientRequestId", "taskId", "message"));
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("clientRequestId", MutationPayloads.clientRequestId(payload, 128));
        for (String field : new String[] {"taskId", "message"}) {
            if (payload.has(field)) body.set(field, stringOrNull(payload, field));
        }
        return CommandResult.json(context.requireApi().request(
                "POST", checkPath(payload) + "/run", body));
    }

    private static CommandResult update(
            CommandContext context,
            ObjectNode payload,
            String status,
            boolean resetResult) {
        rejectUnexpectedFields(payload, Set.of("profile", "checkId", "expectedUpdatedAt"));
        String path = checkPath(payload);
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("status", status);
        body.put("resetResult", resetResult);
        body.put(
                "expectedUpdatedAt",
                MutationPayloads.expectedUpdatedAt(payload, false));
        return CommandResult.json(context.requireApi().request(
                "PATCH", path, body));
    }

    private static String checkPath(ObjectNode payload) {
        return "/api/v1/quality-checks/"
                + Payloads.segment(MutationPayloads.requireString(payload, "checkId"));
    }

    private static JsonNode stringOrNull(ObjectNode payload, String field) {
        JsonNode value = payload.get(field);
        if (!value.isNull() && !value.isTextual()) {
            throw new CliInputException(
                    "INVALID_FIELD", field + " 必须是字符串或 null");
        }
        return value;
    }

    private static void rejectUnexpectedFields(ObjectNode payload, Set<String> allowed) {
        TreeSet<String> unexpected = new TreeSet<>();
        payload.propertyNames().forEach(field -> {
            if (!allowed.contains(field)) unexpected.add(field);
        });
        if (!unexpected.isEmpty()) {
            throw new CliInputException(
                    "UNEXPECTED_FIELD", "命令不接受字段：" + unexpected.getFirst());
        }
    }
}
