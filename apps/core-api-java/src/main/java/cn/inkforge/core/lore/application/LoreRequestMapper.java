package cn.inkforge.core.lore.application;

import cn.inkforge.contracts.api.CreateCharacterRequest;
import cn.inkforge.contracts.api.CreateExperienceRequest;
import cn.inkforge.contracts.api.CreateFactionRequest;
import cn.inkforge.contracts.api.CreateGlossaryRequest;
import cn.inkforge.contracts.api.CreateItemRequest;
import cn.inkforge.contracts.api.CreateLocationRequest;
import cn.inkforge.contracts.api.CreateRelationRequest;
import cn.inkforge.contracts.api.UpdateCharacterRequest;
import cn.inkforge.contracts.api.UpdateExperienceRequest;
import cn.inkforge.contracts.api.UpdateFactionRequest;
import cn.inkforge.contracts.api.UpdateGlossaryRequest;
import cn.inkforge.contracts.api.UpdateItemRequest;
import cn.inkforge.contracts.api.UpdateLocationRequest;
import cn.inkforge.contracts.api.UpdateRelationRequest;
import cn.inkforge.contracts.api.WritingBibleRequest;
import cn.inkforge.core.lore.domain.ExperienceData;
import cn.inkforge.core.lore.domain.ExperiencePatch;
import cn.inkforge.core.lore.domain.LoreEntityData;
import cn.inkforge.core.lore.domain.LoreEntityPatch;
import cn.inkforge.core.lore.domain.RelationData;
import cn.inkforge.core.lore.domain.RelationPatch;
import cn.inkforge.core.lore.domain.WritingBiblePatch;
import cn.inkforge.core.platform.patch.PatchField;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.function.Function;
import org.openapitools.jackson.nullable.JsonNullable;

/** 冻结 HTTP DTO 到设定领域值的唯一映射入口。 */
final class LoreRequestMapper {

    private LoreRequestMapper() {}

    static LoreEntityData character(CreateCharacterRequest request) {
        Map<String, Object> fields = new LinkedHashMap<>();
        fields.put("name", request.getName());
        fields.put("aliases", value(request.getAliases()));
        fields.put("gender", value(request.getGender()));
        fields.put("age", value(request.getAge()));
        fields.put("appearance", value(request.getAppearance()));
        fields.put("personality", value(request.getPersonality()));
        fields.put("identity", value(request.getIdentity()));
        fields.put("background", value(request.getBackground()));
        fields.put("coreDesire", value(request.getCoreDesire()));
        fields.put("behaviorBoundaries", value(request.getBehaviorBoundaries()));
        fields.put("speechStyle", value(request.getSpeechStyle()));
        fields.put("relationshipPrinciples", value(request.getRelationshipPrinciples()));
        fields.put("shortTermGoal", value(request.getShortTermGoal()));
        fields.put("factionId", value(request.getFactionId()));
        fields.put("powerLevel", value(request.getPowerLevel()));
        fields.put("combatAbility", value(request.getCombatAbility()));
        fields.put("specialSkills", value(request.getSpecialSkills()));
        fields.put("currentStatus", request.getCurrentStatus().getValue());
        fields.put("statusNote", value(request.getStatusNote()));
        return new LoreEntityData(fields);
    }

    static LoreEntityPatch character(UpdateCharacterRequest request) {
        Map<String, Object> fields = new LinkedHashMap<>();
        put(fields, "name", request.getName());
        put(fields, "aliases", request.getAliases());
        put(fields, "gender", request.getGender());
        put(fields, "age", request.getAge());
        put(fields, "appearance", request.getAppearance());
        put(fields, "personality", request.getPersonality());
        put(fields, "identity", request.getIdentity());
        put(fields, "background", request.getBackground());
        put(fields, "coreDesire", request.getCoreDesire());
        put(fields, "behaviorBoundaries", request.getBehaviorBoundaries());
        put(fields, "speechStyle", request.getSpeechStyle());
        put(fields, "relationshipPrinciples", request.getRelationshipPrinciples());
        put(fields, "shortTermGoal", request.getShortTermGoal());
        put(fields, "factionId", request.getFactionId());
        put(fields, "powerLevel", request.getPowerLevel());
        put(fields, "combatAbility", request.getCombatAbility());
        put(fields, "specialSkills", request.getSpecialSkills());
        put(fields, "currentStatus", request.getCurrentStatus(), value -> value.getValue());
        put(fields, "statusNote", request.getStatusNote());
        return new LoreEntityPatch(fields);
    }

    static LoreEntityData item(CreateItemRequest request) {
        Map<String, Object> fields = new LinkedHashMap<>();
        fields.put("name", request.getName());
        fields.put("aliases", value(request.getAliases()));
        fields.put("type", value(request.getType()));
        fields.put("rarity", value(request.getRarity()));
        fields.put("effect", value(request.getEffect()));
        fields.put("origin", value(request.getOrigin()));
        fields.put("description", value(request.getDescription()));
        fields.put("ownerId", value(request.getOwnerId()));
        return new LoreEntityData(fields);
    }

    static LoreEntityPatch item(UpdateItemRequest request) {
        Map<String, Object> fields = new LinkedHashMap<>();
        put(fields, "name", request.getName());
        put(fields, "aliases", request.getAliases());
        put(fields, "type", request.getType());
        put(fields, "rarity", request.getRarity());
        put(fields, "effect", request.getEffect());
        put(fields, "origin", request.getOrigin());
        put(fields, "description", request.getDescription());
        put(fields, "ownerId", request.getOwnerId());
        return new LoreEntityPatch(fields);
    }

