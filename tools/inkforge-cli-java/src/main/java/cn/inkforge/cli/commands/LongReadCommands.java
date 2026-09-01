package cn.inkforge.cli.commands;

import cn.inkforge.cli.runtime.CliInputException;
import cn.inkforge.cli.runtime.CommandHandler;
import cn.inkforge.cli.runtime.CommandResult;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** 长篇公共只读命令；所有映射都显式登记，不使用命令名前缀猜路由。 */
public final class LongReadCommands {

    private LongReadCommands() {}

    public static void register(Map<String, CommandHandler> handlers) {
        handlers.put("long.novel.list", (context, payload) -> {
            Payloads.validateRead(payload, List.of(), List.of(), true);
            return get(
                    context,
                    "/api/v1/novels",
                    Map.of("storyLengthProfile", List.of("long_serial")));
        });
        handlers.put("long.novel.get", (context, payload) -> resource(
                context, payload, "novelId", "/api/v1/novels/"));
        handlers.put("long.chapter.list", (context, payload) -> nested(
                context, payload, "novelId", "/api/v1/novels/", "/chapters"));
        handlers.put("long.chapter.get", (context, payload) -> resource(
                context, payload, "chapterId", "/api/v1/chapters/"));
        handlers.put("long.session.list", (context, payload) -> {
            Payloads.validateRead(
                    payload, List.of("novelId"), List.of("chapterId"), true);
            return get(
                    context,
                    "/api/v1/writing/sessions",
                    Payloads.query(payload, "novelId", "chapterId"));
        });
        handlers.put("long.session.get", (context, payload) -> resource(
                context, payload, "sessionId", "/api/v1/writing/sessions/"));
        handlers.put("long.planning.get", (context, payload) -> workspace(
                context, payload, "planning"));
        handlers.put("long.lore.get", (context, payload) -> workspace(
                context, payload, "lore"));
        handlers.put("long.resources.get", (context, payload) -> workspace(
                context, payload, "resources"));
        handlers.put("long.outline-node.list", (context, payload) -> nested(
                context,
                payload,
                "novelId",
                "/api/v1/novels/",
                "/outline-nodes"));
        handlers.put("long.foreshadowing.list", (context, payload) -> nested(
                context,
                payload,
                "novelId",
                "/api/v1/novels/",
                "/foreshadowings"));
        handlers.put("long.task.list", LongReadCommands::listTasks);
        handlers.put("long.task.get", (context, payload) -> resource(
                context, payload, "taskId", "/api/v1/writing/runs/"));
        handlers.put("long.artifact.list", LongReadCommands::listArtifacts);
        handlers.put("long.artifact.get", LongReadCommands::getArtifact);
        handlers.put("long.quality.get", (context, payload) -> resource(
                context, payload, "checkId", "/api/v1/quality-checks/"));
        LongNovelCommands.register(handlers);
        LongChapterCommands.register(handlers);
        LongPlanningCommands.register(handlers);
        LongOutlineNodeCommands.register(handlers);
        LongStyleCommands.register(handlers);
        LongLoreEntityCommands.register(handlers);
        LongRelationshipCommands.register(handlers);
        LongReferenceCommands.register(handlers);
        LongTaskCommands.register(handlers);
        LongArtifactCommands.register(handlers);
        LongQualityCommands.register(handlers);
        LongWatchCommands.register(handlers);
    }

    private static CommandResult listTasks(
            cn.inkforge.cli.runtime.CommandContext context, ObjectNode payload) {
        String[] filters = {
            "novelId",
            "chapterId",
            "writingSessionId",
            "operation",
            "outcome",
            "cursor",
            "limit"
        };
        Payloads.validateRead(
                payload,
                List.of("novelId"),
                List.of(filters).subList(1, filters.length),
                true);
        return get(context, "/api/v1/writing/runs", Payloads.query(payload, filters));
    }

    private static CommandResult listArtifacts(
            cn.inkforge.cli.runtime.CommandContext context, ObjectNode payload) {
        String[] filters = {
            "novelId", "chapterId", "taskId", "status", "kind", "cursor", "limit"
        };
        Payloads.validateRead(
                payload,
                List.of("novelId"),
                List.of(filters).subList(1, filters.length),
                true);
        return get(
                context,
                "/api/v1/review-artifact-summaries",
                Payloads.query(payload, filters));
    }

    private static CommandResult getArtifact(
            cn.inkforge.cli.runtime.CommandContext context, ObjectNode payload) {
        Payloads.validateRead(
                payload,
                List.of("artifactId"),
                List.of("revision"),
                true);
        String path = "/api/v1/review-artifacts/"
                + Payloads.segment(Payloads.requireString(payload, "artifactId"));
        if (!payload.has("revision")) return get(context, path, Map.of());
        JsonNode value = payload.get("revision");
        if (value == null
                || !value.isIntegralNumber()
                || !value.canConvertToInt()
                || value.intValue() < 1) {
            throw new CliInputException(
                    "INVALID_ARTIFACT_REVISION",
                    "revision 必须是大于等于 1 的整数");
        }
        return get(
                context,
                path,
                Map.of("revision", List.of(Integer.toString(value.intValue()))));
    }

    private static CommandResult workspace(
            cn.inkforge.cli.runtime.CommandContext context,
            ObjectNode payload,
            String resource) {
        return nested(
                context,
                payload,
                "novelId",
                "/api/v1/novels/",
                "/workspace/" + resource);
    }

    private static CommandResult nested(
            cn.inkforge.cli.runtime.CommandContext context,
            ObjectNode payload,
            String field,
            String prefix,
            String suffix) {
        Payloads.validateRead(payload, new String[] {field}, new String[0]);
        return get(
                context,
                prefix + Payloads.segment(Payloads.requireString(payload, field)) + suffix,
                Map.of());
    }

    private static CommandResult resource(
            cn.inkforge.cli.runtime.CommandContext context,
            ObjectNode payload,
            String field,
            String prefix) {
        return nested(context, payload, field, prefix, "");
    }

    private static CommandResult get(
            cn.inkforge.cli.runtime.CommandContext context,
            String path,
            Map<String, List<String>> query) {
        return CommandResult.json(context.requireApi().request("GET", path, query, null));
    }
}
