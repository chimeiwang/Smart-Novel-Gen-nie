package cn.inkforge.core.lore.application;

import cn.inkforge.contracts.api.CharacterResponse;
import cn.inkforge.contracts.api.ContentResponse;
import cn.inkforge.contracts.api.CreateCharacterResponse;
import cn.inkforge.contracts.api.CreateExperienceResponse;
import cn.inkforge.contracts.api.CreateFactionResponse;
import cn.inkforge.contracts.api.CreateGlossaryResponse;
import cn.inkforge.contracts.api.CreateItemResponse;
import cn.inkforge.contracts.api.CreateLocationResponse;
import cn.inkforge.contracts.api.CreateRelationResponse;
import cn.inkforge.contracts.api.ExperienceResponse;
import cn.inkforge.contracts.api.FactionResponse;
import cn.inkforge.contracts.api.GlossaryResponse;
import cn.inkforge.contracts.api.ItemResponse;
import cn.inkforge.contracts.api.LocationResponse;
import cn.inkforge.contracts.api.RelationResponse;
import cn.inkforge.contracts.api.WritingBibleResponse;
import cn.inkforge.core.lore.domain.ContentSnapshot;
import cn.inkforge.core.lore.domain.ExperienceMutationResult;
import cn.inkforge.core.lore.domain.ExperienceSnapshot;
import cn.inkforge.core.lore.domain.LoreEntityMutationResult;
import cn.inkforge.core.lore.domain.LoreEntitySnapshot;
import cn.inkforge.core.lore.domain.RelationMutationResult;
import cn.inkforge.core.lore.domain.RelationSnapshot;
import cn.inkforge.core.lore.domain.WritingBibleSnapshot;
import java.util.Map;

/** 设定领域快照到冻结 HTTP DTO 的显式映射，避免泄漏 novelId 和控制字段。 */
final class LoreResponseMapper {

    private LoreResponseMapper() {}

    static CharacterResponse character(LoreEntitySnapshot source) {
        Map<String, Object> fields = source.fields();
        CharacterResponse result = new CharacterResponse();
        result.setId(source.id());
        result.setName(text(fields, "name"));
        result.setAliases(text(fields, "aliases"));
        result.setGender(text(fields, "gender"));
        result.setAge(text(fields, "age"));
        result.setAppearance(text(fields, "appearance"));
        result.setPersonality(text(fields, "personality"));
        result.setIdentity(text(fields, "identity"));
        result.setBackground(text(fields, "background"));
        result.setCoreDesire(text(fields, "coreDesire"));
        result.setBehaviorBoundaries(text(fields, "behaviorBoundaries"));
        result.setSpeechStyle(text(fields, "speechStyle"));
        result.setRelationshipPrinciples(text(fields, "relationshipPrinciples"));
        result.setShortTermGoal(text(fields, "shortTermGoal"));
        result.setFactionId(text(fields, "factionId"));
        result.setPowerLevel(text(fields, "powerLevel"));
        result.setCombatAbility(text(fields, "combatAbility"));
        result.setSpecialSkills(text(fields, "specialSkills"));
        result.setCurrentStatus(CharacterResponse.CurrentStatusEnum.fromValue(
                text(fields, "currentStatus")));
        result.setStatusNote(text(fields, "statusNote"));
        result.setCreatedAt(source.createdAt());
        result.setUpdatedAt(source.updatedAt());
        return result;
    }

    static CreateCharacterResponse character(LoreEntityMutationResult source) {
        LoreEntitySnapshot entity = source.entity();
        Map<String, Object> fields = entity.fields();
        CreateCharacterResponse result = new CreateCharacterResponse();
        result.setId(entity.id());
        result.setName(text(fields, "name"));
        result.setAliases(text(fields, "aliases"));
        result.setGender(text(fields, "gender"));
        result.setAge(text(fields, "age"));
        result.setAppearance(text(fields, "appearance"));
        result.setPersonality(text(fields, "personality"));
        result.setIdentity(text(fields, "identity"));
        result.setBackground(text(fields, "background"));
        result.setCoreDesire(text(fields, "coreDesire"));
        result.setBehaviorBoundaries(text(fields, "behaviorBoundaries"));
        result.setSpeechStyle(text(fields, "speechStyle"));
        result.setRelationshipPrinciples(text(fields, "relationshipPrinciples"));
        result.setShortTermGoal(text(fields, "shortTermGoal"));
        result.setFactionId(text(fields, "factionId"));
        result.setPowerLevel(text(fields, "powerLevel"));
        result.setCombatAbility(text(fields, "combatAbility"));
        result.setSpecialSkills(text(fields, "specialSkills"));
        result.setCurrentStatus(CreateCharacterResponse.CurrentStatusEnum.fromValue(
                text(fields, "currentStatus")));
        result.setStatusNote(text(fields, "statusNote"));
        result.setCreatedAt(entity.createdAt());
        result.setUpdatedAt(entity.updatedAt());
        result.setEffective(source.effective());
        return result;
    }

