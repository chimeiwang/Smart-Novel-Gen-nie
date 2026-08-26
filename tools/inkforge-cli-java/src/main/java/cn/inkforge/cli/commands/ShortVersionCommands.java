package cn.inkforge.cli.commands;

import cn.inkforge.cli.runtime.CliInputException;
import cn.inkforge.cli.runtime.CommandContext;
import cn.inkforge.cli.runtime.CommandHandler;
import cn.inkforge.cli.runtime.CommandResult;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** 中短篇候选版本预览、提交、比较与应用命令。 */
final class ShortVersionCommands {

    private static final Pattern SHA256 = Pattern.compile("[0-9a-f]{64}");
    private static final Set<String> LOCAL_FIELDS = Set.of(
            "profile",
            "novelId",
            "versionId",
            "outputFile",
            "outputDirectory",
            "manifestPath");

    private ShortVersionCommands() {}

    static void register(Map<String, CommandHandler> handlers) {
        handlers.put("short.version.preview", ShortVersionCommands::preview);
        handlers.put("short.version.submit", ShortVersionCommands::submit);
        handlers.put("short.version.list", ShortVersionCommands::list);
        handlers.put("short.version.diff", ShortVersionCommands::diff);
        handlers.put("short.version.get", ShortVersionCommands::get);
        handlers.put("short.version.adopt", (context, payload) ->
                apply(context, payload, "adopt"));
        handlers.put("short.version.restore", (context, payload) ->
                apply(context, payload, "restore"));
    }

    private static CommandResult preview(CommandContext context, ObjectNode payload) {
        JsonNode response = context.requireApi().request(
                "POST", root(payload) + "/versions/preview", remoteFields(payload));
        return CommandResult.json(ShortFileOutputs.responseField(
                context,
                payload,
                response,
                "diff",
                "version-preview-diff.json"));
    }

    private static CommandResult submit(CommandContext context, ObjectNode payload) {
        String novelId = Payloads.requireShortString(payload, "novelId");
        requireConfirmationHash(payload);
        snapshots(context).requireCleanManifest(payload, novelId);
        return CommandResult.json(context.requireApi().request(
                "POST",
                "/api/v1/novels/" + Payloads.segment(novelId) + "/versions",
                remoteFields(payload)));
    }

    private static CommandResult list(CommandContext context, ObjectNode payload) {
        ObjectNode queryPayload = remoteFields(payload);
        List<String> names = new ArrayList<>();
        queryPayload.propertyNames().forEach(names::add);
        return CommandResult.json(context.requireApi().request(
                "GET",
                root(payload) + "/versions",
                Payloads.query(queryPayload, names.toArray(String[]::new)),
                null));
    }

    private static CommandResult diff(CommandContext context, ObjectNode payload) {
        ObjectNode queryPayload = remoteFields(payload);
        List<String> names = new ArrayList<>();
        queryPayload.propertyNames().forEach(names::add);
        JsonNode response = context.requireApi().request(
                "GET",
                root(payload) + "/version-diff",
                Payloads.query(queryPayload, names.toArray(String[]::new)),
                null);
        if (!truthy(response)) return CommandResult.json(response);
        return CommandResult.json(ShortFileOutputs.wholeJson(
                context,
                payload,
                response,
                "version-diff.json",
                "diffFile"));
    }

    private static CommandResult get(CommandContext context, ObjectNode payload) {
        String root = root(payload);
        String versionId = Payloads.requireShortString(payload, "versionId");
        JsonNode response = context.requireApi().request(
                "GET", root + "/versions/" + Payloads.segment(versionId));
        return CommandResult.json(ShortFileOutputs.responseField(
                context,
                payload,
                response,
                "content",
                "version-" + versionId + ".txt"));
    }

    private static CommandResult apply(
            CommandContext context, ObjectNode payload, String action) {
        String novelId = Payloads.requireShortString(payload, "novelId");
        String versionId = Payloads.requireShortString(payload, "versionId");
        requireConfirmationHash(payload);
        snapshots(context).requireCleanManifest(payload, novelId);
        return CommandResult.json(context.requireApi().request(
                "POST",
                "/api/v1/novels/"
                        + Payloads.segment(novelId)
                        + "/versions/"
                        + Payloads.segment(versionId)
                        + "/"
                        + action,
                remoteFields(payload)));
    }

    private static String requireConfirmationHash(ObjectNode payload) {
        JsonNode value = payload.get("confirmationHash");
        if (value == null
                || !value.isTextual()
                || !SHA256.matcher(value.textValue()).matches()) {
            throw new CliInputException(
                    "INVALID_CONFIRMATION_HASH",
                    "confirmationHash 必须是 64 位小写 SHA-256");
        }
        return value.textValue();
    }

    private static ObjectNode remoteFields(ObjectNode payload) {
        ObjectNode result = payload.deepCopy();
        LOCAL_FIELDS.forEach(result::remove);
        return result;
    }

    private static String root(ObjectNode payload) {
        return "/api/v1/novels/"
                + Payloads.segment(Payloads.requireShortString(payload, "novelId"));
    }

    private static ShortSnapshotStore snapshots(CommandContext context) {
        return new ShortSnapshotStore(context.dependencies().json());
    }

    private static boolean truthy(JsonNode value) {
        if (value == null || value.isNull() || value.isMissingNode()) return false;
        if (value.isObject() || value.isArray()) return !value.isEmpty();
        if (value.isTextual()) return !value.textValue().isEmpty();
        if (value.isBoolean()) return value.booleanValue();
        if (value.isNumber()) return value.decimalValue().signum() != 0;
        return true;
    }
}
