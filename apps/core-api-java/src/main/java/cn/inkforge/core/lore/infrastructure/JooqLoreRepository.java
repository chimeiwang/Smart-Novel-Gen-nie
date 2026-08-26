package cn.inkforge.core.lore.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHARACTER;
import static cn.inkforge.core.db.generated.Tables.CHARACTEREXPERIENCE;
import static cn.inkforge.core.db.generated.Tables.CHARACTERRELATION;
import static cn.inkforge.core.db.generated.Tables.CHARACTERSTATECHANGE;
import static cn.inkforge.core.db.generated.Tables.FACTION;
import static cn.inkforge.core.db.generated.Tables.ITEM;
import static cn.inkforge.core.db.generated.Tables.LOCATION;
import static cn.inkforge.core.db.generated.Tables._FACTIONTERRITORIES;

import cn.inkforge.contracts.api.DeleteImpactResponse;
import cn.inkforge.core.lore.application.LoreRepository;
import cn.inkforge.core.lore.domain.ContentKind;
import cn.inkforge.core.lore.domain.ContentSnapshot;
import cn.inkforge.core.lore.domain.EntityMutation;
import cn.inkforge.core.lore.domain.ExperienceData;
import cn.inkforge.core.lore.domain.ExperienceBatchMutationResult;
import cn.inkforge.core.lore.domain.ExperienceMutation;
import cn.inkforge.core.lore.domain.ExperienceMutationResult;
import cn.inkforge.core.lore.domain.ExperiencePatch;
import cn.inkforge.core.lore.domain.ExperienceSnapshot;
import cn.inkforge.core.lore.domain.LoreEntityData;
import cn.inkforge.core.lore.domain.LoreBatchMutationResult;
import cn.inkforge.core.lore.domain.LoreEntityKind;
import cn.inkforge.core.lore.domain.LoreEntityMutationResult;
import cn.inkforge.core.lore.domain.LoreEntityPatch;
import cn.inkforge.core.lore.domain.LoreEntitySnapshot;
import cn.inkforge.core.lore.domain.RelationData;
import cn.inkforge.core.lore.domain.RelationMutationResult;
import cn.inkforge.core.lore.domain.RelationPatch;
import cn.inkforge.core.lore.domain.RelationSnapshot;
import cn.inkforge.core.lore.domain.MutationAction;
import cn.inkforge.core.lore.domain.WritingBiblePatch;
import cn.inkforge.core.lore.domain.WritingBibleSnapshot;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CommandResourceId;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import java.time.Clock;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.jooq.DSLContext;
import org.jooq.UpdatableRecord;
import org.jooq.impl.DSL;

/**
 * 长篇设定 PostgreSQL 仓储；所有写入都持有小说锁和事务级 advisory lock。
 *
 * <p>实体、经历、关系和作品级单例资料共享一个事务视图，供 ReviewArtifact 批量应用时整体回滚。删除前
 * 显式统计跨表引用而不依赖级联；确定性创建只允许资源仍处于初始版本时幂等重放。
 */
public final class JooqLoreRepository implements LoreRepository {

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final JooqLoreRelationshipStore relationships;
    private final JooqLoreContentStore contents;

