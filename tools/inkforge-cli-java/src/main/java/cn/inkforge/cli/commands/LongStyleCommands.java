package cn.inkforge.cli.commands;

import cn.inkforge.cli.runtime.CliInputException;
import cn.inkforge.cli.runtime.CommandHandler;
import cn.inkforge.cli.runtime.CommandResult;
import java.util.Map;
import java.util.Set;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

final class LongStyleCommands {

    private LongStyleCommands() {}

    static void register(Map<String, CommandHandler> handlers) {
        handlers.put("long.style.apply", (context, payload) -> {
            MutationPayloads.requireFields(
                    payload, Set.of("novelId", "styleId", "expectedStyleId"));
            return set(context, payload, MutationPayloads.requireString(payload, "styleId"));
        });
        handlers.put("long.style.clear", (context, payload) -> {
            MutationPayloads.requireFields(payload, Set.of("novelId", "expectedStyleId"));
            return set(context, payload, null);
        });
    }

    private static CommandResult set(
            cn.inkforge.cli.runtime.CommandContext context,
            ObjectNode payload,
            String styleId) {
        JsonNode expected = payload.get("expectedStyleId");
        if (!expected.isNull() && !expected.isTextual()) {
            throw new CliInputException(
                    "INVALID_EXPECTED_STYLE_ID",
                    "expectedStyleId 必须是字符串或显式 null");
        }
        ObjectNode body = context.dependencies().json().createObjectNode();
        if (styleId == null) body.putNull("styleId");
        else body.put("styleId", styleId);
        body.set("expectedStyleId", expected);
        String path = "/api/v1/novels/"
                + Payloads.segment(MutationPayloads.requireString(payload, "novelId"))
                + "/applied-style";
        return CommandResult.json(context.requireApi().request("PATCH", path, body));
    }
}
