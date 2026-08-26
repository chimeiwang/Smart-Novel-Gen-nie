package cn.inkforge.core.lore.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.CHARACTER;
import static cn.inkforge.core.db.generated.Tables.CHARACTEREXPERIENCE;
import static cn.inkforge.core.db.generated.Tables.CHARACTERRELATION;

import cn.inkforge.contracts.api.DeleteImpactResponse;
import cn.inkforge.core.db.generated.enums.Relationtype;
import cn.inkforge.core.db.generated.tables.records.CharacterexperienceRecord;
import cn.inkforge.core.db.generated.tables.records.CharacterrelationRecord;
import cn.inkforge.core.lore.domain.ExperienceBatchMutationResult;
import cn.inkforge.core.lore.domain.ExperienceData;
import cn.inkforge.core.lore.domain.ExperienceMutation;
import cn.inkforge.core.lore.domain.ExperienceMutationResult;
import cn.inkforge.core.lore.domain.ExperiencePatch;
import cn.inkforge.core.lore.domain.ExperienceSnapshot;
import cn.inkforge.core.lore.domain.MutationAction;
import cn.inkforge.core.lore.domain.RelationData;
import cn.inkforge.core.lore.domain.RelationMutationResult;
import cn.inkforge.core.lore.domain.RelationPatch;
import cn.inkforge.core.lore.domain.RelationSnapshot;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CommandResourceId;
import cn.inkforge.core.platform.patch.PatchField;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import java.time.Clock;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.jooq.DSLContext;
import org.jooq.impl.DSL;

/**
 * 人物经历和人物关系的事务仓储。
 *
 * <p>所有写入在小说级锁内验证人物、章节和目标人物归属，禁止跨小说关系。创建使用确定性 ID 支持安全重放，
 * 更新/删除使用时间戳 CAS；批量经历命令在单事务内全成或全败，避免 Agent 只应用一半设定。
 */
final class JooqLoreRelationshipStore {

    private final CoreDatabase database;
    private final Clock clock;

    JooqLoreRelationshipStore(CoreDatabase database, Clock clock) {
        this.database = database;
        this.clock = clock;
    }

