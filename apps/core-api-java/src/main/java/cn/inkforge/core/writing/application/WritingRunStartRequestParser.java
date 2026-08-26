package cn.inkforge.core.writing.application;

import cn.inkforge.contracts.api.LongSerialStartWritingRunRequest;
import cn.inkforge.contracts.api.ShortMediumStartWritingRunRequest;
import cn.inkforge.contracts.api.StartWritingRunRequest;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.generated.model.WritingRunStartBody;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import java.time.OffsetDateTime;
import java.time.format.DateTimeParseException;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Pattern;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.DeserializationFeature;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/**
 * 对写作启动匿名 {@code anyOf} 做严格分支解析。
 *
 * <p>这里故意先检查原始 JSON 类型，再反序列化生成 DTO，避免 Jackson 把数字等输入静默强制转换为字符串；
 * 同时补足 OpenAPI 无法表达的 Pydantic 跨字段校验。
 */
public final class WritingRunStartRequestParser {

    private static final Pattern SHA256 = Pattern.compile("^[0-9a-f]{64}$");
    private static final Set<String> AGENTS =
            Set.of("设定", "剧情", "写作", "校验", "编辑");
    private static final Set<String> LEGACY_FIELDS = Set.of(
            "clientRequestId",
            "novelId",
            "chapterId",
            "writingSessionId",
            "targetWordCount",
            "selectedAgents",
            "userMessage");
    private static final Set<String> SHORT_MEDIUM_FIELDS = Set.of(
            "clientRequestId",
            "workflow",
            "novelId",
            "operation",
            "documentType",
            "chapterId",
            "baseVersionId",
            "sourceOutlineVersionId",
            "selectionStart",
            "selectionEnd",
            "selectedTextHash",
            "userInstruction");
    private static final Set<String> LONG_SERIAL_FIELDS = Set.of(
            "clientRequestId",
            "workflow",
            "novelId",
            "chapterId",
            "writingSessionId",
            "operation",
            "target",
            "scope",
            "selectionTarget",
            "selectionAttachmentMetadata",
            "targetWordCount",
            "userInstruction");
    private static final Set<String> SHORT_OPERATIONS = Set.of(
            "generate_outline", "generate_manuscript", "replace_selection", "full_check");
    private static final Set<String> LONG_OPERATIONS = Set.of(
            "answer_question",
            "create_lore",
            "revise_lore",
            "create_outline",
            "revise_outline",
            "plan_chapter",
            "write_chapter",
            "rewrite_scene",
            "rewrite_chapter_selection",
            "rewrite_outline_selection",
            "review_chapter",
            "manage_foreshadowing");
    private static final Set<String> SELECTION_OPERATIONS =
            Set.of("rewrite_chapter_selection", "rewrite_outline_selection");
    private static final Set<String> RESOURCE_TYPES =
            Set.of("chapter_content", "outline_content", "outline_node_content");

    private final ObjectMapper json;
    private final Validator validator;

    public WritingRunStartRequestParser(ObjectMapper json, Validator validator) {
        this.json = Objects.requireNonNull(json);
        this.validator = Objects.requireNonNull(validator);
    }

    public ParsedWritingRunStartRequest parse(WritingRunStartBody body) {
        JsonNode value = Objects.requireNonNull(body, "写作启动请求体不能为空").value();
        if (!value.isObject()) {
            throw validation("请求体必须是 JSON 对象");
        }
        JsonNode workflow = value.get("workflow");
        if (workflow == null) {
            validateLegacy(value);
            StartWritingRunRequest request = read(value, StartWritingRunRequest.class);
            validateBean(request);
            if (request.getSelectedAgents() == null) {
                request.setSelectedAgents(List.of(
                        StartWritingRunRequest.SelectedAgentsEnum.u,
                        StartWritingRunRequest.SelectedAgentsEnum.u2,
                        StartWritingRunRequest.SelectedAgentsEnum.u3,
                        StartWritingRunRequest.SelectedAgentsEnum.u4,
                        StartWritingRunRequest.SelectedAgentsEnum.u5));
            }
            return new ParsedWritingRunStartRequest.Legacy(request);
        }
        if (!workflow.isTextual()) {
            throw validation("workflow 类型无效");
        }
        return switch (workflow.textValue()) {
            case "short_medium" -> {
                validateShortMedium(value);
                ShortMediumStartWritingRunRequest request =
                        read(value, ShortMediumStartWritingRunRequest.class);
                validateBean(request);
                yield new ParsedWritingRunStartRequest.ShortMedium(request);
            }
            case "long_serial" -> {
                validateLongSerial(value);
                LongSerialStartWritingRunRequest request =
                        read(value, LongSerialStartWritingRunRequest.class);
                validateBean(request);
                yield new ParsedWritingRunStartRequest.LongSerial(request);
            }
            default -> throw validation("workflow 不属于已支持的写作管线");
        };
    }

