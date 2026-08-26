package cn.inkforge.core.lore.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHARACTER;
import static cn.inkforge.core.db.generated.Tables.FACTION;
import static cn.inkforge.core.db.generated.Tables.GLOSSARY;
import static cn.inkforge.core.db.generated.Tables.ITEM;
import static cn.inkforge.core.db.generated.Tables.LOCATION;

import cn.inkforge.core.db.generated.enums.Characterstatus;
import cn.inkforge.core.db.generated.tables.records.CharacterRecord;
import cn.inkforge.core.db.generated.tables.records.FactionRecord;
import cn.inkforge.core.db.generated.tables.records.GlossaryRecord;
import cn.inkforge.core.db.generated.tables.records.ItemRecord;
import cn.inkforge.core.db.generated.tables.records.LocationRecord;
import cn.inkforge.core.lore.domain.LoreEntityKind;
import java.time.LocalDateTime;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.function.Function;
import org.jooq.Table;
import org.jooq.TableField;
import org.jooq.UpdatableRecord;
import org.jooq.Condition;

/** 五类设定实体的 jOOQ 类型描述；共用协议但不退化为字符串 SQL。 */
final class LoreEntityDefinitions {

    static final EntityDefinition<CharacterRecord> CHARACTERS = new EntityDefinition<>(
            LoreEntityKind.CHARACTERS,
            CHARACTER,
            CHARACTER.ID,
            CHARACTER.NOVELID,
            CHARACTER.CREATEDAT,
            CHARACTER.UPDATEDAT,
            List.of(
                    text("name", CHARACTER.NAME),
                    text("aliases", CHARACTER.ALIASES),
                    text("gender", CHARACTER.GENDER),
                    text("age", CHARACTER.AGE),
                    text("appearance", CHARACTER.APPEARANCE),
                    text("personality", CHARACTER.PERSONALITY),
                    text("identity", CHARACTER.IDENTITY),
                    text("background", CHARACTER.BACKGROUND),
                    text("coreDesire", CHARACTER.COREDESIRE),
                    text("behaviorBoundaries", CHARACTER.BEHAVIORBOUNDARIES),
                    text("speechStyle", CHARACTER.SPEECHSTYLE),
                    text("relationshipPrinciples", CHARACTER.RELATIONSHIPPRINCIPLES),
                    text("shortTermGoal", CHARACTER.SHORTTERMGOAL),
                    text("factionId", CHARACTER.FACTIONID),
                    text("powerLevel", CHARACTER.POWERLEVEL),
                    text("combatAbility", CHARACTER.COMBATABILITY),
                    text("specialSkills", CHARACTER.SPECIALSKILLS),
                    field(
                            "currentStatus",
                            CHARACTER.CURRENTSTATUS,
                            value -> Characterstatus.lookupLiteral((String) value),
                            Characterstatus::getLiteral),
                    text("statusNote", CHARACTER.STATUSNOTE)),
            Map.of("currentStatus", "active"));

    static final EntityDefinition<ItemRecord> ITEMS = new EntityDefinition<>(
            LoreEntityKind.ITEMS,
            ITEM,
            ITEM.ID,
            ITEM.NOVELID,
            ITEM.CREATEDAT,
            ITEM.UPDATEDAT,
            List.of(
                    text("name", ITEM.NAME),
                    text("aliases", ITEM.ALIASES),
                    text("type", ITEM.TYPE),
                    text("rarity", ITEM.RARITY),
                    text("effect", ITEM.EFFECT),
                    text("origin", ITEM.ORIGIN),
                    text("description", ITEM.DESCRIPTION),
                    text("ownerId", ITEM.OWNERID)),
            Map.of());

    static final EntityDefinition<LocationRecord> LOCATIONS = new EntityDefinition<>(
            LoreEntityKind.LOCATIONS,
            LOCATION,
            LOCATION.ID,
            LOCATION.NOVELID,
            LOCATION.CREATEDAT,
            LOCATION.UPDATEDAT,
            List.of(
                    text("name", LOCATION.NAME),
                    text("aliases", LOCATION.ALIASES),
                    text("type", LOCATION.TYPE),
                    text("parentId", LOCATION.PARENTID),
                    text("climate", LOCATION.CLIMATE),
                    text("culture", LOCATION.CULTURE),
                    text("description", LOCATION.DESCRIPTION)),
            Map.of());

