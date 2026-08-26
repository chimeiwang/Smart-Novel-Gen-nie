package cn.inkforge.core.lore.application;

import cn.inkforge.contracts.api.DeleteImpactResponse;
import cn.inkforge.core.lore.domain.ContentKind;
import cn.inkforge.core.lore.domain.ContentSnapshot;
import cn.inkforge.core.lore.domain.ExperienceData;
import cn.inkforge.core.lore.domain.ExperienceBatchMutationResult;
import cn.inkforge.core.lore.domain.ExperienceMutation;
import cn.inkforge.core.lore.domain.ExperienceMutationResult;
import cn.inkforge.core.lore.domain.ExperiencePatch;
import cn.inkforge.core.lore.domain.ExperienceSnapshot;
import cn.inkforge.core.lore.domain.LoreEntityData;
import cn.inkforge.core.lore.domain.EntityMutation;
import cn.inkforge.core.lore.domain.LoreBatchMutationResult;
import cn.inkforge.core.lore.domain.LoreEntityKind;
import cn.inkforge.core.lore.domain.LoreEntityMutationResult;
import cn.inkforge.core.lore.domain.LoreEntityPatch;
import cn.inkforge.core.lore.domain.LoreEntitySnapshot;
import cn.inkforge.core.lore.domain.RelationData;
import cn.inkforge.core.lore.domain.RelationMutationResult;
import cn.inkforge.core.lore.domain.RelationPatch;
import cn.inkforge.core.lore.domain.RelationSnapshot;
import cn.inkforge.core.lore.domain.WritingBiblePatch;
import cn.inkforge.core.lore.domain.WritingBibleSnapshot;
import java.time.OffsetDateTime;
import java.util.List;

/** 长篇设定用例的持久化端口。 */
public interface LoreRepository {

    List<LoreEntitySnapshot> listEntities(
            String novelId, String userId, LoreEntityKind kind);

    LoreEntityMutationResult createEntity(
            String novelId,
            String userId,
            LoreEntityKind kind,
            String clientRequestId,
            LoreEntityData data);

    LoreEntitySnapshot updateEntity(
            String novelId,
            String userId,
            LoreEntityKind kind,
            String entityId,
            LoreEntityPatch patch,
            OffsetDateTime expectedUpdatedAt);

    DeleteImpactResponse deleteEntity(
            String novelId,
            String userId,
            LoreEntityKind kind,
            String entityId,
            OffsetDateTime expectedUpdatedAt);

    List<LoreBatchMutationResult> applyEntityMutations(
            String novelId, String userId, List<EntityMutation> mutations);

    ExperienceMutationResult createExperience(
            String novelId,
            String userId,
            String characterId,
            String clientRequestId,
            ExperienceData data);

    List<ExperienceSnapshot> listExperiences(
            String novelId, String userId, String characterId);

    ExperienceSnapshot updateExperience(
            String novelId,
            String userId,
            String experienceId,
            ExperiencePatch patch,
            OffsetDateTime expectedUpdatedAt);

    DeleteImpactResponse deleteExperience(
            String novelId,
            String userId,
            String experienceId,
            OffsetDateTime expectedUpdatedAt);

    List<ExperienceBatchMutationResult> applyExperienceMutations(
            String novelId, String userId, List<ExperienceMutation> mutations);

    RelationMutationResult createRelation(
            String novelId,
            String userId,
            String clientRequestId,
            RelationData data);

    List<RelationSnapshot> listRelations(String novelId, String userId);

    RelationSnapshot updateRelation(
            String novelId,
            String userId,
            String relationId,
            RelationPatch patch,
            OffsetDateTime expectedUpdatedAt);

    DeleteImpactResponse deleteRelation(
            String novelId,
            String userId,
            String relationId,
            OffsetDateTime expectedUpdatedAt);

    ContentSnapshot saveContent(
            String novelId,
            String userId,
            ContentKind kind,
            String content,
            OffsetDateTime expectedUpdatedAt);

    ContentSnapshot saveStoryProgress(
            String novelId,
            String userId,
            String content,
            OffsetDateTime expectedUpdatedAt);

    WritingBibleSnapshot saveWritingBible(
            String novelId,
            String userId,
            WritingBiblePatch patch,
            OffsetDateTime expectedUpdatedAt);
}