    private void validateLegacy(JsonNode value) {
        exactFields(value, LEGACY_FIELDS);
        requiredText(value, "clientRequestId", 16, 128);
        requiredText(value, "novelId", 1, 256);
        requiredText(value, "chapterId", 1, 256);
        requiredText(value, "userMessage", 1, Integer.MAX_VALUE);
        nullableText(value, "writingSessionId", 1, 256);
        optionalInteger(value, "targetWordCount", 1, 10_000_000);
        JsonNode selectedAgents = value.get("selectedAgents");
        if (selectedAgents != null) {
            if (!selectedAgents.isArray()) {
                throw validation("selectedAgents 必须是数组");
            }
            for (JsonNode agent : selectedAgents) {
                if (!agent.isTextual() || !AGENTS.contains(agent.textValue())) {
                    throw validation("selectedAgents 包含无效 Agent");
                }
            }
        }
    }

    private void validateShortMedium(JsonNode value) {
        exactFields(value, SHORT_MEDIUM_FIELDS);
        requiredText(value, "clientRequestId", 16, 128);
        requiredConst(value, "workflow", "short_medium");
        requiredText(value, "novelId", 1, 256);
        String operation = requiredEnum(value, "operation", SHORT_OPERATIONS);
        String documentType = requiredEnum(value, "documentType", Set.of("outline", "manuscript"));
        nullableText(value, "chapterId", 1, 256);
        nullableText(value, "baseVersionId", 1, 256);
        nullableText(value, "sourceOutlineVersionId", 1, 256);
        optionalInteger(value, "selectionStart", 0, Integer.MAX_VALUE);
        optionalInteger(value, "selectionEnd", 0, Integer.MAX_VALUE);
        nullableHash(value, "selectedTextHash");
        nullableText(value, "userInstruction", 1, Integer.MAX_VALUE);

        boolean hasChapter = nonNull(value, "chapterId");
        if (("manuscript".equals(documentType) && !hasChapter)
                || ("outline".equals(documentType) && hasChapter)) {
            throw validation("中短篇文档与章节身份不匹配");
        }
        boolean hasSelection = nonNull(value, "selectionStart")
                || nonNull(value, "selectionEnd")
                || nonNull(value, "selectedTextHash");
        switch (operation) {
            case "generate_outline" -> {
                if (!"outline".equals(documentType)
                        || nonNull(value, "sourceOutlineVersionId")
                        || hasSelection) {
                    throw validation("生成大纲的文档身份无效");
                }
            }
            case "generate_manuscript" -> {
                if (!"manuscript".equals(documentType)
                        || !nonNull(value, "sourceOutlineVersionId")
                        || hasSelection) {
                    throw validation("生成正文必须绑定当前来源大纲版本");
                }
            }
            case "replace_selection" -> {
                if (!nonNull(value, "baseVersionId")
                        || !nonNull(value, "userInstruction")
                        || !nonNull(value, "selectionStart")
                        || !nonNull(value, "selectionEnd")
                        || !nonNull(value, "selectedTextHash")) {
                    throw validation("选区修改缺少不可变来源身份");
                }
                if (value.get("selectionStart").intValue()
                        >= value.get("selectionEnd").intValue()) {
                    throw validation("选区结束位置必须大于开始位置");
                }
            }
            case "full_check" -> {
                if (!"manuscript".equals(documentType)
                        || !nonNull(value, "baseVersionId")
                        || hasSelection) {
                    throw validation("全文检查必须绑定正文版本且不能携带选区");
                }
            }
            default -> throw new IllegalStateException("未覆盖的中短篇操作");
        }
    }