    static final EntityDefinition<FactionRecord> FACTIONS = new EntityDefinition<>(
            LoreEntityKind.FACTIONS,
            FACTION,
            FACTION.ID,
            FACTION.NOVELID,
            FACTION.CREATEDAT,
            FACTION.UPDATEDAT,
            List.of(
                    text("name", FACTION.NAME),
                    text("aliases", FACTION.ALIASES),
                    text("type", FACTION.TYPE),
                    text("baseId", FACTION.BASEID),
                    text("description", FACTION.DESCRIPTION)),
            Map.of());

    static final EntityDefinition<GlossaryRecord> GLOSSARY_ENTRIES = new EntityDefinition<>(
            LoreEntityKind.GLOSSARY,
            GLOSSARY,
            GLOSSARY.ID,
            GLOSSARY.NOVELID,
            GLOSSARY.CREATEDAT,
            GLOSSARY.UPDATEDAT,
            List.of(
                    text("term", GLOSSARY.TERM),
                    text("definition", GLOSSARY.DEFINITION),
                    text("category", GLOSSARY.CATEGORY)),
            Map.of());

    private LoreEntityDefinitions() {}

    static <R extends UpdatableRecord<R>> EntityDefinition<R> definition(
            LoreEntityKind kind) {
        @SuppressWarnings("unchecked")
        EntityDefinition<R> value = (EntityDefinition<R>) switch (kind) {
            case CHARACTERS -> CHARACTERS;
            case ITEMS -> ITEMS;
            case LOCATIONS -> LOCATIONS;
            case FACTIONS -> FACTIONS;
            case GLOSSARY -> GLOSSARY_ENTRIES;
        };
        return value;
    }

    private static <R extends UpdatableRecord<R>> FieldBinding<R, String> text(
            String name, TableField<R, String> field) {
        return field(name, field, value -> (String) value, value -> value);
    }

    private static <R extends UpdatableRecord<R>, T> FieldBinding<R, T> field(
            String name,
            TableField<R, T> field,
            Function<Object, T> toDatabase,
            Function<T, Object> fromDatabase) {
        return new FieldBinding<>(name, field, toDatabase, fromDatabase);
    }

    record EntityDefinition<R extends UpdatableRecord<R>>(
            LoreEntityKind kind,
            Table<R> table,
            TableField<R, String> id,
            TableField<R, String> novelId,
            TableField<R, LocalDateTime> createdAt,
            TableField<R, LocalDateTime> updatedAt,
            List<FieldBinding<R, ?>> fields,
            Map<String, Object> defaults) {

        EntityDefinition {
            fields = List.copyOf(fields);
            defaults = Map.copyOf(defaults);
        }

        Map<String, Object> complete(Map<String, Object> requested) {
            requireKnown(requested);
            Map<String, Object> result = new LinkedHashMap<>();
            for (FieldBinding<R, ?> binding : fields) {
                result.put(
                        binding.name(),
                        requested.containsKey(binding.name())
                                ? requested.get(binding.name())
                                : defaults.get(binding.name()));
            }
            return Collections.unmodifiableMap(result);
        }

        Map<String, Object> snapshot(R record) {
            Map<String, Object> result = new LinkedHashMap<>();
            for (FieldBinding<R, ?> binding : fields) {
                result.put(binding.name(), binding.read(record));
            }
            return Collections.unmodifiableMap(result);
        }

        void write(R record, Map<String, Object> values) {
            requireKnown(values);
            for (FieldBinding<R, ?> binding : fields) {
                if (values.containsKey(binding.name())) {
                    binding.write(record, values.get(binding.name()));
                }
            }
        }

        private void requireKnown(Map<String, Object> values) {
            for (String name : values.keySet()) {
                boolean known = fields.stream().anyMatch(field -> field.name().equals(name));
                if (!known) {
                    throw new IllegalArgumentException("未知设定字段：" + name);
                }
            }
        }
    }

    record FieldBinding<R extends UpdatableRecord<R>, T>(
            String name,
            TableField<R, T> field,
            Function<Object, T> toDatabase,
            Function<T, Object> fromDatabase) {

        FieldBinding {
            Objects.requireNonNull(name);
            Objects.requireNonNull(field);
            Objects.requireNonNull(toDatabase);
            Objects.requireNonNull(fromDatabase);
        }

        Object read(R record) {
            T value = record.get(field);
            return value == null ? null : fromDatabase.apply(value);
        }

        void write(R record, Object value) {
            record.set(field, value == null ? null : toDatabase.apply(value));
        }

        Condition equalsValue(Object value) {
            return field.eq(value == null ? null : toDatabase.apply(value));
        }
    }
}
