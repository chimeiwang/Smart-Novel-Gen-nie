package cn.inkforge.cli.commands;

import cn.inkforge.cli.runtime.CliInputException;
import cn.inkforge.cli.runtime.CommandHandler;
import cn.inkforge.cli.runtime.CommandResult;
import java.util.Map;
import java.util.Set;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

final class LongRelationshipCommands {

    private static final Set<String> RELATION_CREATE_FIELDS = Set.of(
            "characterId", "targetId", "relationType", "intimacy",
            "description", "startDate", "endDate");
    private static final Set<String> RELATION_UPDATE_FIELDS = Set.of(
            "relationType", "intimacy", "description", "startDate", "endDate");
    private static final Set<String> EXPERIENCE_FIELDS =
            Set.of("chapterId", "content", "order");
    private static final Set<String> RELATION_TYPES = Set.of(
            "family", "master_student", "friend", "enemy", "ally", "lover",
            "rival", "subordinate", "acquaintance", "other");

    private LongRelationshipCommands() {}

    static void register(Map<String, CommandHandler> handlers) {
        handlers.put("long.lore.relation.create", LongRelationshipCommands::createRelation);
        handlers.put("long.lore.relation.update", LongRelationshipCommands::updateRelation);
        handlers.put("long.lore.relation.delete", LongRelationshipCommands::deleteRelation);
        handlers.put("long.lore.experience.create", LongRelationshipCommands::createExperience);
        handlers.put("long.lore.experience.update", LongRelationshipCommands::updateExperience);
        handlers.put("long.lore.experience.delete", LongRelationshipCommands::deleteExperience);
    }

    private static CommandResult createRelation(
            cn.inkforge.cli.runtime.CommandContext context, ObjectNode payload) {
        MutationPayloads.requireFields(payload, Set.of("novelId", "clientRequestId", "data"));
        ObjectNode body = MutationPayloads.data(payload, RELATION_CREATE_FIELDS);
        validateRelation(body, true);
        body.put("clientRequestId", MutationPayloads.clientRequestId(payload, 256));
        return post(context, novel(payload) + "/relations", body);
    }

    private static CommandResult updateRelation(
            cn.inkforge.cli.runtime.CommandContext context, ObjectNode payload) {
        MutationPayloads.requireFields(
                payload, Set.of("novelId", "relationId", "expectedUpdatedAt", "data"));
        ObjectNode body = MutationPayloads.data(payload, RELATION_UPDATE_FIELDS);
        validateRelation(body, false);
        body.put("expectedUpdatedAt", MutationPayloads.expectedUpdatedAt(payload, false));
        return patch(context, novel(payload) + "/relations/" + id(payload, "relationId"), body);
    }

    private static CommandResult deleteRelation(
            cn.inkforge.cli.runtime.CommandContext context, ObjectNode payload) {
        MutationPayloads.requireFields(
                payload, Set.of("novelId", "relationId", "expectedUpdatedAt"));
        return delete(
                context,
                novel(payload) + "/relations/" + id(payload, "relationId"),
                cas(context, payload));
    }

    private static CommandResult createExperience(
            cn.inkforge.cli.runtime.CommandContext context, ObjectNode payload) {
        MutationPayloads.requireFields(
                payload, Set.of("novelId", "characterId", "clientRequestId", "data"));
        ObjectNode body = MutationPayloads.data(payload, EXPERIENCE_FIELDS);
        validateExperience(body, true);
        body.put("clientRequestId", MutationPayloads.clientRequestId(payload, 256));
        return post(
                context,
                novel(payload) + "/characters/" + id(payload, "characterId") + "/experiences",
                body);
    }

