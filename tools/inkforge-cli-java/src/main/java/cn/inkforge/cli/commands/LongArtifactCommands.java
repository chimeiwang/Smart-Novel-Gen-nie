package cn.inkforge.cli.commands;

import cn.inkforge.cli.runtime.CliInputException;
import cn.inkforge.cli.runtime.CommandContext;
import cn.inkforge.cli.runtime.CommandHandler;
import cn.inkforge.cli.runtime.CommandResult;
import cn.inkforge.cli.transport.CoreApiException;
import cn.inkforge.cli.transport.CoreResponseContractException;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** ReviewArtifact 决策命令；来源绑定验证与编辑类型门禁不能被普通 CRUD 绕过。 */
final class LongArtifactCommands {

    private static final Set<String> OPTIONAL_FIELDS = Set.of(
            "editedContent",
            "editedContentFile",
            "editedReplacement",
            "editedReplacementFile",
            "selectedUpdateRefs",
            "userMessage");
    private static final Set<String> EDIT_FIELDS = Set.of(
            "editedContent",
            "editedContentFile",
            "editedReplacement",
            "editedReplacementFile",
            "selectedUpdateRefs");
    private static final Set<String> SELECTION_MODES = Set.of(
            "replace_selection",
            "outline_content_selection",
            "outline_node_content_selection");

    private LongArtifactCommands() {}

    static void register(Map<String, CommandHandler> handlers) {
        handlers.put("long.artifact.approve", (context, payload) ->
                decide(context, payload, "approve"));
        handlers.put("long.artifact.revise", (context, payload) ->
                decide(context, payload, "revise"));
        handlers.put("long.artifact.discard", (context, payload) ->
                decide(context, payload, "discard"));
    }

    private static CommandResult decide(
            CommandContext context, ObjectNode payload, String decision) {
        MutationPayloads.requireFields(
                payload,
                Set.of("artifactId", "clientRequestId", "expectedRevision"),
                OPTIONAL_FIELDS);
        MutationPayloads.clientRequestId(payload, 128);
        expectedRevision(payload);
        preflightLocalDecision(payload, decision);
        String artifactId = MutationPayloads.requireString(payload, "artifactId");
        String artifactPath =
                "/api/v1/review-artifacts/" + Payloads.segment(artifactId);
        ObjectNode artifact = null;
        if (!decision.equals("discard")) {
            artifact = verifiedArtifact(context, artifactId, artifactPath);
        }
        ObjectNode body = decisionBody(context, payload, decision, artifact);
        return CommandResult.json(context.requireApi().request(
                "POST", artifactPath + "/decision", body));
    }

    private static void preflightLocalDecision(ObjectNode payload, String decision) {
        if (decision.equals("discard")) {
            TreeSet<String> forbidden = presentFields(payload, EDIT_FIELDS);
            if (!forbidden.isEmpty()) {
                throw new CliInputException(
                        "DISCARD_EDIT_FIELDS_FORBIDDEN",
                        "discard 不接受字段：" + forbidden.getFirst());
            }
            validateUserMessage(payload, false);
            return;
        }
        rejectNonNullPair(
                payload,
                "editedContent",
                "editedContentFile",
                "EDITED_CONTENT_CONFLICT",
                "editedContent 与 editedContentFile 至多提供一个");
        rejectNonNullPair(
                payload,
                "editedReplacement",
                "editedReplacementFile",
                "EDITED_REPLACEMENT_CONFLICT",
                "editedReplacement 与 editedReplacementFile 至多提供一个");
        if (nonNull(payload, "editedContent")
                && nonNull(payload, "editedReplacement")) {
            throw new CliInputException(
                    "EDITED_FIELDS_CONFLICT",
                    "editedContent 与 editedReplacement 不能同时提供");
        }
        validateUserMessage(payload, decision.equals("revise"));
    }

    private static ObjectNode verifiedArtifact(
            CommandContext context, String artifactId, String path) {
        JsonNode response = context.requireApi().request("GET", path);
        if (!(response instanceof ObjectNode artifact)) {
            throw new CoreResponseContractException("Artifact 响应不是 JSON 对象");
        }
        JsonNode status = artifact.get("sourceBindingStatus");
        if (status != null && status.isTextual() && status.textValue().equals("verified")) {
            return artifact;
        }
        if (status != null
                && status.isTextual()
                && Set.of("legacy_missing", "not_yet_supported").contains(status.textValue())) {
            ObjectNode details = context.dependencies().json().createObjectNode();
            details.put("artifactId", artifactId);
            details.put("sourceBindingStatus", status.textValue());
            throw new CoreApiException(
                    409,
                    "SOURCE_BINDING_NOT_VERIFIED",
                    "草案缺少可验证的来源绑定，拒绝执行该决定",
                    details,
                    null);
        }
        throw new CoreResponseContractException(
                "Artifact 响应缺少有效 sourceBindingStatus");
    }

