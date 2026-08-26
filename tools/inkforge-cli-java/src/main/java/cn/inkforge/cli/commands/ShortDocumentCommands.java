package cn.inkforge.cli.commands;

import cn.inkforge.cli.runtime.CliInputException;
import cn.inkforge.cli.runtime.CommandContext;
import cn.inkforge.cli.runtime.CommandHandler;
import cn.inkforge.cli.runtime.CommandResult;
import cn.inkforge.cli.transport.CoreApi;
import cn.inkforge.cli.transport.CoreApiException;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** 中短篇作品与本地工作稿命令。 */
final class ShortDocumentCommands {

    private ShortDocumentCommands() {}

    static void register(Map<String, CommandHandler> handlers) {
        handlers.put("short.list", ShortDocumentCommands::list);
        handlers.put("short.create", ShortDocumentCommands::create);
        handlers.put("short.pull", ShortDocumentCommands::pull);
        handlers.put("short.draft.save", ShortDocumentCommands::draftSave);
    }

    private static CommandResult list(CommandContext context, ObjectNode payload) {
        JsonNode response = context.requireApi().request(
                "GET",
                "/api/v1/novels",
                Map.of("storyLengthProfile", List.of("short_medium")),
                null);
        if (response instanceof ObjectNode object
                && object.get("novels") != null
                && object.get("novels").isArray()) {
            return CommandResult.json(object);
        }
        ObjectNode wrapped = context.dependencies().json().createObjectNode();
        wrapped.set("novels", response);
        return CommandResult.json(wrapped);
    }

    private static CommandResult create(CommandContext context, ObjectNode payload) {
        ObjectNode body = payload.deepCopy();
        body.remove("profile");
        return CommandResult.json(context.requireApi().request(
                "POST", "/api/v1/novels", body));
    }

    private static CommandResult pull(CommandContext context, ObjectNode payload) {
        CoreApi api = context.requireApi();
        String novelId = Payloads.requireShortString(payload, "novelId");
        Path target = Path.of(Payloads.requireShortString(payload, "outputDirectory"));
        String root = "/api/v1/novels/" + Payloads.segment(novelId);
        JsonNode bootstrapResponse = api.request("GET", root + "/workspace/bootstrap");
        if (!(bootstrapResponse instanceof ObjectNode bootstrap)) {
            throw remoteContract(
                    "INVALID_BOOTSTRAP_RESPONSE", "作品工作区响应格式无效");
        }
        ObjectNode currentChapter = object(bootstrap.get("currentChapter"));
        if (currentChapter == null) {
            String fallbackChapterId = firstChapterId(bootstrap.get("chapters"));
            if (fallbackChapterId != null) {
                JsonNode fallback = api.request(
                        "GET",
                        root + "/workspace/bootstrap",
                        Map.of("chapterId", List.of(fallbackChapterId)),
                        null);
                if (fallback instanceof ObjectNode object) {
                    bootstrap = object;
                    currentChapter = object(object.get("currentChapter"));
                }
            }
        }
        if (currentChapter == null) {
            throw remoteContract(
                    "MANUSCRIPT_CHAPTER_MISSING", "中短篇作品缺少唯一全文章节");
        }

        JsonNode planningResponse = api.request("GET", root + "/workspace/planning");
        ObjectNode planning = object(planningResponse);
        ObjectNode outlineRecord = planning == null ? null : object(planning.get("outline"));
        String outline = documentContent(outlineRecord, "大纲");
        String manuscript = documentContent(currentChapter, "正文");
        String chapterId = text(currentChapter, "id");
        if (chapterId == null || chapterId.isEmpty()) {
            throw remoteContract(
                    "MANUSCRIPT_CHAPTER_MISSING", "全文章节缺少 id");
        }
        JsonNode outlineVersions = api.request(
                "GET",
                root + "/versions",
                Map.of("documentType", List.of("outline")),
                null);
        JsonNode manuscriptVersions = api.request(
                "GET",
                root + "/versions",
                Map.of(
                        "documentType", List.of("manuscript"),
                        "chapterId", List.of(chapterId)),
                null);

        ObjectNode metadata = context.dependencies().json().createObjectNode();
        metadata.put("chapterId", chapterId);
        copyOrNull(metadata, "outlineUpdatedAt", outlineRecord, "updatedAt");
        copyOrNull(metadata, "manuscriptUpdatedAt", currentChapter, "updatedAt");
        metadata.set("outlineVersions", outlineVersions.deepCopy());
        metadata.set("manuscriptVersions", manuscriptVersions.deepCopy());
        ShortSnapshotStore snapshots = new ShortSnapshotStore(context.dependencies().json());
        return CommandResult.json(snapshots.export(
                target, novelId, outline, manuscript, metadata));
    }

