package cn.inkforge.cli.commands;

import cn.inkforge.cli.runtime.CliInputException;
import cn.inkforge.cli.runtime.CommandHandler;
import cn.inkforge.cli.runtime.CommandResult;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

final class LongReferenceCommands {

    private static final Set<String> TYPES = Set.of("note", "web", "book", "image", "custom");
    private static final Pattern SHA256 = Pattern.compile("[0-9a-f]{64}");

    private LongReferenceCommands() {}

    static void register(Map<String, CommandHandler> handlers) {
        handlers.put("long.reference.create", LongReferenceCommands::create);
        handlers.put("long.reference.update", LongReferenceCommands::update);
        handlers.put("long.reference.delete", LongReferenceCommands::delete);
        handlers.put("long.reference.reindex", LongReferenceCommands::reindex);
    }

    private static CommandResult create(
            cn.inkforge.cli.runtime.CommandContext context, ObjectNode payload) {
        MutationPayloads.requireFields(
                payload,
                Set.of("novelId", "clientRequestId", "title", "type"),
                Set.of("content", "contentFile", "sourceUrl"));
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("clientRequestId", MutationPayloads.clientRequestId(payload, 256));
        body.put("title", title(payload));
        body.put("type", type(payload));
        body.put("content", MutationPayloads.contentSource(payload));
        if (payload.has("sourceUrl")) body.set("sourceUrl", sourceUrl(payload));
        return CommandResult.json(context.requireApi().request("POST", collection(payload), body));
    }

    private static CommandResult update(
            cn.inkforge.cli.runtime.CommandContext context, ObjectNode payload) {
        Set<String> business = Set.of("title", "type", "sourceUrl", "content", "contentFile");
        MutationPayloads.requireFields(
                payload,
                Set.of("novelId", "referenceId", "expectedUpdatedAt"),
                business);
        boolean supplied = business.stream().anyMatch(payload::has);
        if (!supplied) throw new CliInputException("DATA_REQUIRED", "更新至少需要一个业务字段");
        ObjectNode body = context.dependencies().json().createObjectNode();
        if (payload.has("title")) body.put("title", title(payload));
        if (payload.has("type")) body.put("type", type(payload));
        if (payload.has("sourceUrl")) body.set("sourceUrl", sourceUrl(payload));
        if (payload.has("content") || payload.has("contentFile")) {
            body.put("content", MutationPayloads.contentSource(payload));
        }
        body.put("expectedUpdatedAt", MutationPayloads.expectedUpdatedAt(payload, false));
        return CommandResult.json(context.requireApi().request("PATCH", item(payload), body));
    }

    private static CommandResult delete(
            cn.inkforge.cli.runtime.CommandContext context, ObjectNode payload) {
        MutationPayloads.requireFields(
                payload, Set.of("novelId", "referenceId", "expectedUpdatedAt"));
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("expectedUpdatedAt", MutationPayloads.expectedUpdatedAt(payload, false));
        return CommandResult.json(context.requireApi().request("DELETE", item(payload), body));
    }

    private static CommandResult reindex(
            cn.inkforge.cli.runtime.CommandContext context, ObjectNode payload) {
        MutationPayloads.requireFields(
                payload, Set.of("novelId", "referenceId", "expectedContentHash"));
        String hash = MutationPayloads.requireString(payload, "expectedContentHash");
        if (!SHA256.matcher(hash).matches()) {
            throw new CliInputException(
                    "INVALID_CONTENT_HASH", "expectedContentHash 必须是 64 位小写十六进制字符串");
        }
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("expectedContentHash", hash);
        return CommandResult.json(context.requireApi().request("POST", item(payload) + "/reindex", body));
    }

    private static String title(ObjectNode payload) {
        String title = MutationPayloads.requireString(payload, "title");
        if (title.trim().isEmpty()) {
            throw new CliInputException("INVALID_REFERENCE_TITLE", "title 不能为空白字符串");
        }
        return title;
    }

    private static String type(ObjectNode payload) {
        String type = MutationPayloads.requireString(payload, "type");
        if (!TYPES.contains(type)) {
            throw new CliInputException(
                    "INVALID_REFERENCE_TYPE", "type 必须是 note、web、book、image 或 custom");
        }
        return type;
    }

    private static JsonNode sourceUrl(ObjectNode payload) {
        JsonNode value = payload.get("sourceUrl");
        if (!value.isNull() && !value.isTextual()) {
            throw new CliInputException(
                    "INVALID_SOURCE_URL", "sourceUrl 必须是字符串或显式 null");
        }
        return value;
    }

    private static String collection(ObjectNode payload) {
        return "/api/v1/novels/"
                + Payloads.segment(MutationPayloads.requireString(payload, "novelId"))
                + "/references";
    }

    private static String item(ObjectNode payload) {
        return collection(payload)
                + "/"
                + Payloads.segment(MutationPayloads.requireString(payload, "referenceId"));
    }
}
