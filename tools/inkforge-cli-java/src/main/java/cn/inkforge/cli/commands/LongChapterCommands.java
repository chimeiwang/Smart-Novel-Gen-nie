package cn.inkforge.cli.commands;

import cn.inkforge.cli.runtime.CliInputException;
import cn.inkforge.cli.runtime.CommandHandler;
import cn.inkforge.cli.runtime.CommandResult;
import java.util.Map;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

final class LongChapterCommands {

    private LongChapterCommands() {}

    static void register(Map<String, CommandHandler> handlers) {
        handlers.put("long.chapter.create", LongChapterCommands::create);
        handlers.put("long.chapter.save", LongChapterCommands::save);
        handlers.put("long.chapter.status", LongChapterCommands::status);
        handlers.put("long.chapter.progress.save", LongChapterCommands::progress);
    }

    private static CommandResult create(
            cn.inkforge.cli.runtime.CommandContext context, ObjectNode payload) {
        String novelId = Payloads.segment(MutationPayloads.requireString(payload, "novelId"));
        return CommandResult.json(context.requireApi().request(
                "POST", "/api/v1/novels/" + novelId + "/chapters"));
    }

    private static CommandResult save(
            cn.inkforge.cli.runtime.CommandContext context, ObjectNode payload) {
        String path = chapterPath(payload);
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("title", MutationPayloads.requireString(payload, "title"));
        body.put("content", MutationPayloads.contentSource(payload));
        body.put(
                "expectedUpdatedAt",
                MutationPayloads.expectedUpdatedAt(payload, false));
        return CommandResult.json(context.requireApi().request("PATCH", path, body));
    }

    private static CommandResult status(
            cn.inkforge.cli.runtime.CommandContext context, ObjectNode payload) {
        String path = chapterPath(payload);
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("status", MutationPayloads.requireString(payload, "status"));
        body.put(
                "expectedUpdatedAt",
                MutationPayloads.expectedUpdatedAt(payload, false));
        return CommandResult.json(context.requireApi().request(
                "PATCH", path + "/status", body));
    }

    private static CommandResult progress(
            cn.inkforge.cli.runtime.CommandContext context, ObjectNode payload) {
        JsonNode content = payload.get("content");
        if (content == null || !content.isTextual()) {
            throw new CliInputException("FIELD_REQUIRED", "缺少字符串字段 content");
        }
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("content", content.textValue());
        String expected = MutationPayloads.expectedUpdatedAt(payload, true);
        if (expected == null) body.putNull("expectedUpdatedAt");
        else body.put("expectedUpdatedAt", expected);
        return CommandResult.json(context.requireApi().request(
                "PUT", chapterPath(payload) + "/progress", body));
    }

    private static String chapterPath(ObjectNode payload) {
        return "/api/v1/chapters/"
                + Payloads.segment(MutationPayloads.requireString(payload, "chapterId"));
    }
}