    private static CommandResult draftSave(CommandContext context, ObjectNode payload) {
        String novelId = Payloads.requireShortString(payload, "novelId");
        String documentType = Payloads.requireShortString(payload, "documentType");
        if (!SetHolder.DOCUMENT_TYPES.contains(documentType)) {
            throw new CliInputException(
                    "INVALID_DOCUMENT_TYPE",
                    "documentType 只能是 outline 或 manuscript");
        }
        Path filePath = Path.of(Payloads.requireShortString(payload, "filePath"))
                .toAbsolutePath()
                .normalize();
        Path manifestPath = Path.of(Payloads.requireShortString(payload, "manifestPath"))
                .toAbsolutePath()
                .normalize();
        ShortSnapshotStore snapshots = new ShortSnapshotStore(context.dependencies().json());
        ObjectNode manifest = snapshots.load(manifestPath, novelId);
        ObjectNode documents = (ObjectNode) manifest.get("documents");
        ObjectNode descriptor = (ObjectNode) documents.get(documentType);
        if (!descriptor.get("path").textValue().equals(filePath.toString())) {
            throw new CliInputException(
                    "INVALID_MANIFEST",
                    "filePath 与 manifest 中的文档路径不一致");
        }
        String content = snapshots.readUtf8(filePath);
        String updatedAtField = documentType.equals("outline")
                ? "outlineUpdatedAt"
                : "manuscriptUpdatedAt";
        String expectedUpdatedAt = text(manifest, updatedAtField);
        if (expectedUpdatedAt == null || expectedUpdatedAt.isEmpty()) {
            throw new CliInputException(
                    "INVALID_MANIFEST", "manifest 缺少 " + updatedAtField);
        }
        JsonNode response;
        if (documentType.equals("outline")) {
            ObjectNode body = context.dependencies().json().createObjectNode();
            body.put("content", content);
            body.put("expectedUpdatedAt", expectedUpdatedAt);
            response = context.requireApi().request(
                    "PUT",
                    "/api/v1/novels/" + Payloads.segment(novelId) + "/outline",
                    body);
        } else {
            String chapterId = text(manifest, "chapterId");
            if (chapterId == null || chapterId.isEmpty()) {
                throw new CliInputException(
                        "INVALID_MANIFEST", "manifest 缺少 chapterId");
            }
            String title = payload.has("title")
                    ? Payloads.requireShortString(payload, "title")
                    : "全文";
            ObjectNode body = context.dependencies().json().createObjectNode();
            body.put("title", title);
            body.put("content", content);
            body.put("expectedUpdatedAt", expectedUpdatedAt);
            response = context.requireApi().request(
                    "PATCH",
                    "/api/v1/chapters/" + Payloads.segment(chapterId),
                    body);
        }
        ObjectNode responseObject = object(response);
        String nextUpdatedAt = responseObject == null
                ? null
                : text(responseObject, "updatedAt");
        if (nextUpdatedAt == null || nextUpdatedAt.isEmpty()) {
            throw remoteContract(
                    "INVALID_DRAFT_SAVE_RESPONSE",
                    "工作稿保存响应缺少 updatedAt，未推进本地 manifest");
        }
        String contentHash = snapshots.advance(
                manifestPath,
                manifest,
                documentType,
                updatedAtField,
                nextUpdatedAt,
                content);
        ObjectNode result = responseObject.deepCopy();
        result.put("manifestPath", manifestPath.toString());
        result.put("contentHash", contentHash);
        return CommandResult.json(result);
    }

    private static String documentContent(ObjectNode record, String label) {
        if (record == null || !record.has("content")) return "";
        JsonNode content = record.get("content");
        if (!content.isTextual()) {
            throw remoteContract(
                    "INVALID_DOCUMENT_CONTENT",
                    "服务端返回了无效的" + label + "内容");
        }
        return content.textValue();
    }

    private static String firstChapterId(JsonNode chapters) {
        if (chapters == null || !chapters.isArray() || chapters.isEmpty()) return null;
        ObjectNode first = object(chapters.get(0));
        return first == null ? null : text(first, "id");
    }

    private static ObjectNode object(JsonNode value) {
        return value instanceof ObjectNode object ? object : null;
    }

    private static String text(ObjectNode value, String field) {
        JsonNode node = value.get(field);
        return node != null && node.isTextual() ? node.textValue() : null;
    }

    private static void copyOrNull(
            ObjectNode target,
            String targetField,
            ObjectNode source,
            String sourceField) {
        JsonNode value = source == null ? null : source.get(sourceField);
        if (value == null) target.putNull(targetField);
        else target.set(targetField, value.deepCopy());
    }

    private static CoreApiException remoteContract(String code, String message) {
        return new CoreApiException(500, code, message, null, null);
    }

    private static final class SetHolder {
        private static final java.util.Set<String> DOCUMENT_TYPES =
                java.util.Set.of("outline", "manuscript");
    }
}
