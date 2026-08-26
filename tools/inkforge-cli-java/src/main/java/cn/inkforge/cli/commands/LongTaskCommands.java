package cn.inkforge.cli.commands;

import cn.inkforge.cli.runtime.CliInputException;
import cn.inkforge.cli.runtime.CommandContext;
import cn.inkforge.cli.runtime.CommandHandler;
import cn.inkforge.cli.runtime.CommandResult;
import java.math.BigInteger;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import java.util.regex.Pattern;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** 长篇 Agent 运行命令；选区身份在发起任务前完成本地一致性校验。 */
final class LongTaskCommands {

    private static final Set<String> OPERATIONS = Set.of(
            "plan_chapter",
            "write_chapter",
            "review_chapter",
            "rewrite_chapter_selection",
            "rewrite_outline_selection");
    private static final Set<String> SELECTION_OPERATIONS =
            Set.of("rewrite_chapter_selection", "rewrite_outline_selection");
    private static final Set<String> SELECTION_FIELDS = Set.of(
            "resourceType",
            "resourceId",
            "baseUpdatedAt",
            "baseContentHash",
            "selectionStart",
            "selectionEnd",
            "selectedTextHash");
    private static final Pattern SHA256 = Pattern.compile("[0-9a-f]{64}");

    private LongTaskCommands() {}

    static void register(Map<String, CommandHandler> handlers) {
        handlers.put("long.agent.start", LongTaskCommands::start);
        handlers.put("long.task.resume", LongTaskCommands::resume);
        handlers.put("long.task.cancel", LongTaskCommands::cancel);
    }

    private static CommandResult start(CommandContext context, ObjectNode payload) {
        MutationPayloads.requireFields(
                payload,
                Set.of(
                        "clientRequestId",
                        "novelId",
                        "chapterId",
                        "operation",
                        "target",
                        "scope",
                        "userInstruction"),
                Set.of(
                        "writingSessionId",
                        "selectionTarget",
                        "targetWordCount"));
        String clientRequestId = MutationPayloads.clientRequestId(payload, 128);
        String novelId = MutationPayloads.requireString(payload, "novelId");
        String chapterId = MutationPayloads.requireString(payload, "chapterId");
        String operation = MutationPayloads.requireString(payload, "operation");
        if (!OPERATIONS.contains(operation)) {
            throw new CliInputException(
                    "INVALID_OPERATION",
                    "operation 不是受支持的长篇 Agent 操作");
        }
        ObjectNode target = requireObject(payload, "target", "INVALID_TARGET");
        if (!textEquals(target, "type", "chapter")
                || !textEquals(target, "id", chapterId)) {
            throw new CliInputException(
                    "INVALID_TARGET", "target 必须指向 chapterId 对应章节");
        }
        ObjectNode selection = selectionTarget(payload, operation, chapterId);
        ObjectNode scope = requireObject(payload, "scope", "INVALID_SCOPE");
        validateScope(scope, operation, chapterId, selection);
        String instruction = MutationPayloads.requireString(payload, "userInstruction");
        if (instruction.trim().isEmpty()) {
            throw new CliInputException(
                    "INVALID_USER_INSTRUCTION", "userInstruction 不能为空白");
        }

        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("clientRequestId", clientRequestId);
        body.put("workflow", "long_serial");
        body.put("novelId", novelId);
        body.put("chapterId", chapterId);
        body.put("operation", operation);
        body.set("target", target.deepCopy());
        body.set("scope", scope.deepCopy());
        body.put("userInstruction", instruction);
        if (selection != null) body.set("selectionTarget", selection.deepCopy());
        if (payload.has("writingSessionId")) {
            body.set(
                    "writingSessionId",
                    optionalNonEmptyStringOrNull(payload, "writingSessionId"));
        }
        if (payload.has("targetWordCount")) {
            body.set("targetWordCount", payload.get("targetWordCount").deepCopy());
        }
        return post(context, "/api/v1/writing/runs", body);
    }

    private static CommandResult resume(CommandContext context, ObjectNode payload) {
        MutationPayloads.requireFields(
                payload,
                Set.of("taskId", "clientRequestId"),
                Set.of("writingSessionId", "userMessage"));
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("clientRequestId", MutationPayloads.clientRequestId(payload, 128));
        if (payload.has("writingSessionId")) {
            body.set(
                    "writingSessionId",
                    optionalNonEmptyStringOrNull(payload, "writingSessionId"));
        }
        if (payload.has("userMessage")) {
            body.set("userMessage", stringOrNull(payload, "userMessage"));
        }
        return post(
                context,
                "/api/v1/writing/runs/"
                        + Payloads.segment(MutationPayloads.requireString(payload, "taskId"))
                        + "/resume",
                body);
    }

    private static CommandResult cancel(CommandContext context, ObjectNode payload) {
        MutationPayloads.requireFields(payload, Set.of("taskId", "clientRequestId"));
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("clientRequestId", MutationPayloads.clientRequestId(payload, 128));
        return post(
                context,
                "/api/v1/writing/runs/"
                        + Payloads.segment(MutationPayloads.requireString(payload, "taskId"))
                        + "/cancel",
                body);
    }