    static ItemResponse item(LoreEntitySnapshot source) {
        Map<String, Object> fields = source.fields();
        ItemResponse result = new ItemResponse();
        fillItem(result, source, fields);
        return result;
    }

    static CreateItemResponse item(LoreEntityMutationResult source) {
        LoreEntitySnapshot entity = source.entity();
        Map<String, Object> fields = entity.fields();
        CreateItemResponse result = new CreateItemResponse();
        result.setId(entity.id());
        result.setName(text(fields, "name"));
        result.setAliases(text(fields, "aliases"));
        result.setType(text(fields, "type"));
        result.setRarity(text(fields, "rarity"));
        result.setEffect(text(fields, "effect"));
        result.setOrigin(text(fields, "origin"));
        result.setDescription(text(fields, "description"));
        result.setOwnerId(text(fields, "ownerId"));
        result.setCreatedAt(entity.createdAt());
        result.setUpdatedAt(entity.updatedAt());
        result.setEffective(source.effective());
        return result;
    }

    static LocationResponse location(LoreEntitySnapshot source) {
        Map<String, Object> fields = source.fields();
        LocationResponse result = new LocationResponse();
        result.setId(source.id());
        result.setName(text(fields, "name"));
        result.setAliases(text(fields, "aliases"));
        result.setType(text(fields, "type"));
        result.setParentId(text(fields, "parentId"));
        result.setClimate(text(fields, "climate"));
        result.setCulture(text(fields, "culture"));
        result.setDescription(text(fields, "description"));
        result.setCreatedAt(source.createdAt());
        result.setUpdatedAt(source.updatedAt());
        return result;
    }

    static CreateLocationResponse location(LoreEntityMutationResult source) {
        LoreEntitySnapshot entity = source.entity();
        Map<String, Object> fields = entity.fields();
        CreateLocationResponse result = new CreateLocationResponse();
        result.setId(entity.id());
        result.setName(text(fields, "name"));
        result.setAliases(text(fields, "aliases"));
        result.setType(text(fields, "type"));
        result.setParentId(text(fields, "parentId"));
        result.setClimate(text(fields, "climate"));
        result.setCulture(text(fields, "culture"));
        result.setDescription(text(fields, "description"));
        result.setCreatedAt(entity.createdAt());
        result.setUpdatedAt(entity.updatedAt());
        result.setEffective(source.effective());
        return result;
    }

    static FactionResponse faction(LoreEntitySnapshot source) {
        Map<String, Object> fields = source.fields();
        FactionResponse result = new FactionResponse();
        result.setId(source.id());
        result.setName(text(fields, "name"));
        result.setAliases(text(fields, "aliases"));
        result.setType(text(fields, "type"));
        result.setBaseId(text(fields, "baseId"));
        result.setDescription(text(fields, "description"));
        result.setCreatedAt(source.createdAt());
        result.setUpdatedAt(source.updatedAt());
        return result;
    }

    static CreateFactionResponse faction(LoreEntityMutationResult source) {
        LoreEntitySnapshot entity = source.entity();
        Map<String, Object> fields = entity.fields();
        CreateFactionResponse result = new CreateFactionResponse();
        result.setId(entity.id());
        result.setName(text(fields, "name"));
        result.setAliases(text(fields, "aliases"));
        result.setType(text(fields, "type"));
        result.setBaseId(text(fields, "baseId"));
        result.setDescription(text(fields, "description"));
        result.setCreatedAt(entity.createdAt());
        result.setUpdatedAt(entity.updatedAt());
        result.setEffective(source.effective());
        return result;
    }

    static GlossaryResponse glossary(LoreEntitySnapshot source) {
        Map<String, Object> fields = source.fields();
        GlossaryResponse result = new GlossaryResponse();
        result.setId(source.id());
        result.setTerm(text(fields, "term"));
        result.setDefinition(text(fields, "definition"));
        result.setCategory(text(fields, "category"));
        result.setCreatedAt(source.createdAt());
        result.setUpdatedAt(source.updatedAt());
        return result;
    }

