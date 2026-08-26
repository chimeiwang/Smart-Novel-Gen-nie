package cn.inkforge.cli.commands;

import cn.inkforge.cli.runtime.CliInputException;
import cn.inkforge.cli.runtime.CommandHandler;
import cn.inkforge.cli.runtime.CommandResult;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

final class LongNovelCommands {

    private static final List<String> TEXT_FIELDS = List.of(
            "summary",
            "genre",
            "protagonist",
            "coreSellingPoint",
            "readerPromise",
            "firstChapterGoal");

    private LongNovelCommands() {}

    static void register(Map<String, CommandHandler> handlers) {
        handlers.put("long.novel.create", LongNovelCommands::create);
        handlers.put("long.novel.summary.save", LongNovelCommands::saveSummary);
    }

    private static CommandResult create(
            cn.inkforge.cli.runtime.CommandContext context, ObjectNode payload) {
        Set<String> allowed = new TreeSet<>(TEXT_FIELDS);
        allowed.addAll(Set.of("profile", "name", "targetTotalWordCount"));
        TreeSet<String> unknown = new TreeSet<>();
        payload.propertyNames().forEach(name -> {
            if (!allowed.contains(name)) unknown.add(name);
        });
        if (!unknown.isEmpty()) {
            throw new CliInputException(
                    "UNEXPECTED_FIELDS",
                    "命令包含不支持的字段：" + String.join(", ", unknown));
        }
        JsonNode name = payload.get("name");
        if (name == null || !name.isTextual() || name.textValue().trim().isEmpty()) {
            throw new CliInputException("FIELD_REQUIRED", "缺少非空字符串字段：name");
        }
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("name", name.textValue().trim());
        for (String field : TEXT_FIELDS) {
            if (!payload.has(field)) continue;
            JsonNode value = payload.get(field);
            if (!value.isNull() && !value.isTextual()) {
                throw new CliInputException("INVALID_FIELD", field + " 必须是字符串或 null");
            }
            body.set(field, value);
        }
        if (payload.has("targetTotalWordCount")) {
            JsonNode value = payload.get("targetTotalWordCount");
            if (!value.isNull() && (!value.isIntegralNumber() || value.longValue() <= 0)) {
                throw new CliInputException(
                        "INVALID_FIELD", "targetTotalWordCount 必须是大于 0 的整数或 null");
            }
            body.set("targetTotalWordCount", value);
        }
        body.put("storyLengthProfile", "long_serial");
        return CommandResult.json(context.requireApi().request("POST", "/api/v1/novels", body));
    }

    private static CommandResult saveSummary(
            cn.inkforge.cli.runtime.CommandContext context, ObjectNode payload) {
        MutationPayloads.requireFields(
                payload, Set.of("novelId", "summary", "expectedUpdatedAt"));
        JsonNode summary = payload.get("summary");
        if (!summary.isNull() && !summary.isTextual()) {
            throw new CliInputException("INVALID_FIELD", "summary 必须是字符串或 null");
        }
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.set("summary", summary);
        body.put(
                "expectedUpdatedAt",
                MutationPayloads.expectedUpdatedAt(payload, false));
        String novelId = Payloads.segment(MutationPayloads.requireString(payload, "novelId"));
        return CommandResult.json(context.requireApi().request(
                "PUT", "/api/v1/novels/" + novelId + "/summary", body));
    }
}