    static LoreEntityData location(CreateLocationRequest request) {
        Map<String, Object> fields = new LinkedHashMap<>();
        fields.put("name", request.getName());
        fields.put("aliases", value(request.getAliases()));
        fields.put("type", value(request.getType()));
        fields.put("parentId", value(request.getParentId()));
        fields.put("climate", value(request.getClimate()));
        fields.put("culture", value(request.getCulture()));
        fields.put("description", value(request.getDescription()));
        return new LoreEntityData(fields);
    }

    static LoreEntityPatch location(UpdateLocationRequest request) {
        Map<String, Object> fields = new LinkedHashMap<>();
        put(fields, "name", request.getName());
        put(fields, "aliases", request.getAliases());
        put(fields, "type", request.getType());
        put(fields, "parentId", request.getParentId());
        put(fields, "climate", request.getClimate());
        put(fields, "culture", request.getCulture());
        put(fields, "description", request.getDescription());
        return new LoreEntityPatch(fields);
    }

    static LoreEntityData faction(CreateFactionRequest request) {
        Map<String, Object> fields = new LinkedHashMap<>();
        fields.put("name", request.getName());
        fields.put("aliases", value(request.getAliases()));
        fields.put("type", value(request.getType()));
        fields.put("baseId", value(request.getBaseId()));
        fields.put("description", value(request.getDescription()));
        return new LoreEntityData(fields);
    }

    static LoreEntityPatch faction(UpdateFactionRequest request) {
        Map<String, Object> fields = new LinkedHashMap<>();
        put(fields, "name", request.getName());
        put(fields, "aliases", request.getAliases());
        put(fields, "type", request.getType());
        put(fields, "baseId", request.getBaseId());
        put(fields, "description", request.getDescription());
        return new LoreEntityPatch(fields);
    }

    static LoreEntityData glossary(CreateGlossaryRequest request) {
        Map<String, Object> fields = new LinkedHashMap<>();
        fields.put("term", request.getTerm());
        fields.put("definition", request.getDefinition());
        fields.put("category", value(request.getCategory()));
        return new LoreEntityData(fields);
    }

    static LoreEntityPatch glossary(UpdateGlossaryRequest request) {
        Map<String, Object> fields = new LinkedHashMap<>();
        put(fields, "term", request.getTerm());
        put(fields, "definition", request.getDefinition());
        put(fields, "category", request.getCategory());
        return new LoreEntityPatch(fields);
    }

    static ExperienceData experience(CreateExperienceRequest request) {
        return new ExperienceData(
                value(request.getChapterId()),
                request.getContent(),
                value(request.getOrder()));
    }

    static ExperiencePatch experience(UpdateExperienceRequest request) {
        return new ExperiencePatch(
                PatchField.from(request.getChapterId()),
                PatchField.from(request.getContent()),
                PatchField.from(request.getOrder()));
    }

    static RelationData relation(CreateRelationRequest request) {
        return new RelationData(
                request.getCharacterId(),
                request.getTargetId(),
                request.getRelationType().getValue(),
                request.getIntimacy(),
                value(request.getDescription()),
                value(request.getStartDate()),
                value(request.getEndDate()));
    }

    static RelationPatch relation(UpdateRelationRequest request) {
        return new RelationPatch(
                PatchField.from(request.getRelationType()).map(value -> value.getValue()),
                PatchField.from(request.getIntimacy()),
                PatchField.from(request.getDescription()),
                PatchField.from(request.getStartDate()),
                PatchField.from(request.getEndDate()));
    }

    static WritingBiblePatch writingBible(WritingBibleRequest request) {
        Map<String, Object> fields = new LinkedHashMap<>();
        putProfile(fields, request.getStoryLengthProfile());
        put(fields, "targetTotalWordCount", request.getTargetTotalWordCount());
        put(fields, "genre", request.getGenre());
        put(fields, "targetReaders", request.getTargetReaders());
        put(fields, "coreSellingPoint", request.getCoreSellingPoint());
        put(fields, "readerPromise", request.getReaderPromise());
        put(fields, "appealModel", request.getAppealModel());
        put(fields, "taboo", request.getTaboo());
        put(fields, "comparableTitles", request.getComparableTitles());
        put(fields, "notes", request.getNotes());
        return new WritingBiblePatch(fields);
    }

    private static <T> T value(JsonNullable<T> value) {
        return value == null || value.isUndefined() ? null : value.orElse(null);
    }

    private static <T> void put(
            Map<String, Object> target, String name, JsonNullable<T> value) {
        put(target, name, value, Function.identity());
    }

    private static <T, R> void put(
            Map<String, Object> target,
            String name,
            JsonNullable<T> value,
            Function<? super T, ? extends R> mapper) {
        if (value != null && !value.isUndefined()) {
            T raw = value.orElse(null);
            target.put(name, raw == null ? null : mapper.apply(raw));
        }
    }

    private static void putProfile(
            Map<String, Object> target,
            JsonNullable<WritingBibleRequest.StoryLengthProfileEnum> value) {
        if (value != null && !value.isUndefined() && value.orElse(null) != null) {
            target.put("storyLengthProfile", value.get().getValue());
        }
    }
}