    ExperienceMutationResult createExperience(
            String novelId,
            String userId,
            String characterId,
            String clientRequestId,
            ExperienceData data) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            LoreTransactionGuard.requireOwner(transaction, novelId, userId);
            LoreTransactionGuard.lockNovel(transaction, novelId, userId);
            return createExperienceInTransaction(
                    transaction, novelId, userId, characterId, null, clientRequestId, data);
        });
    }

    List<ExperienceSnapshot> listExperiences(
            String novelId, String userId, String characterId) {
        DSLContext context = database.dsl();
        LoreTransactionGuard.requireOwner(context, novelId, userId);
        requireRelated(
                context,
                CHARACTER.ID,
                CHARACTER.NOVELID,
                characterId,
                novelId,
                "角色");
        return context.selectFrom(CHARACTEREXPERIENCE)
                .where(CHARACTEREXPERIENCE.CHARACTERID.eq(characterId))
                .orderBy(
                        CHARACTEREXPERIENCE.ORDER.asc(),
                        CHARACTEREXPERIENCE.CREATEDAT.asc(),
                        CHARACTEREXPERIENCE.ID.asc())
                .fetch()
                .map(JooqLoreRelationshipStore::experience);
    }

    ExperienceSnapshot updateExperience(
            String novelId,
            String userId,
            String experienceId,
            ExperiencePatch patch,
            OffsetDateTime expectedUpdatedAt) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            LoreTransactionGuard.requireOwner(transaction, novelId, userId);
            LoreTransactionGuard.lockNovel(transaction, novelId, userId);
            return updateExperienceInTransaction(
                    transaction, novelId, experienceId, patch, expectedUpdatedAt);
        });
    }

    DeleteImpactResponse deleteExperience(
            String novelId,
            String userId,
            String experienceId,
            OffsetDateTime expectedUpdatedAt) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            LoreTransactionGuard.requireOwner(transaction, novelId, userId);
            LoreTransactionGuard.lockNovel(transaction, novelId, userId);
            return deleteExperienceInTransaction(
                    transaction, novelId, experienceId, expectedUpdatedAt);
        });
    }

    List<ExperienceBatchMutationResult> applyExperienceMutations(
            String novelId, String userId, List<ExperienceMutation> mutations) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            LoreTransactionGuard.requireOwner(transaction, novelId, userId);
            LoreTransactionGuard.lockNovel(transaction, novelId, userId);
            // 批次共享一个小说写锁和事务；任一条安全字段或归属校验失败都会回滚整个批次。
            List<ExperienceBatchMutationResult> results =
                    new ArrayList<>(mutations.size());
            for (ExperienceMutation mutation : mutations) {
                if (mutation.action() == MutationAction.CREATE) {
                    if (mutation.clientRequestId() == null) {
                        throw new IllegalArgumentException(
                                "角色经历 create 缺少安全控制字段");
                    }
                    ExperienceMutationResult result = createExperienceInTransaction(
                            transaction,
                            novelId,
                            userId,
                            mutation.characterId(),
                            mutation.characterName(),
                            mutation.clientRequestId(),
                            experienceData(mutation.fields()));
                    results.add(new ExperienceBatchMutationResult(
                            mutation.action(), result.experience(), null, result.effective()));
                    continue;
                }
                if (mutation.entityId() == null || mutation.expectedUpdatedAt() == null) {
                    throw new IllegalArgumentException(
                            "角色经历 " + mutation.action().name().toLowerCase()
                                    + " 缺少安全控制字段");
                }
                if (mutation.action() == MutationAction.UPDATE) {
                    ExperienceSnapshot result = updateExperienceInTransaction(
                            transaction,
                            novelId,
                            mutation.entityId(),
                            experiencePatch(mutation.fields()),
                            mutation.expectedUpdatedAt());
                    results.add(new ExperienceBatchMutationResult(
                            mutation.action(), result, null, null));
                } else {
                    DeleteImpactResponse result = deleteExperienceInTransaction(
                            transaction,
                            novelId,
                            mutation.entityId(),
                            mutation.expectedUpdatedAt());
                    results.add(new ExperienceBatchMutationResult(
                            mutation.action(), null, result, null));
                }
            }
            return List.copyOf(results);
        });
    }

    RelationMutationResult createRelation(
            String novelId,
            String userId,
            String clientRequestId,
            RelationData data) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            LoreTransactionGuard.requireOwner(transaction, novelId, userId);
            LoreTransactionGuard.lockNovel(transaction, novelId, userId);
            // 关系两端都必须在当前小说中存在，不能仅凭可猜测 ID 建立跨作品引用。
            String relationId = CommandResourceId.derive(
                    "relations", userId, novelId, clientRequestId);
            CharacterrelationRecord existing = transaction.selectFrom(CHARACTERRELATION)
                    .where(CHARACTERRELATION.ID.eq(relationId))
                    .forUpdate()
                    .fetchOne();
            if (existing != null) {
                if (sameRelation(existing, data)
                        && existing.getCreatedat().equals(existing.getUpdatedat())) {
                    return new RelationMutationResult(relation(existing), false);
                }
                throw createConflict();
            }
            requireCharacter(transaction, data.characterId(), novelId);
            requireCharacter(transaction, data.targetId(), novelId);
            LocalDateTime now = DatabaseTimestamp.now(clock);
            CharacterrelationRecord created = transaction.insertInto(CHARACTERRELATION)
                    .set(CHARACTERRELATION.ID, relationId)
                    .set(CHARACTERRELATION.CHARACTERID, data.characterId())
                    .set(CHARACTERRELATION.TARGETID, data.targetId())
                    .set(CHARACTERRELATION.RELATIONTYPE,
                            Relationtype.lookupLiteral(data.relationType()))
                    .set(CHARACTERRELATION.INTIMACY, data.intimacy())
                    .set(CHARACTERRELATION.DESCRIPTION, data.description())
                    .set(CHARACTERRELATION.STARTDATE, data.startDate())
                    .set(CHARACTERRELATION.ENDDATE, data.endDate())
                    .set(CHARACTERRELATION.CREATEDAT, now)
                    .set(CHARACTERRELATION.UPDATEDAT, now)
                    .returning()
                    .fetchSingle();
            return new RelationMutationResult(relation(created), true);
        });
    }

    List<RelationSnapshot> listRelations(String novelId, String userId) {
        DSLContext context = database.dsl();
        LoreTransactionGuard.requireOwner(context, novelId, userId);
        var characterIds = context.select(CHARACTER.ID)
                .from(CHARACTER)
                .where(CHARACTER.NOVELID.eq(novelId));
        return context.selectFrom(CHARACTERRELATION)
                .where(
                        CHARACTERRELATION.CHARACTERID.in(characterIds),
                        CHARACTERRELATION.TARGETID.in(characterIds))
                .orderBy(
                        CHARACTERRELATION.CREATEDAT.asc(),
                        CHARACTERRELATION.ID.asc())
                .fetch()
                .map(JooqLoreRelationshipStore::relation);
    }

    RelationSnapshot updateRelation(
            String novelId,
            String userId,
            String relationId,
            RelationPatch patch,
            OffsetDateTime expectedUpdatedAt) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            LoreTransactionGuard.requireOwner(transaction, novelId, userId);
            LoreTransactionGuard.lockNovel(transaction, novelId, userId);
            CharacterrelationRecord current = relationForUpdate(
                    transaction, novelId, relationId);
            LoreTransactionGuard.requireVersion(
                    current.getUpdatedat(), expectedUpdatedAt,
                    "LORE_RELATION_VERSION_CONFLICT");
            if (relationChanged(current, patch)) {
                apply(current, patch);
                current.setUpdatedat(DatabaseTimestamp.next(clock, current.getUpdatedat()));
                current.store();
            }
            return relation(current);
        });
    }

    DeleteImpactResponse deleteRelation(
            String novelId,
            String userId,
            String relationId,
            OffsetDateTime expectedUpdatedAt) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            LoreTransactionGuard.requireOwner(transaction, novelId, userId);
            LoreTransactionGuard.lockNovel(transaction, novelId, userId);
            CharacterrelationRecord current = relationForUpdate(
                    transaction, novelId, relationId);
            LoreTransactionGuard.requireVersion(
                    current.getUpdatedat(), expectedUpdatedAt,
                    "LORE_RELATION_VERSION_CONFLICT");
            current.delete();
            return deleteImpact("relation", relationId);
        });
    }

    private ExperienceMutationResult createExperienceInTransaction(
            DSLContext transaction,
            String novelId,
            String userId,
            String characterId,
            String characterName,
            String clientRequestId,
            ExperienceData data) {
        String experienceId = CommandResourceId.derive(
                "experiences", userId, novelId, clientRequestId);
        // 既有确定性 ID 只有在人物绑定与初始内容完全一致时才算重放，更新后的记录不能冒充创建回放。
        CharacterexperienceRecord existing = transaction.selectFrom(CHARACTEREXPERIENCE)
                .where(CHARACTEREXPERIENCE.ID.eq(experienceId))
                .forUpdate()
                .fetchOne();
        if (existing != null) {
            boolean characterMatches;
            if (characterId != null) {
                characterMatches = existing.getCharacterid().equals(characterId);
            } else if (characterName != null) {
                String boundName = transaction.select(CHARACTER.NAME)
                        .from(CHARACTER)
                        .where(
                                CHARACTER.ID.eq(existing.getCharacterid()),
                                CHARACTER.NOVELID.eq(novelId))
                        .fetchOne(CHARACTER.NAME);
                characterMatches = characterName.equals(boundName);
            } else {
                characterMatches = false;
            }
            boolean orderMatches = data.order() == null
                    || Objects.equals(existing.getOrder(), data.order());
            if (characterMatches
                    && Objects.equals(existing.getChapterid(), data.chapterId())
                    && existing.getContent().equals(data.content())
                    && orderMatches
                    && existing.getCreatedat().equals(existing.getUpdatedat())) {
                return new ExperienceMutationResult(experience(existing), false);
            }
            throw createConflict();
        }
        String resolvedCharacter = characterId == null
                ? resolveCharacterId(transaction, novelId, characterName)
                : characterId;
        requireCharacter(transaction, resolvedCharacter, novelId);
        if (data.chapterId() != null) {
            requireRelated(
                    transaction,
                    CHAPTER.ID,
                    CHAPTER.NOVELID,
                    data.chapterId(),
                    novelId,
                    "章节");
        }
        Integer order = data.order();
        if (order == null) {
            Integer maximum = transaction.select(DSL.max(CHARACTEREXPERIENCE.ORDER))
                    .from(CHARACTEREXPERIENCE)
                    .where(CHARACTEREXPERIENCE.CHARACTERID.eq(resolvedCharacter))
                    .fetchOne(DSL.max(CHARACTEREXPERIENCE.ORDER));
            order = (maximum == null ? -1 : maximum) + 1;
        }
        LocalDateTime now = DatabaseTimestamp.now(clock);
        CharacterexperienceRecord created = transaction.insertInto(CHARACTEREXPERIENCE)
                .set(CHARACTEREXPERIENCE.ID, experienceId)
                .set(CHARACTEREXPERIENCE.CHARACTERID, resolvedCharacter)
                .set(CHARACTEREXPERIENCE.CHAPTERID, data.chapterId())
                .set(CHARACTEREXPERIENCE.CONTENT, data.content())
                .set(CHARACTEREXPERIENCE.ORDER, order)
                .set(CHARACTEREXPERIENCE.CREATEDAT, now)
                .set(CHARACTEREXPERIENCE.UPDATEDAT, now)
                .returning()
                .fetchSingle();
        return new ExperienceMutationResult(experience(created), true);
    }

    private ExperienceSnapshot updateExperienceInTransaction(
            DSLContext transaction,
            String novelId,
            String experienceId,
            ExperiencePatch patch,
            OffsetDateTime expectedUpdatedAt) {
        CharacterexperienceRecord current = experienceForUpdate(
                transaction, novelId, experienceId);
        LoreTransactionGuard.requireVersion(
                current.getUpdatedat(), expectedUpdatedAt,
                "LORE_EXPERIENCE_VERSION_CONFLICT");
        if (patch.chapterId().present() && patch.chapterId().value() != null) {
            requireRelated(
                    transaction,
                    CHAPTER.ID,
                    CHAPTER.NOVELID,
                    patch.chapterId().value(),
                    novelId,
                    "章节");
        }
        if (experienceChanged(current, patch)) {
            apply(current, patch);
            current.setUpdatedat(DatabaseTimestamp.next(clock, current.getUpdatedat()));
            current.store();
        }
        return experience(current);
    }

    private static DeleteImpactResponse deleteExperienceInTransaction(
            DSLContext transaction,
            String novelId,
            String experienceId,
            OffsetDateTime expectedUpdatedAt) {
        CharacterexperienceRecord current = experienceForUpdate(
                transaction, novelId, experienceId);
        LoreTransactionGuard.requireVersion(
                current.getUpdatedat(), expectedUpdatedAt,
                "LORE_EXPERIENCE_VERSION_CONFLICT");
        current.delete();
        return deleteImpact("experience", experienceId);
    }

    private static String resolveCharacterId(
            DSLContext transaction, String novelId, String characterName) {
        if (characterName == null) {
            throw new IllegalArgumentException("角色经历无法唯一解析角色");
        }
        List<String> ids = transaction.select(CHARACTER.ID)
                .from(CHARACTER)
                .where(
                        CHARACTER.NOVELID.eq(novelId),
                        CHARACTER.NAME.eq(characterName))
                .limit(2)
                .forUpdate()
                .fetch(CHARACTER.ID);
        if (ids.size() != 1) {
            throw new IllegalArgumentException("角色经历无法唯一解析角色");
        }
        return ids.getFirst();
    }

    private static CharacterexperienceRecord experienceForUpdate(
            DSLContext transaction, String novelId, String experienceId) {
        var characters = transaction.select(CHARACTER.ID)
                .from(CHARACTER)
                .where(CHARACTER.NOVELID.eq(novelId));
        CharacterexperienceRecord value = transaction.selectFrom(CHARACTEREXPERIENCE)
                .where(
                        CHARACTEREXPERIENCE.ID.eq(experienceId),
                        CHARACTEREXPERIENCE.CHARACTERID.in(characters))
                .forUpdate()
                .fetchOne();
        if (value == null) {
            throw new ApiException(404, "EXPERIENCE_NOT_FOUND", "角色经历不存在");
        }
        return value;
    }

    private static CharacterrelationRecord relationForUpdate(
            DSLContext transaction, String novelId, String relationId) {
        var characters = transaction.select(CHARACTER.ID)
                .from(CHARACTER)
                .where(CHARACTER.NOVELID.eq(novelId));
        CharacterrelationRecord value = transaction.selectFrom(CHARACTERRELATION)
                .where(
                        CHARACTERRELATION.ID.eq(relationId),
                        CHARACTERRELATION.CHARACTERID.in(characters),
                        CHARACTERRELATION.TARGETID.in(characters))
                .forUpdate()
                .fetchOne();
        if (value == null) {
            throw new ApiException(404, "RELATION_NOT_FOUND", "人物关系不存在");
        }
        return value;
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
                    422, "RELATED_RESOURCE_CROSS_NOVEL", label + "不属于当前小说");
        }
    }

    private static void requireCharacter(
            DSLContext transaction, String characterId, String novelId) {
        requireRelated(
                transaction,
                CHARACTER.ID,
                CHARACTER.NOVELID,
                characterId,
                novelId,
                "角色");
    }

    private static ExperienceData experienceData(Map<String, Object> fields) {
        return new ExperienceData(
                (String) fields.get("chapterId"),
                (String) fields.get("content"),
                (Integer) fields.get("order"));
    }

    private static ExperiencePatch experiencePatch(Map<String, Object> fields) {
        return new ExperiencePatch(
                patch(fields, "chapterId", String.class),
                patch(fields, "content", String.class),
                patch(fields, "order", Integer.class));
    }

    private static <T> PatchField<T> patch(
            Map<String, Object> fields, String name, Class<T> type) {
        return new PatchField<>(
                fields.containsKey(name),
                fields.get(name) == null ? null : type.cast(fields.get(name)));
    }

    private static boolean experienceChanged(
            CharacterexperienceRecord current, ExperiencePatch patch) {
        return changed(current.getChapterid(), patch.chapterId())
                || changed(current.getContent(), patch.content())
                || changed(current.getOrder(), patch.order());
    }

    private static void apply(
            CharacterexperienceRecord current, ExperiencePatch patch) {
        if (patch.chapterId().present()) current.setChapterid(patch.chapterId().value());
        if (patch.content().present()) current.setContent(patch.content().value());
        if (patch.order().present()) current.setOrder(patch.order().value());
    }

    private static boolean relationChanged(
            CharacterrelationRecord current, RelationPatch patch) {
        return changed(current.getRelationtype().getLiteral(), patch.relationType())
                || changed(current.getIntimacy(), patch.intimacy())
                || changed(current.getDescription(), patch.description())
                || changed(current.getStartdate(), patch.startDate())
                || changed(current.getEnddate(), patch.endDate());
    }

    private static void apply(CharacterrelationRecord current, RelationPatch patch) {
        if (patch.relationType().present()) {
            current.setRelationtype(Relationtype.lookupLiteral(
                    patch.relationType().value()));
        }
        if (patch.intimacy().present()) current.setIntimacy(patch.intimacy().value());
        if (patch.description().present()) {
            current.setDescription(patch.description().value());
        }
        if (patch.startDate().present()) current.setStartdate(patch.startDate().value());
        if (patch.endDate().present()) current.setEnddate(patch.endDate().value());
    }

    private static <T> boolean changed(T current, PatchField<T> patch) {
        return patch.present() && !Objects.equals(current, patch.value());
    }

    private static boolean sameRelation(
            CharacterrelationRecord value, RelationData data) {
        return value.getCharacterid().equals(data.characterId())
                && value.getTargetid().equals(data.targetId())
                && value.getRelationtype().getLiteral().equals(data.relationType())
                && value.getIntimacy() == data.intimacy()
                && Objects.equals(value.getDescription(), data.description())
                && Objects.equals(value.getStartdate(), data.startDate())
                && Objects.equals(value.getEnddate(), data.endDate());
    }

    private static ExperienceSnapshot experience(CharacterexperienceRecord value) {
        return new ExperienceSnapshot(
                value.getId(),
                value.getCharacterid(),
                value.getChapterid(),
                value.getContent(),
                value.getOrder(),
                DatabaseTimestamp.api(value.getCreatedat()),
                DatabaseTimestamp.api(value.getUpdatedat()));
    }

    private static RelationSnapshot relation(CharacterrelationRecord value) {
        return new RelationSnapshot(
                value.getId(),
                value.getCharacterid(),
                value.getTargetid(),
                value.getRelationtype().getLiteral(),
                value.getIntimacy(),
                value.getDescription(),
                value.getStartdate(),
                value.getEnddate(),
                DatabaseTimestamp.api(value.getCreatedat()),
                DatabaseTimestamp.api(value.getUpdatedat()));
    }

    private static DeleteImpactResponse deleteImpact(String type, String id) {
        DeleteImpactResponse response = new DeleteImpactResponse();
        response.setDeletedType(DeleteImpactResponse.DeletedTypeEnum.fromValue(type));
        response.setDeletedId(id);
        response.setAffected(Map.of());
        return response;
    }

    private static ApiException createConflict() {
        return new ApiException(
                409, "RESOURCE_CREATE_CONFLICT", "创建请求已绑定其他内容");
    }
}