    static CreateGlossaryResponse glossary(LoreEntityMutationResult source) {
        LoreEntitySnapshot entity = source.entity();
        Map<String, Object> fields = entity.fields();
        CreateGlossaryResponse result = new CreateGlossaryResponse();
        result.setId(entity.id());
        result.setTerm(text(fields, "term"));
        result.setDefinition(text(fields, "definition"));
        result.setCategory(text(fields, "category"));
        result.setCreatedAt(entity.createdAt());
        result.setUpdatedAt(entity.updatedAt());
        result.setEffective(source.effective());
        return result;
    }

    static ExperienceResponse experience(ExperienceSnapshot source) {
        ExperienceResponse result = new ExperienceResponse();
        fillExperience(result, source);
        return result;
    }

    static CreateExperienceResponse experience(ExperienceMutationResult source) {
        ExperienceSnapshot value = source.experience();
        CreateExperienceResponse result = new CreateExperienceResponse();
        result.setId(value.id());
        result.setCharacterId(value.characterId());
        result.setChapterId(value.chapterId());
        result.setContent(value.content());
        result.setOrder(value.order());
        result.setCreatedAt(value.createdAt());
        result.setUpdatedAt(value.updatedAt());
        result.setEffective(source.effective());
        return result;
    }

    static RelationResponse relation(RelationSnapshot source) {
        RelationResponse result = new RelationResponse();
        result.setId(source.id());
        result.setCharacterId(source.characterId());
        result.setTargetId(source.targetId());
        result.setRelationType(RelationResponse.RelationTypeEnum.fromValue(
                source.relationType()));
        result.setIntimacy(source.intimacy());
        result.setDescription(source.description());
        result.setStartDate(source.startDate());
        result.setEndDate(source.endDate());
        result.setCreatedAt(source.createdAt());
        result.setUpdatedAt(source.updatedAt());
        return result;
    }

    static CreateRelationResponse relation(RelationMutationResult source) {
        RelationSnapshot value = source.relation();
        CreateRelationResponse result = new CreateRelationResponse();
        result.setId(value.id());
        result.setCharacterId(value.characterId());
        result.setTargetId(value.targetId());
        result.setRelationType(CreateRelationResponse.RelationTypeEnum.fromValue(
                value.relationType()));
        result.setIntimacy(value.intimacy());
        result.setDescription(value.description());
        result.setStartDate(value.startDate());
        result.setEndDate(value.endDate());
        result.setCreatedAt(value.createdAt());
        result.setUpdatedAt(value.updatedAt());
        result.setEffective(source.effective());
        return result;
    }

    static ContentResponse content(ContentSnapshot source) {
        ContentResponse result = new ContentResponse();
        result.setId(source.id());
        result.setContent(source.content());
        result.setCreatedAt(source.createdAt());
        result.setUpdatedAt(source.updatedAt());
        return result;
    }

    static WritingBibleResponse writingBible(WritingBibleSnapshot source) {
        WritingBibleResponse result = new WritingBibleResponse();
        result.setId(source.id());
        result.setStoryLengthProfile(WritingBibleResponse.StoryLengthProfileEnum.fromValue(
                source.storyLengthProfile()));
        result.setTargetTotalWordCount(source.targetTotalWordCount());
        result.setGenre(source.genre());
        result.setTargetReaders(source.targetReaders());
        result.setCoreSellingPoint(source.coreSellingPoint());
        result.setReaderPromise(source.readerPromise());
        result.setAppealModel(source.appealModel());
        result.setTaboo(source.taboo());
        result.setComparableTitles(source.comparableTitles());
        result.setNotes(source.notes());
        result.setCreatedAt(source.createdAt());
        result.setUpdatedAt(source.updatedAt());
        return result;
    }

    private static void fillItem(
            ItemResponse result,
            LoreEntitySnapshot source,
            Map<String, Object> fields) {
        result.setId(source.id());
        result.setName(text(fields, "name"));
        result.setAliases(text(fields, "aliases"));
        result.setType(text(fields, "type"));
        result.setRarity(text(fields, "rarity"));
        result.setEffect(text(fields, "effect"));
        result.setOrigin(text(fields, "origin"));
        result.setDescription(text(fields, "description"));
        result.setOwnerId(text(fields, "ownerId"));
        result.setCreatedAt(source.createdAt());
        result.setUpdatedAt(source.updatedAt());
    }

    private static void fillExperience(
            ExperienceResponse result, ExperienceSnapshot source) {
        result.setId(source.id());
        result.setCharacterId(source.characterId());
        result.setChapterId(source.chapterId());
        result.setContent(source.content());
        result.setOrder(source.order());
        result.setCreatedAt(source.createdAt());
        result.setUpdatedAt(source.updatedAt());
    }

    private static String text(Map<String, Object> fields, String name) {
        return (String) fields.get(name);
    }
}