    private static CommandResult updateExperience(
            cn.inkforge.cli.runtime.CommandContext context, ObjectNode payload) {
        MutationPayloads.requireFields(
                payload, Set.of("novelId", "experienceId", "expectedUpdatedAt", "data"));
        ObjectNode body = MutationPayloads.data(payload, EXPERIENCE_FIELDS);
        validateExperience(body, false);
        body.put("expectedUpdatedAt", MutationPayloads.expectedUpdatedAt(payload, false));
        return patch(
                context,
                novel(payload) + "/experiences/" + id(payload, "experienceId"),
                body);
    }

    private static CommandResult deleteExperience(
            cn.inkforge.cli.runtime.CommandContext context, ObjectNode payload) {
        MutationPayloads.requireFields(
                payload, Set.of("novelId", "experienceId", "expectedUpdatedAt"));
        return delete(
                context,
                novel(payload) + "/experiences/" + id(payload, "experienceId"),
                cas(context, payload));
    }

    private static void validateRelation(ObjectNode data, boolean creating) {
        if (creating) {
            MutationPayloads.requireString(data, "characterId");
            MutationPayloads.requireString(data, "targetId");
        }
        JsonNode type = data.get("relationType");
        if (type != null) {
            if (!type.isTextual() || !RELATION_TYPES.contains(type.textValue())) {
                throw invalid("data.relationType 不是受支持的关系类型");
            }
        } else if (creating) {
            throw new CliInputException("FIELD_REQUIRED", "data 缺少字段 relationType");
        }
        JsonNode intimacy = data.get("intimacy");
        if (intimacy != null) {
            if (intimacy.isNull()) throw invalid("data.intimacy 不能为 null");
            if (!intimacy.isIntegralNumber()) throw invalid("data.intimacy 必须是整数或 null");
            if (intimacy.intValue() < 0 || intimacy.intValue() > 100) {
                throw invalid("data.intimacy 必须在 0 到 100 之间");
            }
        }
        for (String field : Set.of("description", "startDate", "endDate")) {
            nullableString(data, field);
        }
    }

    private static void validateExperience(ObjectNode data, boolean creating) {
        JsonNode content = data.get("content");
        if (creating) {
            MutationPayloads.requireString(data, "content", true);
        } else if (content != null) {
            if (content.isNull()) {
                throw invalid("data.content 不能为 null");
            }
            if (!content.isTextual()) throw invalid("data.content 必须是字符串或 null");
        }
        nullableString(data, "chapterId");
        JsonNode order = data.get("order");
        if (order != null) {
            if (!order.isNull() && !order.isIntegralNumber()) {
                throw invalid("data.order 必须是整数或 null");
            }
            if (!creating && order.isNull()) throw invalid("data.order 不能为 null");
        }
    }

    private static void nullableString(ObjectNode data, String field) {
        JsonNode value = data.get(field);
        if (value != null && !value.isNull() && !value.isTextual()) {
            throw invalid("data." + field + " 必须是字符串或 null");
        }
    }

    private static ObjectNode cas(
            cn.inkforge.cli.runtime.CommandContext context, ObjectNode payload) {
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("expectedUpdatedAt", MutationPayloads.expectedUpdatedAt(payload, false));
        return body;
    }

    private static String novel(ObjectNode payload) {
        return "/api/v1/novels/" + id(payload, "novelId");
    }

    private static String id(ObjectNode payload, String field) {
        return Payloads.segment(MutationPayloads.requireString(payload, field));
    }

    private static CommandResult post(
            cn.inkforge.cli.runtime.CommandContext context, String path, ObjectNode body) {
        return CommandResult.json(context.requireApi().request("POST", path, body));
    }

    private static CommandResult patch(
            cn.inkforge.cli.runtime.CommandContext context, String path, ObjectNode body) {
        return CommandResult.json(context.requireApi().request("PATCH", path, body));
    }

    private static CommandResult delete(
            cn.inkforge.cli.runtime.CommandContext context, String path, ObjectNode body) {
        return CommandResult.json(context.requireApi().request("DELETE", path, body));
    }

    private static CliInputException invalid(String message) {
        return new CliInputException("INVALID_DATA_FIELD", message);
    }
}