    private static ObjectNode selectionTarget(
            ObjectNode payload, String operation, String chapterId) {
        JsonNode raw = payload.get("selectionTarget");
        if (!SELECTION_OPERATIONS.contains(operation)) {
            if (raw != null && !raw.isNull()) {
                throw new CliInputException(
                        "SELECTION_TARGET_FORBIDDEN",
                        "普通长篇操作不能携带 selectionTarget");
            }
            return null;
        }
        if (!(raw instanceof ObjectNode selection)) {
            throw new CliInputException(
                    "SELECTION_TARGET_REQUIRED", "选区操作必须携带 selectionTarget");
        }
        TreeSet<String> unknown = new TreeSet<>();
        selection.propertyNames().forEach(field -> {
            if (!SELECTION_FIELDS.contains(field)) unknown.add(field);
        });
        if (!unknown.isEmpty()) {
            throw new CliInputException(
                    "UNEXPECTED_FIELD",
                    "selectionTarget 不接受字段：" + unknown.getFirst());
        }
        String resourceType = selectionString(selection, "resourceType");
        String resourceId = selectionString(selection, "resourceId");
        selectionString(selection, "baseUpdatedAt");
        if (!Set.of("chapter_content", "outline_content", "outline_node_content")
                .contains(resourceType)) {
            throw invalidSelection("resourceType 无效");
        }
        if (operation.equals("rewrite_chapter_selection")
                && !resourceType.equals("chapter_content")) {
            throw invalidSelection("章节选区只能指向 chapter_content");
        }
        if (operation.equals("rewrite_outline_selection")
                && !Set.of("outline_content", "outline_node_content").contains(resourceType)) {
            throw invalidSelection("大纲选区只能指向大纲正文");
        }
        if (resourceType.equals("chapter_content") && !resourceId.equals(chapterId)) {
            throw invalidSelection("章节选区 resourceId 必须等于 chapterId");
        }
        for (String field : Set.of("baseContentHash", "selectedTextHash")) {
            String hash = selectionString(selection, field);
            if (!SHA256.matcher(hash).matches()) {
                throw invalidSelection(field + " 必须是 64 位小写 SHA-256");
            }
        }
        JsonNode startNode = selection.get("selectionStart");
        JsonNode endNode = selection.get("selectionEnd");
        if (startNode == null
                || endNode == null
                || !startNode.isIntegralNumber()
                || !endNode.isIntegralNumber()) {
            throw invalidSelection("选区必须是非空的正向码点范围");
        }
        BigInteger start = startNode.bigIntegerValue();
        BigInteger end = endNode.bigIntegerValue();
        if (start.signum() < 0 || end.compareTo(start) <= 0) {
            throw invalidSelection("选区必须是非空的正向码点范围");
        }
        return selection;
    }

    private static void validateScope(
            ObjectNode scope,
            String operation,
            String chapterId,
            ObjectNode selection) {
        if (!operation.equals("rewrite_outline_selection")) {
            if (!textEquals(scope, "kind", "chapter")
                    || !textEquals(scope, "chapterId", chapterId)) {
                throw new CliInputException(
                        "INVALID_SCOPE", "scope 必须是 chapterId 对应章节范围");
            }
            return;
        }
        if (selection == null) {
            throw new CliInputException("INVALID_SCOPE", "大纲选区 scope 无效");
        }
        String expectedKind = selection.get("resourceType").textValue().equals("outline_content")
                ? "novel"
                : "outline_node";
        if (!textEquals(scope, "kind", expectedKind)) {
            throw new CliInputException(
                    "INVALID_SCOPE", "大纲选区 scope 必须匹配资源身份");
        }
        if (expectedKind.equals("outline_node")
                && !textEquals(
                        scope,
                        "outlineNodeId",
                        selection.get("resourceId").textValue())) {
            throw new CliInputException(
                    "INVALID_SCOPE",
                    "outlineNodeId 必须匹配 selectionTarget.resourceId");
        }
    }

    private static ObjectNode requireObject(
            ObjectNode payload, String field, String code) {
        JsonNode value = payload.get(field);
        if (!(value instanceof ObjectNode object)) {
            throw new CliInputException(code, field + " 必须是 JSON 对象");
        }
        return object;
    }

    private static String selectionString(ObjectNode selection, String field) {
        JsonNode value = selection.get(field);
        if (value == null || !value.isTextual() || value.textValue().isEmpty()) {
            throw invalidSelection(field + " 必须是非空字符串");
        }
        return value.textValue();
    }

    private static JsonNode optionalNonEmptyStringOrNull(
            ObjectNode payload, String field) {
        JsonNode value = payload.get(field);
        if (value.isNull()) return value;
        if (!value.isTextual() || value.textValue().isEmpty()) {
            throw new CliInputException(
                    "INVALID_FIELD", field + " 必须是非空字符串或 null");
        }
        return value;
    }

    private static JsonNode stringOrNull(ObjectNode payload, String field) {
        JsonNode value = payload.get(field);
        if (!value.isNull() && !value.isTextual()) {
            throw new CliInputException(
                    "INVALID_FIELD", field + " 必须是字符串或 null");
        }
        return value;
    }

    private static boolean textEquals(ObjectNode value, String field, String expected) {
        JsonNode actual = value.get(field);
        return actual != null && actual.isTextual() && actual.textValue().equals(expected);
    }

    private static CliInputException invalidSelection(String message) {
        return new CliInputException("INVALID_SELECTION_TARGET", message);
    }

    private static CommandResult post(
            CommandContext context, String path, ObjectNode body) {
        return CommandResult.json(context.requireApi().request("POST", path, body));
    }
}