    public JooqLoreRepository(
            CoreDatabase database, CuidV1Generator ids, Clock clock) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.relationships = new JooqLoreRelationshipStore(database, clock);
        this.contents = new JooqLoreContentStore(database, ids, clock);
    }

    @Override
    public List<LoreEntitySnapshot> listEntities(
            String novelId, String userId, LoreEntityKind kind) {
        DSLContext context = database.dsl();
        LoreTransactionGuard.requireOwner(context, novelId, userId);
        return switch (kind) {
            case CHARACTERS -> listEntities(
                    context, novelId, LoreEntityDefinitions.CHARACTERS);
            case ITEMS -> listEntities(context, novelId, LoreEntityDefinitions.ITEMS);
            case LOCATIONS -> listEntities(
                    context, novelId, LoreEntityDefinitions.LOCATIONS);
            case FACTIONS -> listEntities(
                    context, novelId, LoreEntityDefinitions.FACTIONS);
            case GLOSSARY -> listEntities(
                    context, novelId, LoreEntityDefinitions.GLOSSARY_ENTRIES);
        };
    }

    @Override
    public LoreEntityMutationResult createEntity(
            String novelId,
            String userId,
            LoreEntityKind kind,
            String clientRequestId,
            LoreEntityData data) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            LoreTransactionGuard.requireOwner(transaction, novelId, userId);
            LoreTransactionGuard.lockNovel(transaction, novelId, userId);
            return switch (kind) {
                case CHARACTERS -> createEntity(
                        transaction,
                        novelId,
                        userId,
                        clientRequestId,
                        data,
                        LoreEntityDefinitions.CHARACTERS);
                case ITEMS -> createEntity(
                        transaction,
                        novelId,
                        userId,
                        clientRequestId,
                        data,
                        LoreEntityDefinitions.ITEMS);
                case LOCATIONS -> createEntity(
                        transaction,
                        novelId,
                        userId,
                        clientRequestId,
                        data,
                        LoreEntityDefinitions.LOCATIONS);
                case FACTIONS -> createEntity(
                        transaction,
                        novelId,
                        userId,
                        clientRequestId,
                        data,
                        LoreEntityDefinitions.FACTIONS);
                case GLOSSARY -> createEntity(
                        transaction,
                        novelId,
                        userId,
                        clientRequestId,
                        data,
                        LoreEntityDefinitions.GLOSSARY_ENTRIES);
            };
        });
    }

    @Override
    public LoreEntitySnapshot updateEntity(
            String novelId,
            String userId,
            LoreEntityKind kind,
            String entityId,
            LoreEntityPatch patch,
            OffsetDateTime expectedUpdatedAt) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            LoreTransactionGuard.requireOwner(transaction, novelId, userId);
            LoreTransactionGuard.lockNovel(transaction, novelId, userId);
            return switch (kind) {
                case CHARACTERS -> updateEntity(
                        transaction,
                        novelId,
                        entityId,
                        patch,
                        expectedUpdatedAt,
                        LoreEntityDefinitions.CHARACTERS);
                case ITEMS -> updateEntity(
                        transaction,
                        novelId,
                        entityId,
                        patch,
                        expectedUpdatedAt,
                        LoreEntityDefinitions.ITEMS);
                case LOCATIONS -> updateEntity(
                        transaction,
                        novelId,
                        entityId,
                        patch,
                        expectedUpdatedAt,
                        LoreEntityDefinitions.LOCATIONS);
                case FACTIONS -> updateEntity(
                        transaction,
                        novelId,
                        entityId,
                        patch,
                        expectedUpdatedAt,
                        LoreEntityDefinitions.FACTIONS);
                case GLOSSARY -> updateEntity(
                        transaction,
                        novelId,
                        entityId,
                        patch,
                        expectedUpdatedAt,
                        LoreEntityDefinitions.GLOSSARY_ENTRIES);
            };
        });
    }

    @Override
    public DeleteImpactResponse deleteEntity(
            String novelId,
            String userId,
            LoreEntityKind kind,
            String entityId,
            OffsetDateTime expectedUpdatedAt) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            LoreTransactionGuard.requireOwner(transaction, novelId, userId);
            LoreTransactionGuard.lockNovel(transaction, novelId, userId);
            return switch (kind) {
                case CHARACTERS -> deleteEntity(
                        transaction,
                        novelId,
                        entityId,
                        expectedUpdatedAt,
                        LoreEntityDefinitions.CHARACTERS);
                case ITEMS -> deleteEntity(
                        transaction,
                        novelId,
                        entityId,
                        expectedUpdatedAt,
                        LoreEntityDefinitions.ITEMS);
                case LOCATIONS -> deleteEntity(
                        transaction,
                        novelId,
                        entityId,
                        expectedUpdatedAt,
                        LoreEntityDefinitions.LOCATIONS);
                case FACTIONS -> deleteEntity(
                        transaction,
                        novelId,
                        entityId,
                        expectedUpdatedAt,
                        LoreEntityDefinitions.FACTIONS);
                case GLOSSARY -> deleteEntity(
                        transaction,
                        novelId,
                        entityId,
                        expectedUpdatedAt,
                        LoreEntityDefinitions.GLOSSARY_ENTRIES);
            };
        });
    }

    @Override
    public List<LoreBatchMutationResult> applyEntityMutations(
            String novelId, String userId, List<EntityMutation> mutations) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            LoreTransactionGuard.requireOwner(transaction, novelId, userId);
            LoreTransactionGuard.lockNovel(transaction, novelId, userId);
            java.util.ArrayList<LoreBatchMutationResult> results =
                    new java.util.ArrayList<>(mutations.size());
            for (EntityMutation mutation : mutations) {
                if (mutation.action() == MutationAction.CREATE) {
                    if (mutation.clientRequestId() == null) {
                        throw new IllegalArgumentException(
                                mutation.errorLabel() + " create 缺少 clientRequestId");
                    }
                    LoreEntityMutationResult result = createEntityInTransaction(
                            transaction,
                            novelId,
                            userId,
                            mutation.kind(),
                            mutation.clientRequestId(),
                            new LoreEntityData(mutation.fields()));
                    results.add(new LoreBatchMutationResult(
                            mutation.action(),
                            result.entity(),
                            null,
                            result.effective()));
                    continue;
                }
                String entityId = mutation.entityId();
                if (entityId == null) {
                    entityId = resolveEntityId(
                            transaction,
                            novelId,
                            mutation.kind(),
                            mutation.lookupField(),
                            mutation.lookupValue(),
                            mutation.errorLabel());
                }
                if (mutation.expectedUpdatedAt() == null) {
                    throw new IllegalArgumentException(
                            mutation.errorLabel() + " "
                                    + mutation.action().name().toLowerCase()
                                    + " 缺少 expectedUpdatedAt");
                }
                if (mutation.action() == MutationAction.UPDATE) {
                    LoreEntitySnapshot result = updateEntityInTransaction(
                            transaction,
                            novelId,
                            mutation.kind(),
                            entityId,
                            new LoreEntityPatch(mutation.fields()),
                            mutation.expectedUpdatedAt());
                    results.add(new LoreBatchMutationResult(
                            mutation.action(), result, null, null));
                } else {
                    DeleteImpactResponse result = deleteEntityInTransaction(
                            transaction,
                            novelId,
                            mutation.kind(),
                            entityId,
                            mutation.expectedUpdatedAt());
                    results.add(new LoreBatchMutationResult(
                            mutation.action(), null, result, null));
                }
            }
            return List.copyOf(results);
        });
    }

    @Override
    public ExperienceMutationResult createExperience(
            String novelId,
            String userId,
            String characterId,
            String clientRequestId,
            ExperienceData data) {
        return relationships.createExperience(
                novelId, userId, characterId, clientRequestId, data);
    }

    @Override
    public List<ExperienceSnapshot> listExperiences(
            String novelId, String userId, String characterId) {
        return relationships.listExperiences(novelId, userId, characterId);
    }

    @Override
    public ExperienceSnapshot updateExperience(
            String novelId,
            String userId,
            String experienceId,
            ExperiencePatch patch,
            OffsetDateTime expectedUpdatedAt) {
        return relationships.updateExperience(
                novelId, userId, experienceId, patch, expectedUpdatedAt);
    }

    @Override
    public DeleteImpactResponse deleteExperience(
            String novelId,
            String userId,
            String experienceId,
            OffsetDateTime expectedUpdatedAt) {
        return relationships.deleteExperience(
                novelId, userId, experienceId, expectedUpdatedAt);
    }

    @Override
    public List<ExperienceBatchMutationResult> applyExperienceMutations(
            String novelId, String userId, List<ExperienceMutation> mutations) {
        return relationships.applyExperienceMutations(novelId, userId, mutations);
    }

    @Override
    public RelationMutationResult createRelation(
            String novelId,
            String userId,
            String clientRequestId,
            RelationData data) {
        return relationships.createRelation(novelId, userId, clientRequestId, data);
    }

    @Override
    public List<RelationSnapshot> listRelations(String novelId, String userId) {
        return relationships.listRelations(novelId, userId);
    }

    @Override
    public RelationSnapshot updateRelation(
            String novelId,
            String userId,
            String relationId,
            RelationPatch patch,
            OffsetDateTime expectedUpdatedAt) {
        return relationships.updateRelation(
                novelId, userId, relationId, patch, expectedUpdatedAt);
    }

    @Override
    public DeleteImpactResponse deleteRelation(
            String novelId,
            String userId,
            String relationId,
            OffsetDateTime expectedUpdatedAt) {
        return relationships.deleteRelation(
                novelId, userId, relationId, expectedUpdatedAt);
    }

    @Override
    public ContentSnapshot saveContent(
            String novelId,
            String userId,
            ContentKind kind,
            String content,
            OffsetDateTime expectedUpdatedAt) {
        return contents.saveContent(
                novelId, userId, kind, content, expectedUpdatedAt);
    }

    @Override
    public ContentSnapshot saveStoryProgress(
            String novelId,
            String userId,
            String content,
            OffsetDateTime expectedUpdatedAt) {
        return contents.saveStoryProgress(
                novelId, userId, content, expectedUpdatedAt);
    }

    @Override
    public WritingBibleSnapshot saveWritingBible(
            String novelId,
            String userId,
            WritingBiblePatch patch,
            OffsetDateTime expectedUpdatedAt) {
        return contents.saveWritingBible(
                novelId, userId, patch, expectedUpdatedAt);
    }

    private <R extends UpdatableRecord<R>> List<LoreEntitySnapshot> listEntities(
            DSLContext context,
            String novelId,
            LoreEntityDefinitions.EntityDefinition<R> definition) {
        return context.selectFrom(definition.table())
                .where(definition.novelId().eq(novelId))
                .orderBy(definition.createdAt().asc(), definition.id().asc())
                .fetch()
                .map(record -> snapshot(definition, record));
    }

    private LoreEntityMutationResult createEntityInTransaction(
            DSLContext transaction,
            String novelId,
            String userId,
            LoreEntityKind kind,
            String clientRequestId,
            LoreEntityData data) {
        return switch (kind) {
            case CHARACTERS -> createEntity(
                    transaction, novelId, userId, clientRequestId, data,
                    LoreEntityDefinitions.CHARACTERS);
            case ITEMS -> createEntity(
                    transaction, novelId, userId, clientRequestId, data,
                    LoreEntityDefinitions.ITEMS);
            case LOCATIONS -> createEntity(
                    transaction, novelId, userId, clientRequestId, data,
                    LoreEntityDefinitions.LOCATIONS);
            case FACTIONS -> createEntity(
                    transaction, novelId, userId, clientRequestId, data,
                    LoreEntityDefinitions.FACTIONS);
            case GLOSSARY -> createEntity(
                    transaction, novelId, userId, clientRequestId, data,
                    LoreEntityDefinitions.GLOSSARY_ENTRIES);
        };
    }

    private LoreEntitySnapshot updateEntityInTransaction(
            DSLContext transaction,
            String novelId,
            LoreEntityKind kind,
            String entityId,
            LoreEntityPatch patch,
            OffsetDateTime expectedUpdatedAt) {
        return switch (kind) {
            case CHARACTERS -> updateEntity(
                    transaction, novelId, entityId, patch, expectedUpdatedAt,
                    LoreEntityDefinitions.CHARACTERS);
            case ITEMS -> updateEntity(
                    transaction, novelId, entityId, patch, expectedUpdatedAt,
                    LoreEntityDefinitions.ITEMS);
            case LOCATIONS -> updateEntity(
                    transaction, novelId, entityId, patch, expectedUpdatedAt,
                    LoreEntityDefinitions.LOCATIONS);
            case FACTIONS -> updateEntity(
                    transaction, novelId, entityId, patch, expectedUpdatedAt,
                    LoreEntityDefinitions.FACTIONS);
            case GLOSSARY -> updateEntity(
                    transaction, novelId, entityId, patch, expectedUpdatedAt,
                    LoreEntityDefinitions.GLOSSARY_ENTRIES);
        };
    }

    private DeleteImpactResponse deleteEntityInTransaction(
            DSLContext transaction,
            String novelId,
            LoreEntityKind kind,
            String entityId,
            OffsetDateTime expectedUpdatedAt) {
        return switch (kind) {
            case CHARACTERS -> deleteEntity(
                    transaction, novelId, entityId, expectedUpdatedAt,
                    LoreEntityDefinitions.CHARACTERS);
            case ITEMS -> deleteEntity(
                    transaction, novelId, entityId, expectedUpdatedAt,
                    LoreEntityDefinitions.ITEMS);
            case LOCATIONS -> deleteEntity(
                    transaction, novelId, entityId, expectedUpdatedAt,
                    LoreEntityDefinitions.LOCATIONS);
            case FACTIONS -> deleteEntity(
                    transaction, novelId, entityId, expectedUpdatedAt,
                    LoreEntityDefinitions.FACTIONS);
            case GLOSSARY -> deleteEntity(
                    transaction, novelId, entityId, expectedUpdatedAt,
                    LoreEntityDefinitions.GLOSSARY_ENTRIES);
        };
    }

    private static String resolveEntityId(
            DSLContext transaction,
            String novelId,
            LoreEntityKind kind,
            String lookupField,
            String lookupValue,
            String errorLabel) {
        return switch (kind) {
            case CHARACTERS -> resolveEntityId(
                    transaction, novelId, lookupField, lookupValue, errorLabel,
                    LoreEntityDefinitions.CHARACTERS);
            case ITEMS -> resolveEntityId(
                    transaction, novelId, lookupField, lookupValue, errorLabel,
                    LoreEntityDefinitions.ITEMS);
            case LOCATIONS -> resolveEntityId(
                    transaction, novelId, lookupField, lookupValue, errorLabel,
                    LoreEntityDefinitions.LOCATIONS);
            case FACTIONS -> resolveEntityId(
                    transaction, novelId, lookupField, lookupValue, errorLabel,
                    LoreEntityDefinitions.FACTIONS);
            case GLOSSARY -> resolveEntityId(
                    transaction, novelId, lookupField, lookupValue, errorLabel,
                    LoreEntityDefinitions.GLOSSARY_ENTRIES);
        };
    }

    private static <R extends UpdatableRecord<R>> String resolveEntityId(
            DSLContext transaction,
            String novelId,
            String lookupField,
            String lookupValue,
            String errorLabel,
            LoreEntityDefinitions.EntityDefinition<R> definition) {
        if (lookupField == null || lookupValue == null) {
            throw new IllegalArgumentException(errorLabel + " 无法唯一解析已有实体");
        }
        LoreEntityDefinitions.FieldBinding<R, ?> binding = definition.fields().stream()
                .filter(field -> field.name().equals(lookupField))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException(
                        errorLabel + " 无法唯一解析已有实体"));
        List<String> ids = transaction.select(definition.id())
                .from(definition.table())
                .where(
                        definition.novelId().eq(novelId),
                        binding.equalsValue(lookupValue))
                .limit(2)
                .forUpdate()
                .fetch(definition.id());
        if (ids.size() != 1) {
            throw new IllegalArgumentException(errorLabel + " 无法唯一解析已有实体");
        }
        return ids.getFirst();
    }

    private <R extends UpdatableRecord<R>> LoreEntityMutationResult createEntity(
            DSLContext transaction,
            String novelId,
            String userId,
            String clientRequestId,
            LoreEntityData data,
            LoreEntityDefinitions.EntityDefinition<R> definition) {
        String entityId = CommandResourceId.derive(
                definition.kind().value(), userId, novelId, clientRequestId);
        Map<String, Object> fields = definition.complete(data.fields());
        R existing = transaction.selectFrom(definition.table())
                .where(definition.id().eq(entityId))
                .forUpdate()
                .fetchOne();
        if (existing != null) {
            if (existing.get(definition.novelId()).equals(novelId)
                    && existing.get(definition.createdAt())
                            .equals(existing.get(definition.updatedAt()))
                    && definition.snapshot(existing).equals(fields)) {
                return new LoreEntityMutationResult(
                        snapshot(definition, existing), false);
            }
            throw createConflict();
        }
        validateEntityLinks(
                transaction, novelId, definition.kind(), entityId, fields);
        LocalDateTime now = DatabaseTimestamp.now(clock);
        R created = transaction.newRecord(definition.table());
        created.set(definition.id(), entityId);
        created.set(definition.novelId(), novelId);
        definition.write(created, fields);
        created.set(definition.createdAt(), now);
        created.set(definition.updatedAt(), now);
        created.insert();
        return new LoreEntityMutationResult(snapshot(definition, created), true);
    }

    private <R extends UpdatableRecord<R>> LoreEntitySnapshot updateEntity(
            DSLContext transaction,
            String novelId,
            String entityId,
            LoreEntityPatch patch,
            OffsetDateTime expectedUpdatedAt,
            LoreEntityDefinitions.EntityDefinition<R> definition) {
        R current = transaction.selectFrom(definition.table())
                .where(
                        definition.id().eq(entityId),
                        definition.novelId().eq(novelId))
                .forUpdate()
                .fetchOne();
        if (current == null) {
            throw entityNotFound();
        }
        LoreTransactionGuard.requireVersion(
                current.get(definition.updatedAt()),
                expectedUpdatedAt,
                "LORE_ENTITY_VERSION_CONFLICT");
        Map<String, Object> before = definition.snapshot(current);
        boolean changed = patch.fields().entrySet().stream()
                .anyMatch(entry -> !Objects.equals(
                        before.get(entry.getKey()), entry.getValue()));
        if (changed) {
            validateEntityLinks(
                    transaction,
                    novelId,
                    definition.kind(),
                    entityId,
                    patch.fields());
            definition.write(current, patch.fields());
            current.set(
                    definition.updatedAt(),
                    DatabaseTimestamp.next(clock, current.get(definition.updatedAt())));
            current.store();
        }
        return snapshot(definition, current);
    }

    private <R extends UpdatableRecord<R>> DeleteImpactResponse deleteEntity(
            DSLContext transaction,
            String novelId,
            String entityId,
            OffsetDateTime expectedUpdatedAt,
            LoreEntityDefinitions.EntityDefinition<R> definition) {
        R current = transaction.selectFrom(definition.table())
                .where(
                        definition.id().eq(entityId),
                        definition.novelId().eq(novelId))
                .forUpdate()
                .fetchOne();
        if (current == null) {
            throw entityNotFound();
        }
        LoreTransactionGuard.requireVersion(
                current.get(definition.updatedAt()),
                expectedUpdatedAt,
                "LORE_ENTITY_VERSION_CONFLICT");
        Map<String, Integer> references = deleteReferences(
                transaction, definition.kind(), entityId);
        if (!references.isEmpty()) {
            throw new ApiException(
                    409,
                    "LORE_ENTITY_REFERENCED",
                    "设定实体仍被引用，不能删除",
                    references);
        }
        current.delete();
        return deleteImpact(definition.kind().value(), entityId, Map.of());
    }

    private static <R extends UpdatableRecord<R>> LoreEntitySnapshot snapshot(
            LoreEntityDefinitions.EntityDefinition<R> definition, R record) {
        return new LoreEntitySnapshot(
                definition.kind(),
                record.get(definition.id()),
                definition.snapshot(record),
                DatabaseTimestamp.api(record.get(definition.createdAt())),
                DatabaseTimestamp.api(record.get(definition.updatedAt())));
    }

    private static void validateEntityLinks(
            DSLContext transaction,
            String novelId,
            LoreEntityKind kind,
            String entityId,
            Map<String, Object> fields) {
        switch (kind) {
            case CHARACTERS -> validateOptionalLink(
                    transaction,
                    fields,
                    "factionId",
                    FACTION.ID,
                    FACTION.NOVELID,
                    novelId,
                    "势力");
            case ITEMS -> validateOptionalLink(
                    transaction,
                    fields,
                    "ownerId",
                    CHARACTER.ID,
                    CHARACTER.NOVELID,
                    novelId,
                    "角色");
            case LOCATIONS -> validateLocationParent(
                    transaction, novelId, entityId, fields);
            case FACTIONS -> validateOptionalLink(
                    transaction,
                    fields,
                    "baseId",
                    LOCATION.ID,
                    LOCATION.NOVELID,
                    novelId,
                    "地点");
            case GLOSSARY -> {
                // 术语没有外部引用字段。
            }
        }
    }

    private static <R extends org.jooq.Record> void validateOptionalLink(
            DSLContext transaction,
            Map<String, Object> fields,
            String fieldName,
            org.jooq.TableField<R, String> idField,
            org.jooq.TableField<R, String> novelField,
            String novelId,
            String label) {
        if (!fields.containsKey(fieldName) || fields.get(fieldName) == null) {
            return;
        }
        requireRelated(
                transaction,
                idField,
                novelField,
                (String) fields.get(fieldName),
                novelId,
                label);
    }

    private static void validateLocationParent(
            DSLContext transaction,
            String novelId,
            String entityId,
            Map<String, Object> fields) {
        if (!fields.containsKey("parentId") || fields.get("parentId") == null) {
            return;
        }
        String parentId = (String) fields.get("parentId");
        requireRelated(
                transaction,
                LOCATION.ID,
                LOCATION.NOVELID,
                parentId,
                novelId,
                "地点");
        if (parentId.equals(entityId)) {
            throw new ApiException(
                    422, "LOCATION_CYCLE", "地点不能以自身为父地点");
        }
        String current = parentId;
        java.util.HashSet<String> visited = new java.util.HashSet<>();
        while (current != null && visited.add(current)) {
            if (current.equals(entityId)) {
                throw new ApiException(
                        422, "LOCATION_CYCLE", "地点层级不能形成循环");
            }
            current = transaction.select(LOCATION.PARENTID)
                    .from(LOCATION)
                    .where(LOCATION.ID.eq(current))
                    .fetchOne(LOCATION.PARENTID);
        }
    }

    private static Map<String, Integer> deleteReferences(
            DSLContext transaction, LoreEntityKind kind, String entityId) {
        Map<String, Integer> references = new LinkedHashMap<>();
        switch (kind) {
            case CHARACTERS -> {
                putCount(references, "relations", transaction.fetchCount(
                        CHARACTERRELATION,
                        CHARACTERRELATION.CHARACTERID.eq(entityId)
                                .or(CHARACTERRELATION.TARGETID.eq(entityId))));
                putCount(references, "experiences", transaction.fetchCount(
                        CHARACTEREXPERIENCE,
                        CHARACTEREXPERIENCE.CHARACTERID.eq(entityId)));
                putCount(references, "ownedItems", transaction.fetchCount(
                        ITEM, ITEM.OWNERID.eq(entityId)));
                putCount(references, "stateChanges", transaction.fetchCount(
                        CHARACTERSTATECHANGE,
                        CHARACTERSTATECHANGE.CHARACTERID.eq(entityId)));
            }
            case LOCATIONS -> {
                putCount(references, "childLocations", transaction.fetchCount(
                        LOCATION, LOCATION.PARENTID.eq(entityId)));
                putCount(references, "basedFactions", transaction.fetchCount(
                        FACTION, FACTION.BASEID.eq(entityId)));
                putCount(references, "territoryFactions", transaction.fetchCount(
                        _FACTIONTERRITORIES,
                        _FACTIONTERRITORIES.B.eq(entityId)));
            }
            case FACTIONS -> {
                putCount(references, "characters", transaction.fetchCount(
                        CHARACTER, CHARACTER.FACTIONID.eq(entityId)));
                putCount(references, "territories", transaction.fetchCount(
                        _FACTIONTERRITORIES,
                        _FACTIONTERRITORIES.A.eq(entityId)));
            }
            case ITEMS, GLOSSARY -> {
                // 这两类实体没有现有数据库级反向引用。
            }
        }
        return references;
    }

    private static void putCount(
            Map<String, Integer> target, String name, int count) {
        if (count > 0) target.put(name, count);
    }

    private static <R extends org.jooq.Record> void requireRelated(
            DSLContext context,
            org.jooq.TableField<R, String> idField,
            org.jooq.TableField<R, String> novelField,
            String entityId,
            String novelId,
            String label) {
        String relatedNovel = context.select(novelField)
                .from(idField.getTable())
                .where(idField.eq(entityId))
                .fetchOne(novelField);
        if (relatedNovel == null) {
            throw new ApiException(
                    422, "RELATED_RESOURCE_NOT_FOUND", label + "不存在");
        }
        if (!relatedNovel.equals(novelId)) {
            throw new ApiException(
                    422,
                    "RELATED_RESOURCE_CROSS_NOVEL",
                    label + "不属于当前小说");
        }
    }

    private static DeleteImpactResponse deleteImpact(
            String type, String id, Map<String, Integer> affected) {
        DeleteImpactResponse response = new DeleteImpactResponse();
        response.setDeletedType(DeleteImpactResponse.DeletedTypeEnum.fromValue(type));
        response.setDeletedId(id);
        response.setAffected(affected);
        return response;
    }

    private static ApiException createConflict() {
        return new ApiException(
                409, "RESOURCE_CREATE_CONFLICT", "创建请求已绑定其他内容");
    }

    private static ApiException entityNotFound() {
        return new ApiException(404, "LORE_NOT_FOUND", "设定资源不存在");
    }
}