    private static ObjectNode decisionBody(
            CommandContext context,
            ObjectNode payload,
            String decision,
            ObjectNode artifact) {
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("clientRequestId", MutationPayloads.clientRequestId(payload, 128));
        body.put("expectedRevision", expectedRevision(payload));
        body.put("decision", decision);
        if (!decision.equals("discard")) {
            String editedContent = editedContent(payload);
            String editedReplacement = editedReplacement(payload);
            if (editedContent != null && editedReplacement != null) {
                throw new CliInputException(
                        "EDITED_FIELDS_CONFLICT",
                        "editedContent 与 editedReplacement 不能同时提供");
            }
            boolean selection = selectionArtifact(artifact);
            if (selection && editedContent != null) {
                throw new CliInputException(
                        "SELECTION_EDITED_CONTENT_FORBIDDEN",
                        "选区草案只能提供 editedReplacement");
            }
            if (!selection && editedReplacement != null) {
                throw new CliInputException(
                        "FULL_EDITED_REPLACEMENT_FORBIDDEN",
                        "全文草案只能提供 editedContent");
            }
            if (editedContent != null) body.put("editedContent", editedContent);
            if (editedReplacement != null) {
                body.put("editedReplacement", editedReplacement);
            }
            if (payload.has("selectedUpdateRefs")) {
                body.set(
                        "selectedUpdateRefs",
                        payload.get("selectedUpdateRefs").deepCopy());
            }
        }
        if (payload.has("userMessage")) {
            body.set("userMessage", userMessage(payload));
        }
        if (decision.equals("revise")) {
            JsonNode message = body.get("userMessage");
            if (message == null
                    || !message.isTextual()
                    || message.textValue().trim().isEmpty()) {
                throw new CliInputException(
                        "USER_MESSAGE_REQUIRED",
                        "revise 必须提供非空 userMessage");
            }
        }
        return body;
    }

    private static int expectedRevision(ObjectNode payload) {
        JsonNode value = payload.get("expectedRevision");
        if (value == null || !value.isIntegralNumber() || !value.canConvertToInt()) {
            throw new CliInputException(
                    "INVALID_EXPECTED_REVISION",
                    "expectedRevision 必须是大于等于 1 的整数");
        }
        int revision = value.intValue();
        if (revision < 1) {
            throw new CliInputException(
                    "INVALID_EXPECTED_REVISION",
                    "expectedRevision 必须是大于等于 1 的整数");
        }
        return revision;
    }

    private static String editedContent(ObjectNode payload) {
        JsonNode inline = payload.get("editedContent");
        JsonNode file = payload.get("editedContentFile");
        if (inline != null && !inline.isNull() && file != null && !file.isNull()) {
            throw new CliInputException(
                    "EDITED_CONTENT_CONFLICT",
                    "editedContent 与 editedContentFile 至多提供一个");
        }
        if (inline != null && !inline.isNull()) {
            if (!inline.isTextual()) {
                throw new CliInputException(
                        "INVALID_EDITED_CONTENT",
                        "editedContent 必须是字符串或 null");
            }
            return inline.textValue();
        }
        if (file != null && !file.isNull()) {
            if (!file.isTextual() || file.textValue().isEmpty()) {
                throw new CliInputException(
                        "INVALID_EDITED_CONTENT_FILE",
                        "editedContentFile 必须是非空字符串");
            }
            return MutationPayloads.readUtf8(file.textValue());
        }
        return null;
    }

    private static String editedReplacement(ObjectNode payload) {
        JsonNode inline = payload.get("editedReplacement");
        JsonNode file = payload.get("editedReplacementFile");
        if (inline != null && !inline.isNull() && file != null && !file.isNull()) {
            throw new CliInputException(
                    "EDITED_REPLACEMENT_CONFLICT",
                    "editedReplacement 与 editedReplacementFile 至多提供一个");
        }
        if (inline != null && !inline.isNull()) {
            if (!inline.isTextual() || inline.textValue().trim().isEmpty()) {
                throw new CliInputException(
                        "INVALID_EDITED_REPLACEMENT",
                        "editedReplacement 必须是非空字符串或 null");
            }
            return inline.textValue();
        }
        if (file != null && !file.isNull()) {
            if (!file.isTextual() || file.textValue().isEmpty()) {
                throw new CliInputException(
                        "INVALID_EDITED_REPLACEMENT_FILE",
                        "editedReplacementFile 必须是非空字符串");
            }
            String content = MutationPayloads.readUtf8(file.textValue());
            if (content.trim().isEmpty()) {
                throw new CliInputException(
                        "INVALID_EDITED_REPLACEMENT",
                        "editedReplacementFile 内容不能为空");
            }
            return content;
        }
        return null;
    }

    private static boolean selectionArtifact(ObjectNode artifact) {
        JsonNode payload = artifact == null ? null : artifact.get("payload");
        JsonNode target = payload != null && payload.isObject() ? payload.get("target") : null;
        JsonNode mode = target != null && target.isObject() ? target.get("mode") : null;
        return mode != null && mode.isTextual() && SELECTION_MODES.contains(mode.textValue());
    }

    private static void validateUserMessage(ObjectNode payload, boolean required) {
        JsonNode message = payload.get("userMessage");
        if (message != null && !message.isNull() && !message.isTextual()) {
            throw new CliInputException(
                    "INVALID_USER_MESSAGE", "userMessage 必须是字符串或 null");
        }
        if (required
                && (message == null
                        || !message.isTextual()
                        || message.textValue().trim().isEmpty())) {
            throw new CliInputException(
                    "USER_MESSAGE_REQUIRED", "revise 必须提供非空 userMessage");
        }
    }

    private static JsonNode userMessage(ObjectNode payload) {
        validateUserMessage(payload, false);
        return payload.get("userMessage");
    }

    private static void rejectNonNullPair(
            ObjectNode payload,
            String left,
            String right,
            String code,
            String message) {
        if (nonNull(payload, left) && nonNull(payload, right)) {
            throw new CliInputException(code, message);
        }
    }

    private static boolean nonNull(ObjectNode payload, String field) {
        JsonNode value = payload.get(field);
        return value != null && !value.isNull();
    }

    private static TreeSet<String> presentFields(
            ObjectNode payload, Set<String> fields) {
        TreeSet<String> present = new TreeSet<>();
        fields.forEach(field -> {
            if (payload.has(field)) present.add(field);
        });
        return present;
    }
}
