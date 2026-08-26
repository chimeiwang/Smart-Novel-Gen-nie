package cn.inkforge.cli.commands;

import cn.inkforge.cli.runtime.CliInputException;
import cn.inkforge.cli.runtime.CommandHandler;
import cn.inkforge.cli.runtime.CommandResult;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** 五类长篇设定实体共享同一安全写协议，字段集合仍按资源强隔离。 */
final class LongLoreEntityCommands {

    private static final Set<String> CHARACTER_STATUSES =
            Set.of("active", "missing", "dead", "imprisoned", "unknown");
    private static final Map<String, Resource> RESOURCES = resources();

    private LongLoreEntityCommands() {}

    static void register(Map<String, CommandHandler> handlers) {
        RESOURCES.forEach((name, resource) -> {
            handlers.put("long.lore." + name + ".create", (context, payload) ->
                    create(context, payload, name, resource));
            handlers.put("long.lore." + name + ".update", (context, payload) ->
                    update(context, payload, name, resource));
            handlers.put("long.lore." + name + ".delete", (context, payload) ->
                    delete(context, payload, resource));
        });
    }

    private static CommandResult create(
            cn.inkforge.cli.runtime.CommandContext context,
            ObjectNode payload,
            String name,
            Resource resource) {
        MutationPayloads.requireFields(payload, Set.of("novelId", "clientRequestId", "data"));
        ObjectNode body = MutationPayloads.data(payload, resource.businessFields());
        validate(name, resource, body, true);
        body.put("clientRequestId", MutationPayloads.clientRequestId(payload, 256));
        return CommandResult.json(context.requireApi().request(
                "POST", collection(payload, resource), body));
    }

    private static CommandResult update(
            cn.inkforge.cli.runtime.CommandContext context,
            ObjectNode payload,
            String name,
            Resource resource) {
        MutationPayloads.requireFields(
                payload,
                Set.of("novelId", resource.idField(), "expectedUpdatedAt", "data"));
        ObjectNode body = MutationPayloads.data(payload, resource.businessFields());
        validate(name, resource, body, false);
        body.put("expectedUpdatedAt", MutationPayloads.expectedUpdatedAt(payload, false));
        return CommandResult.json(context.requireApi().request(
                "PATCH", item(payload, resource), body));
    }

    private static CommandResult delete(
            cn.inkforge.cli.runtime.CommandContext context,
            ObjectNode payload,
            Resource resource) {
        MutationPayloads.requireFields(
                payload, Set.of("novelId", resource.idField(), "expectedUpdatedAt"));
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("expectedUpdatedAt", MutationPayloads.expectedUpdatedAt(payload, false));
        return CommandResult.json(context.requireApi().request(
                "DELETE", item(payload, resource), body));
    }

    private static void validate(
            String name, Resource resource, ObjectNode data, boolean creating) {
        if (creating) {
            TreeSet<String> missing = new TreeSet<>();
            resource.createRequiredFields().forEach(field -> {
                if (!data.has(field)) missing.add(field);
            });
            if (!missing.isEmpty()) {
                throw new CliInputException(
                        "FIELD_REQUIRED",
                        "data 缺少创建必填字段：" + String.join(", ", missing));
            }
        }
        data.properties().forEach(entry -> {
            String field = entry.getKey();
            JsonNode value = entry.getValue();
            if (value.isNull()) {
                if (resource.nonNullableFields().contains(field)) {
                    throw new CliInputException(
                            "INVALID_DATA_FIELD", "data." + field + " 不能为 null");
                }
                return;
            }
            if (!value.isTextual()) {
                throw new CliInputException(
                        "INVALID_DATA_FIELD", "data." + field + " 必须是字符串或 null");
            }
            if (Set.of("name", "term").contains(field)
                    && value.textValue().trim().isEmpty()) {
                throw new CliInputException(
                        "INVALID_DATA_FIELD", "data." + field + " 不能为空字符串");
            }
            if (name.equals("character")
                    && field.equals("currentStatus")
                    && !CHARACTER_STATUSES.contains(value.textValue())) {
                throw new CliInputException(
                        "INVALID_DATA_FIELD", "data.currentStatus 不是受支持的角色状态");
            }
        });
    }

    private static String collection(ObjectNode payload, Resource resource) {
        return "/api/v1/novels/"
                + Payloads.segment(MutationPayloads.requireString(payload, "novelId"))
                + "/"
                + resource.pathSegment();
    }

    private static String item(ObjectNode payload, Resource resource) {
        return collection(payload, resource)
                + "/"
                + Payloads.segment(MutationPayloads.requireString(payload, resource.idField()));
    }

    private static Map<String, Resource> resources() {
        LinkedHashMap<String, Resource> values = new LinkedHashMap<>();
        values.put("character", new Resource(
                "characters",
                "characterId",
                Set.of(
                        "name", "aliases", "gender", "age", "appearance", "personality",
                        "identity", "background", "coreDesire", "behaviorBoundaries",
                        "speechStyle", "relationshipPrinciples", "shortTermGoal", "factionId",
                        "powerLevel", "combatAbility", "specialSkills", "currentStatus", "statusNote"),
                Set.of("name"),
                Set.of("name", "currentStatus")));
        values.put("location", new Resource(
                "locations",
                "locationId",
                Set.of("name", "aliases", "type", "parentId", "climate", "culture", "description"),
                Set.of("name"),
                Set.of("name")));
        values.put("faction", new Resource(
                "factions",
                "factionId",
                Set.of("name", "aliases", "type", "baseId", "description"),
                Set.of("name"),
                Set.of("name")));
        values.put("item", new Resource(
                "items",
                "itemId",
                Set.of("name", "aliases", "type", "rarity", "effect", "origin", "description", "ownerId"),
                Set.of("name"),
                Set.of("name")));
        values.put("glossary", new Resource(
                "glossary",
                "glossaryId",
                Set.of("term", "definition", "category"),
                Set.of("term", "definition"),
                Set.of("term", "definition")));
        return Map.copyOf(values);
    }

    private record Resource(
            String pathSegment,
            String idField,
            Set<String> businessFields,
            Set<String> createRequiredFields,
            Set<String> nonNullableFields) {}
}
