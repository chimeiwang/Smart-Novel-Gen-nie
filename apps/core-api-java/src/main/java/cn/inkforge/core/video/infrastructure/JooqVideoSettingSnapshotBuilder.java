package cn.inkforge.core.video.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHARACTER;
import static cn.inkforge.core.db.generated.Tables.CHARACTERRELATION;
import static cn.inkforge.core.db.generated.Tables.ITEM;
import static cn.inkforge.core.db.generated.Tables.LOCATION;
import static cn.inkforge.core.db.generated.Tables.WORLDSETTING;

import cn.inkforge.core.db.generated.tables.records.CharacterRecord;
import cn.inkforge.core.db.generated.tables.records.CharacterrelationRecord;
import cn.inkforge.core.db.generated.tables.records.ItemRecord;
import cn.inkforge.core.db.generated.tables.records.LocationRecord;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.jooq.DSLContext;
import tools.jackson.databind.ObjectMapper;

/** 在创建提示词任务的同一事务内冻结长篇人物、关系、地点、道具和世界设定。 */
final class JooqVideoSettingSnapshotBuilder {

    private final ObjectMapper json;

    JooqVideoSettingSnapshotBuilder(ObjectMapper json) {
        this.json = Objects.requireNonNull(json);
    }

    Map<String, Object> build(DSLContext context, String novelId) {
        List<CharacterRecord> characters = context.selectFrom(CHARACTER)
                .where(CHARACTER.NOVELID.eq(novelId))
                .orderBy(CHARACTER.ID)
                .forUpdate()
                .fetch();
        Set<String> characterIds = characters.stream()
                .map(CharacterRecord::getId)
                .collect(java.util.stream.Collectors.toSet());
        Map<String, String> characterNames = new HashMap<>();
        characters.forEach(value -> characterNames.put(value.getId(), value.getName()));
        List<CharacterrelationRecord> relations = characterIds.isEmpty()
                ? List.of()
                : context.selectFrom(CHARACTERRELATION)
                        .where(
                                CHARACTERRELATION.CHARACTERID.in(characterIds),
                                CHARACTERRELATION.TARGETID.in(characterIds))
                        .orderBy(CHARACTERRELATION.ID)
                        .forUpdate()
                        .fetch();
        List<LocationRecord> locations = context.selectFrom(LOCATION)
                .where(LOCATION.NOVELID.eq(novelId))
                .orderBy(LOCATION.ID)
                .forUpdate()
                .fetch();
        Set<String> locationIds = locations.stream()
                .map(LocationRecord::getId)
                .collect(java.util.stream.Collectors.toSet());
        List<ItemRecord> items = context.selectFrom(ITEM)
                .where(ITEM.NOVELID.eq(novelId))
                .orderBy(ITEM.ID)
                .forUpdate()
                .fetch();
        var world = context.selectFrom(WORLDSETTING)
                .where(WORLDSETTING.NOVELID.eq(novelId))
                .forUpdate()
                .fetchOne();

        List<Map<String, Object>> entries = new ArrayList<>();
        for (CharacterRecord character : characters) {
            LinkedHashMap<String, Object> content = new LinkedHashMap<>();
            content.put("kind", "character");
            content.put("id", character.getId());
            content.put("name", character.getName());
            content.put("aliases", aliases(character.getAliases()));
            content.put("appearance", character.getAppearance());
            content.put("identity", character.getIdentity());
            entries.add(withHash(content));
        }
        for (CharacterrelationRecord relation : relations) {
            LinkedHashMap<String, Object> content = new LinkedHashMap<>();
            content.put("kind", "relationship");
            content.put("id", relation.getId());
            content.put(
                    "name",
                    characterNames.get(relation.getCharacterid())
                            + " → "
                            + characterNames.get(relation.getTargetid()));
            content.put("sourceCharacterId", relation.getCharacterid());
            content.put("targetCharacterId", relation.getTargetid());
            content.put(
                    "relationType",
                    relation.getRelationtype() == null
                            ? null
                            : relation.getRelationtype().getLiteral());
            content.put("description", relation.getDescription());
            entries.add(withHash(content));
        }
        for (LocationRecord location : locations) {
            LinkedHashMap<String, Object> content = new LinkedHashMap<>();
            content.put("kind", "location");
            content.put("id", location.getId());
            content.put("name", location.getName());
            content.put("aliases", aliases(location.getAliases()));
            content.put("locationType", location.getType());
            content.put(
                    "parentLocationId",
                    locationIds.contains(location.getParentid()) ? location.getParentid() : null);
            content.put("climate", location.getClimate());
            content.put("culture", location.getCulture());
            content.put("description", location.getDescription());
            entries.add(withHash(content));
        }
        for (ItemRecord item : items) {
            LinkedHashMap<String, Object> content = new LinkedHashMap<>();
            content.put("kind", "item");
            content.put("id", item.getId());
            content.put("name", item.getName());
            content.put("aliases", aliases(item.getAliases()));
            content.put("itemType", item.getType());
            content.put(
                    "ownerCharacterId",
                    characterIds.contains(item.getOwnerid()) ? item.getOwnerid() : null);
            content.put("description", item.getDescription());
            entries.add(withHash(content));
        }
        if (world != null && world.getContent() != null && !world.getContent().isEmpty()) {
            LinkedHashMap<String, Object> content = new LinkedHashMap<>();
            content.put("kind", "world_setting");
            content.put("id", world.getId());
            content.put("name", "世界设定");
            content.put("content", world.getContent());
            entries.add(withHash(content));
        }

        List<Map<String, Object>> sorted = new ArrayList<>(entries);
        sorted.sort(Comparator
                .comparing((Map<String, Object> value) -> (String) value.get("kind"))
                .thenComparing(value -> (String) value.get("id")));
        String fingerprint = canonicalHash(sorted);
        LinkedHashMap<String, Object> snapshot = new LinkedHashMap<>();
        snapshot.put("schemaVersion", "1.0");
        snapshot.put("fingerprint", fingerprint);
        snapshot.put("entries", List.copyOf(entries));
        return snapshot;
    }

    private Map<String, Object> withHash(LinkedHashMap<String, Object> content) {
        LinkedHashMap<String, Object> value = new LinkedHashMap<>(content);
        value.put("contentHash", canonicalHash(content));
        return value;
    }

    private String canonicalHash(Object value) {
        return CommandIdempotency.sha256(
                CommandIdempotency.canonicalJsonBytes(value, json));
    }

    private static List<String> aliases(String value) {
        if (value == null) return List.of();
        List<String> result = new ArrayList<>();
        for (String item : value.replace('，', ',').split(",")) {
            String normalized = item.strip();
            if (!normalized.isEmpty()) result.add(normalized);
        }
        return List.copyOf(result);
    }
}