    private void validateLongSerial(JsonNode value) {
        exactFields(value, LONG_SERIAL_FIELDS);
        requiredText(value, "clientRequestId", 16, 128);
        requiredConst(value, "workflow", "long_serial");
        requiredText(value, "novelId", 1, 256);
        requiredText(value, "chapterId", 1, 256);
        nullableText(value, "writingSessionId", 1, 256);
        String operation = requiredEnum(value, "operation", LONG_OPERATIONS);
        validateTarget(requiredObject(value, "target"));
        validateScope(requiredObject(value, "scope"));
        optionalInteger(value, "targetWordCount", 1, 10_000_000);
        String instruction = requiredText(value, "userInstruction", 1, Integer.MAX_VALUE);
        if (instruction.isBlank()) {
            throw validation("用户要求不能为空白");
        }

        JsonNode selection = nullableObject(value, "selectionTarget");
        JsonNode attachment = nullableObject(value, "selectionAttachmentMetadata");
        if (selection != null) {
            validateSelectionTarget(selection);
        }
        if (attachment != null) {
            validateSelectionAttachment(attachment);
        }
        boolean selectionOperation = SELECTION_OPERATIONS.contains(operation);
        if (selectionOperation != (selection != null)) {
            throw validation(selectionOperation
                    ? "选区操作必须携带 selectionTarget"
                    : "普通长篇操作不能携带 selectionTarget");
        }
        if (!selectionOperation && attachment != null) {
            throw validation("普通长篇操作不能携带 selectionAttachmentMetadata");
        }
        if (attachment != null && selection == null) {
            throw validation("selectionAttachmentMetadata 必须绑定 selectionTarget");
        }
        if (selection != null) {
            String resourceType = selection.get("resourceType").textValue();
            if ("rewrite_chapter_selection".equals(operation)
                    && !"chapter_content".equals(resourceType)) {
                throw validation("章节选区操作只能指向章节正文");
            }
            if ("rewrite_outline_selection".equals(operation)
                    && !Set.of("outline_content", "outline_node_content")
                            .contains(resourceType)) {
                throw validation("大纲选区操作只能指向总纲或大纲节点正文");
            }
        }
    }

    private void validateTarget(JsonNode value) {
        exactFields(value, Set.of("type", "id"));
        requiredConst(value, "type", "chapter");
        requiredText(value, "id", 1, Integer.MAX_VALUE);
    }

    private void validateScope(JsonNode value) {
        String kind = requiredEnum(
                value, "kind", Set.of("chapter", "chapter_range", "outline_node", "novel"));
        switch (kind) {
            case "chapter" -> {
                exactFields(value, Set.of("kind", "chapterId"));
                requiredText(value, "chapterId", 1, Integer.MAX_VALUE);
            }
            case "chapter_range" -> {
                exactFields(value, Set.of("kind", "chapterStartOrder", "chapterEndOrder"));
                int start = requiredInteger(value, "chapterStartOrder", 0, Integer.MAX_VALUE);
                int end = requiredInteger(value, "chapterEndOrder", 0, Integer.MAX_VALUE);
                if (start > end) {
                    throw validation("章节范围起点不能晚于终点");
                }
            }
            case "outline_node" -> {
                exactFields(value, Set.of("kind", "outlineNodeId"));
                requiredText(value, "outlineNodeId", 1, Integer.MAX_VALUE);
            }
            case "novel" -> exactFields(value, Set.of("kind"));
            default -> throw new IllegalStateException("未覆盖的范围类型");
        }
    }

    private void validateSelectionTarget(JsonNode value) {
        exactFields(value, Set.of(
                "resourceType",
                "resourceId",
                "baseUpdatedAt",
                "baseContentHash",
                "selectionStart",
                "selectionEnd",
                "selectedTextHash"));
        requiredEnum(value, "resourceType", RESOURCE_TYPES);
        requiredText(value, "resourceId", 1, Integer.MAX_VALUE);
        requiredAwareDateTime(value, "baseUpdatedAt");
        requiredHash(value, "baseContentHash");
        int start = requiredInteger(value, "selectionStart", 0, Integer.MAX_VALUE);
        int end = requiredInteger(value, "selectionEnd", 0, Integer.MAX_VALUE);
        requiredHash(value, "selectedTextHash");
        if (start >= end) {
            throw validation("选区结束位置必须大于开始位置");
        }
    }

    private void validateSelectionAttachment(JsonNode value) {
        exactFields(value, Set.of(
                "resourceType",
                "resourceId",
                "sourceLabel",
                "baseUpdatedAt",
                "baseContentHash",
                "selectionStart",
                "selectionEnd",
                "selectedTextHash",
                "selectionPreview"));
        requiredEnum(value, "resourceType", RESOURCE_TYPES);
        requiredText(value, "resourceId", 1, Integer.MAX_VALUE);
        requiredText(value, "sourceLabel", 1, 256);
        requiredAwareDateTime(value, "baseUpdatedAt");
        requiredHash(value, "baseContentHash");
        int start = requiredInteger(value, "selectionStart", 0, Integer.MAX_VALUE);
        int end = requiredInteger(value, "selectionEnd", 0, Integer.MAX_VALUE);
        requiredHash(value, "selectedTextHash");
        requiredText(value, "selectionPreview", 1, 256);
        if (start >= end) {
            throw validation("选区结束位置必须大于开始位置");
        }
    }

