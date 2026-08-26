package cn.inkforge.cli.commands;

import cn.inkforge.cli.runtime.CliInputException;
import cn.inkforge.cli.runtime.CommandHandler;
import cn.inkforge.cli.runtime.CommandResult;
import java.util.Map;
import java.util.Set;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

final class LongPlanningCommands {

    private static final Set<String> WRITING_BIBLE_FIELDS = Set.of(
            "storyLengthProfile",
            "targetTotalWordCount",
            "genre",
            "targetReaders",
            "coreSellingPoint",
            "readerPromise",
            "appealModel",
            "taboo",
            "comparableTitles",
            "notes");
    private static final Set<String> PLOT_PROGRESS_FIELDS = Set.of(
            "currentStage",
            "currentGoal",
            "currentConflict",
            "nextMilestone");

    private LongPlanningCommands() {}

    static void register(Map<String, CommandHandler> handlers) {
        handlers.put("long.outline.save", (context, payload) ->
                saveText(context, payload, "outline", false));
        handlers.put("long.lore.story-background.save", (context, payload) ->
                saveText(context, payload, "story-background", true));
        handlers.put("long.lore.world-setting.save", (context, payload) ->
                saveText(context, payload, "world-setting", true));
        handlers.put("long.lore.story-progress.save", (context, payload) ->
                saveText(context, payload, "story-progress", true));
        handlers.put("long.lore.writing-bible.save", LongPlanningCommands::writingBible);
        handlers.put("long.plot-progress.save", LongPlanningCommands::plotProgress);
    }

    private static CommandResult saveText(
            cn.inkforge.cli.runtime.CommandContext context,
            ObjectNode payload,
            String suffix,
            boolean nullable) {
        MutationPayloads.requireFields(
                payload,
                Set.of("novelId", "expectedUpdatedAt"),
                Set.of("content", "contentFile"));
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("content", MutationPayloads.contentSource(payload));
        String expected = MutationPayloads.expectedUpdatedAt(payload, nullable);
        if (expected == null) body.putNull("expectedUpdatedAt");
        else body.put("expectedUpdatedAt", expected);
        return CommandResult.json(context.requireApi().request(
                "PUT", planningPath(payload, suffix), body));
    }

    private static CommandResult writingBible(
            cn.inkforge.cli.runtime.CommandContext context, ObjectNode payload) {
        MutationPayloads.requireFields(
                payload, Set.of("novelId", "expectedUpdatedAt", "data"));
        ObjectNode body = MutationPayloads.data(payload, WRITING_BIBLE_FIELDS);
        JsonNode profile = body.get("storyLengthProfile");
        if (profile != null
                && (!profile.isTextual() || !"long_serial".equals(profile.textValue()))) {
            throw new CliInputException(
                    "INVALID_STORY_LENGTH_PROFILE",
                    "长篇作品圣经的 storyLengthProfile 必须严格等于字符串 long_serial");
        }
        setExpected(body, MutationPayloads.expectedUpdatedAt(payload, true));
        return CommandResult.json(context.requireApi().request(
                "PUT", planningPath(payload, "writing-bible"), body));
    }

    private static CommandResult plotProgress(
            cn.inkforge.cli.runtime.CommandContext context, ObjectNode payload) {
        MutationPayloads.requireFields(
                payload, Set.of("novelId", "expectedUpdatedAt", "data"));
        ObjectNode body = MutationPayloads.data(payload, PLOT_PROGRESS_FIELDS);
        MutationPayloads.requireString(body, "currentStage");
        setExpected(body, MutationPayloads.expectedUpdatedAt(payload, true));
        return CommandResult.json(context.requireApi().request(
                "PUT", planningPath(payload, "plot-progress"), body));
    }

    private static String planningPath(ObjectNode payload, String suffix) {
        return "/api/v1/novels/"
                + Payloads.segment(MutationPayloads.requireString(payload, "novelId"))
                + "/"
                + suffix;
    }

    private static void setExpected(ObjectNode body, String expected) {
        if (expected == null) body.putNull("expectedUpdatedAt");
        else body.put("expectedUpdatedAt", expected);
    }
}
