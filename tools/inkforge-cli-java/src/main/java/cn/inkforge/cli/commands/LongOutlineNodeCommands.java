package cn.inkforge.cli.commands;

import cn.inkforge.cli.runtime.CliInputException;
import cn.inkforge.cli.runtime.CommandHandler;
import cn.inkforge.cli.runtime.CommandResult;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

final class LongOutlineNodeCommands {

    private static final Set<String> BUSINESS_FIELDS = Set.of(
            "title",
            "content",
            "kind",
            "status",
            "order",
            "parentId",
            "linkedChapterId",
            "estimatedWordCount",
            "actualWordCount",
            "chapterStartOrder",
            "chapterEndOrder");
    private static final Set<String> KINDS = Set.of("stage", "plot_unit", "chapter_group");
    private static final Set<String> STATUSES = Set.of("planned", "in_progress", "completed", "skipped");
    private static final Set<String> STRING_FIELDS =
            Set.of("title", "content", "parentId", "linkedChapterId");
    private static final Set<String> INTEGER_FIELDS = Set.of(
            "order",
            "estimatedWordCount",
            "actualWordCount",
            "chapterStartOrder",
            "chapterEndOrder");

    private LongOutlineNodeCommands() {}

    static void register(Map<String, CommandHandler> handlers) {
        handlers.put("long.outline-node.create", LongOutlineNodeCommands::create);
        handlers.put("long.outline-node.update", LongOutlineNodeCommands::update);
        handlers.put("long.outline-node.delete", LongOutlineNodeCommands::delete);
    }

    private static CommandResult create(
            cn.inkforge.cli.runtime.CommandContext context, ObjectNode payload) {
        MutationPayloads.requireFields(
                payload, Set.of("novelId", "clientRequestId", "data"));
        ObjectNode body = MutationPayloads.data(payload, BUSINESS_FIELDS);
        validate(body, true);
        body.put("clientRequestId", MutationPayloads.clientRequestId(payload, 256));
        return CommandResult.json(context.requireApi().request("POST", collection(payload), body));
    }

    private static CommandResult update(
            cn.inkforge.cli.runtime.CommandContext context, ObjectNode payload) {
        MutationPayloads.requireFields(
                payload, Set.of("novelId", "outlineNodeId", "expectedUpdatedAt", "data"));
        ObjectNode body = MutationPayloads.data(payload, BUSINESS_FIELDS);
        validate(body, false);
        body.put("expectedUpdatedAt", MutationPayloads.expectedUpdatedAt(payload, false));
        return CommandResult.json(context.requireApi().request("PATCH", item(payload), body));
    }

    private static CommandResult delete(
            cn.inkforge.cli.runtime.CommandContext context, ObjectNode payload) {
        MutationPayloads.requireFields(
                payload, Set.of("novelId", "outlineNodeId", "expectedUpdatedAt"));
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("expectedUpdatedAt", MutationPayloads.expectedUpdatedAt(payload, false));
        return CommandResult.json(context.requireApi().request("DELETE", item(payload), body));
    }

    private static void validate(ObjectNode data, boolean creating) {
        if (creating) {
            TreeSet<String> missing = new TreeSet<>();
            for (String field : Set.of("title", "kind")) {
                if (!data.has(field)) missing.add(field);
            }
            if (!missing.isEmpty()) {
                throw new CliInputException(
                        "FIELD_REQUIRED",
                        "data 缺少创建必填字段：" + String.join(", ", missing));
            }
        }
        for (String field : STRING_FIELDS) {
            JsonNode value = data.get(field);
            if (value != null && !value.isNull() && !value.isTextual()) {
                throw invalid("data." + field + " 必须是字符串或 null");
            }
        }
        JsonNode title = data.get("title");
        if (title != null
                && (!title.isTextual() || title.textValue().trim().isEmpty())) {
            throw invalid("data.title 必须是非空字符串");
        }
        JsonNode kind = data.get("kind");
        if (kind != null && (!kind.isTextual() || !KINDS.contains(kind.textValue()))) {
            throw invalid("data.kind 不是受支持的大纲节点类型");
        }
        JsonNode status = data.get("status");
        if (status != null
                && (!status.isTextual() || !STATUSES.contains(status.textValue()))) {
            throw invalid("data.status 不是受支持的大纲节点状态");
        }
        for (String field : INTEGER_FIELDS) {
            JsonNode value = data.get(field);
            if (value != null && !value.isNull() && !value.isIntegralNumber()) {
                throw invalid("data." + field + " 必须是整数或 null");
            }
        }
        for (String field : Set.of("estimatedWordCount", "actualWordCount")) {
            JsonNode value = data.get(field);
            if (value != null && value.isIntegralNumber() && value.longValue() < 0) {
                throw invalid("data." + field + " 不能小于 0");
            }
        }
        JsonNode start = data.get("chapterStartOrder");
        JsonNode end = data.get("chapterEndOrder");
        boolean hasStart = start != null && !start.isNull();
        boolean hasEnd = end != null && !end.isNull();
        if (creating && hasStart != hasEnd) throw invalid("章节范围必须同时提供起止序号");
        if (hasStart && hasEnd
                && (!start.isIntegralNumber()
                        || !end.isIntegralNumber()
                        || start.longValue() <= 0
                        || start.longValue() > end.longValue())) {
            throw invalid("章节范围必须是有效的正整数闭区间");
        }
    }

    private static String collection(ObjectNode payload) {
        return "/api/v1/novels/"
                + Payloads.segment(MutationPayloads.requireString(payload, "novelId"))
                + "/outline-nodes";
    }

    private static String item(ObjectNode payload) {
        return collection(payload)
                + "/"
                + Payloads.segment(MutationPayloads.requireString(payload, "outlineNodeId"));
    }

    private static CliInputException invalid(String message) {
        return new CliInputException("INVALID_DATA_FIELD", message);
    }
}