    private <T> T read(JsonNode value, Class<T> type) {
        try {
            return json.readerFor(type)
                    .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
                    .readValue(value);
        } catch (JacksonException exception) {
            throw validation("请求体与写作分支契约不匹配");
        }
    }

    private <T> void validateBean(T value) {
        Set<ConstraintViolation<T>> violations = validator.validate(value);
        if (!violations.isEmpty()) {
            throw validation("请求体字段校验失败");
        }
    }

    private static void exactFields(JsonNode value, Set<String> allowed) {
        if (!value.isObject()) {
            throw validation("嵌套字段必须是 JSON 对象");
        }
        Set<String> actual = new LinkedHashSet<>();
        actual.addAll(value.propertyNames());
        actual.removeAll(allowed);
        if (!actual.isEmpty()) {
            throw validation("请求体包含不允许的字段");
        }
    }

    private static String requiredText(JsonNode value, String field, int min, int max) {
        JsonNode node = value.get(field);
        if (node == null || !node.isTextual()) {
            throw validation(field + " 必须是字符串");
        }
        int length = node.textValue().codePointCount(0, node.textValue().length());
        if (length < min || length > max) {
            throw validation(field + " 长度无效");
        }
        return node.textValue();
    }

    private static void nullableText(JsonNode value, String field, int min, int max) {
        JsonNode node = value.get(field);
        if (node == null || node.isNull()) {
            return;
        }
        requiredText(value, field, min, max);
    }

    private static String requiredEnum(JsonNode value, String field, Set<String> allowed) {
        String text = requiredText(value, field, 1, Integer.MAX_VALUE);
        if (!allowed.contains(text)) {
            throw validation(field + " 取值无效");
        }
        return text;
    }

    private static void requiredConst(JsonNode value, String field, String expected) {
        if (!expected.equals(requiredText(value, field, 1, Integer.MAX_VALUE))) {
            throw validation(field + " 取值无效");
        }
    }

    private static int requiredInteger(JsonNode value, String field, int min, int max) {
        JsonNode node = value.get(field);
        if (node == null || !node.isIntegralNumber() || !node.canConvertToInt()) {
            throw validation(field + " 必须是整数");
        }
        int number = node.intValue();
        if (number < min || number > max) {
            throw validation(field + " 范围无效");
        }
        return number;
    }

    private static void optionalInteger(JsonNode value, String field, int min, int max) {
        JsonNode node = value.get(field);
        // 冻结请求契约允许可选字段显式发送 JSON null；Jackson 的 NullNode 不是 Java null，不能把它
        // 交给必填整数校验。非空值仍必须保持严格类型和范围，不能开启字符串到整数的隐式转换。
        if (node != null && !node.isNull()) {
            requiredInteger(value, field, min, max);
        }
    }

    private static void requiredHash(JsonNode value, String field) {
        if (!SHA256.matcher(requiredText(value, field, 64, 64)).matches()) {
            throw validation(field + " 不是有效 SHA-256");
        }
    }

    private static void nullableHash(JsonNode value, String field) {
        JsonNode node = value.get(field);
        if (node == null || node.isNull()) {
            return;
        }
        requiredHash(value, field);
    }

    private static void requiredAwareDateTime(JsonNode value, String field) {
        String input = requiredText(value, field, 1, Integer.MAX_VALUE);
        try {
            OffsetDateTime.parse(input);
        } catch (DateTimeParseException exception) {
            throw validation(field + " 必须包含时区");
        }
    }

    private static JsonNode requiredObject(JsonNode value, String field) {
        JsonNode node = value.get(field);
        if (node == null || !node.isObject()) {
            throw validation(field + " 必须是对象");
        }
        return node;
    }

    private static JsonNode nullableObject(JsonNode value, String field) {
        JsonNode node = value.get(field);
        if (node == null || node.isNull()) {
            return null;
        }
        if (!node.isObject()) {
            throw validation(field + " 必须是对象");
        }
        return node;
    }

    private static boolean nonNull(JsonNode value, String field) {
        JsonNode node = value.get(field);
        return node != null && !node.isNull();
    }

    private static ApiException validation(String reason) {
        Map<String, Object> detail = new LinkedHashMap<>();
        detail.put("path", List.of("body"));
        detail.put("message", reason);
        detail.put("type", "validation_error");
        return new ApiException(
                422, "VALIDATION_ERROR", "请求参数校验失败", List.of(detail));
    }
}
