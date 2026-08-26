package cn.inkforge.core.novels.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHARACTER;
import static cn.inkforge.core.db.generated.Tables.CHARACTEREXPERIENCE;
import static cn.inkforge.core.db.generated.Tables.CHARACTERRELATION;
import static cn.inkforge.core.db.generated.Tables.FACTION;
import static cn.inkforge.core.db.generated.Tables.GLOSSARY;
import static cn.inkforge.core.db.generated.Tables.ITEM;
import static cn.inkforge.core.db.generated.Tables.LOCATION;

import cn.inkforge.contracts.api.CharacterDto;
import cn.inkforge.contracts.api.CharacterExperienceDto;
import cn.inkforge.contracts.api.CharacterRelationDto;
import cn.inkforge.contracts.api.CharacterStatus;
import cn.inkforge.contracts.api.FactionDto;
import cn.inkforge.contracts.api.FactionSummary;
import cn.inkforge.contracts.api.GlossaryDto;
import cn.inkforge.contracts.api.ItemDto;
import cn.inkforge.contracts.api.LocationDto;
import cn.inkforge.contracts.api.OwnerSummary;
import cn.inkforge.contracts.api.RelationPeer;
import cn.inkforge.contracts.api.RelationType;
import cn.inkforge.contracts.api.WorkspaceLoreResponse;
import cn.inkforge.core.db.generated.tables.records.CharacterRecord;
import cn.inkforge.core.db.generated.tables.records.CharacterexperienceRecord;
import cn.inkforge.core.db.generated.tables.records.CharacterrelationRecord;
import cn.inkforge.core.db.generated.tables.records.FactionRecord;
import cn.inkforge.core.db.generated.tables.records.GlossaryRecord;
import cn.inkforge.core.db.generated.tables.records.ItemRecord;
import cn.inkforge.core.db.generated.tables.records.LocationRecord;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.jooq.DSLContext;

/** 设定工作区批量读模型；关系和经历查询数量不随人物数量线性增长。 */
final class WorkspaceLoreReader {

    WorkspaceLoreResponse read(DSLContext context, String novelId) {
        List<CharacterRecord> characters = context.selectFrom(CHARACTER)
                .where(CHARACTER.NOVELID.eq(novelId))
                .orderBy(CHARACTER.UPDATEDAT.desc(), CHARACTER.ID.asc())
                .fetch();
        List<String> characterIds = characters.stream().map(CharacterRecord::getId).toList();
        List<CharacterexperienceRecord> experiences = characterIds.isEmpty()
                ? List.of()
                : context.selectFrom(CHARACTEREXPERIENCE)
                        .where(CHARACTEREXPERIENCE.CHARACTERID.in(characterIds))
                        .orderBy(CHARACTEREXPERIENCE.ORDER.asc(), CHARACTEREXPERIENCE.ID.asc())
                        .fetch();
        List<CharacterrelationRecord> relations = characterIds.isEmpty()
                ? List.of()
                : context.selectFrom(CHARACTERRELATION)
                        .where(CHARACTERRELATION.CHARACTERID.in(characterIds)
                                .or(CHARACTERRELATION.TARGETID.in(characterIds)))
                        .orderBy(
                                CHARACTERRELATION.CREATEDAT.asc(),
                                CHARACTERRELATION.ID.asc())
                        .fetch();
        List<FactionRecord> factions = context.selectFrom(FACTION)
                .where(FACTION.NOVELID.eq(novelId))
                .orderBy(FACTION.UPDATEDAT.desc(), FACTION.ID.asc())
                .fetch();
        List<ItemRecord> items = context.selectFrom(ITEM)
                .where(ITEM.NOVELID.eq(novelId))
                .orderBy(ITEM.UPDATEDAT.desc(), ITEM.ID.asc())
                .fetch();
        List<LocationRecord> locations = context.selectFrom(LOCATION)
                .where(LOCATION.NOVELID.eq(novelId))
                .orderBy(LOCATION.UPDATEDAT.desc(), LOCATION.ID.asc())
                .fetch();
        List<GlossaryRecord> glossaries = context.selectFrom(GLOSSARY)
                .where(GLOSSARY.NOVELID.eq(novelId))
                .orderBy(GLOSSARY.UPDATEDAT.desc(), GLOSSARY.ID.asc())
                .fetch();

        Map<String, CharacterRecord> characterById = new HashMap<>();
        characters.forEach(value -> characterById.put(value.getId(), value));
        Map<String, FactionRecord> factionById = new HashMap<>();
        factions.forEach(value -> factionById.put(value.getId(), value));
        Map<String, List<CharacterexperienceRecord>> experiencesByCharacter = new HashMap<>();
        experiences.forEach(value -> experiencesByCharacter
                .computeIfAbsent(value.getCharacterid(), ignored -> new ArrayList<>())
                .add(value));
        Map<String, List<CharacterrelationRecord>> outgoing = new HashMap<>();
        Map<String, List<CharacterrelationRecord>> incoming = new HashMap<>();
        relations.forEach(value -> {
            outgoing.computeIfAbsent(value.getCharacterid(), ignored -> new ArrayList<>())
                    .add(value);
            incoming.computeIfAbsent(value.getTargetid(), ignored -> new ArrayList<>())
                    .add(value);
        });

        WorkspaceLoreResponse result = new WorkspaceLoreResponse();
        result.setCharacters(characters.stream()
                .map(value -> character(
                        value,
                        factionById,
                        characterById,
                        experiencesByCharacter.getOrDefault(value.getId(), List.of()),
                        outgoing.getOrDefault(value.getId(), List.of()),
                        incoming.getOrDefault(value.getId(), List.of())))
                .toList());
        result.setItems(items.stream().map(value -> item(value, characterById)).toList());
        result.setLocations(locations.stream().map(WorkspaceLoreReader::location).toList());
        result.setFactions(factions.stream().map(WorkspaceLoreReader::faction).toList());
        result.setGlossaries(glossaries.stream().map(WorkspaceLoreReader::glossary).toList());
        return result;
    }

    private static CharacterDto character(
            CharacterRecord value,
            Map<String, FactionRecord> factions,
            Map<String, CharacterRecord> characters,
            List<CharacterexperienceRecord> experiences,
            List<CharacterrelationRecord> outgoing,
            List<CharacterrelationRecord> incoming) {
        CharacterDto result = new CharacterDto();
        result.setId(value.getId());
        result.setName(value.getName());
        result.setAliases(value.getAliases());
        result.setGender(value.getGender());
        result.setAge(value.getAge());
        result.setAppearance(value.getAppearance());
        result.setPersonality(value.getPersonality());
        result.setIdentity(value.getIdentity());
        result.setBackground(value.getBackground());
        result.setCoreDesire(value.getCoredesire());
        result.setBehaviorBoundaries(value.getBehaviorboundaries());
        result.setSpeechStyle(value.getSpeechstyle());
        result.setRelationshipPrinciples(value.getRelationshipprinciples());
        result.setShortTermGoal(value.getShorttermgoal());
        result.setFactionId(value.getFactionid());
        FactionRecord faction = factions.get(value.getFactionid());
        result.setFaction(faction == null
                ? null
                : new FactionSummary(faction.getId(), faction.getName()));
        result.setPowerLevel(value.getPowerlevel());
        result.setCombatAbility(value.getCombatability());
        result.setSpecialSkills(value.getSpecialskills());
        result.setCurrentStatus(CharacterStatus.fromValue(value.getCurrentstatus().getLiteral()));
        result.setStatusNote(value.getStatusnote());
        result.setExperiences(experiences.stream()
                .map(WorkspaceLoreReader::experience)
                .toList());
        result.setOutgoingRelations(outgoing.stream()
                .map(relation -> relation(relation, characters, false))
                .toList());
        result.setIncomingRelations(incoming.stream()
                .map(relation -> relation(relation, characters, true))
                .toList());
        result.setCreatedAt(DatabaseTimestamp.api(value.getCreatedat()));
        result.setUpdatedAt(DatabaseTimestamp.api(value.getUpdatedat()));
        return result;
    }

    private static CharacterExperienceDto experience(CharacterexperienceRecord value) {
        return new CharacterExperienceDto(
                value.getChapterid(),
                value.getContent(),
                DatabaseTimestamp.api(value.getCreatedat()),
                value.getId(),
                value.getOrder(),
                DatabaseTimestamp.api(value.getUpdatedat()));
    }

    private static CharacterRelationDto relation(
            CharacterrelationRecord value,
            Map<String, CharacterRecord> characters,
            boolean incoming) {
        CharacterRelationDto result = new CharacterRelationDto();
        result.setId(value.getId());
        result.setCharacterId(value.getCharacterid());
        result.setTargetId(value.getTargetid());
        result.setRelationType(RelationType.fromValue(value.getRelationtype().getLiteral()));
        result.setIntimacy(value.getIntimacy());
        result.setDescription(value.getDescription());
        result.setStartDate(value.getStartdate());
        result.setEndDate(value.getEnddate());
        CharacterRecord source = characters.get(value.getCharacterid());
        CharacterRecord target = characters.get(value.getTargetid());
        result.setCharacter(incoming && source != null
                ? new RelationPeer(source.getId(), source.getName())
                : null);
        result.setTarget(!incoming && target != null
                ? new RelationPeer(target.getId(), target.getName())
                : null);
        result.setCreatedAt(DatabaseTimestamp.api(value.getCreatedat()));
        result.setUpdatedAt(DatabaseTimestamp.api(value.getUpdatedat()));
        return result;
    }

    private static ItemDto item(
            ItemRecord value, Map<String, CharacterRecord> characters) {
        ItemDto result = new ItemDto();
        result.setId(value.getId());
        result.setName(value.getName());
        result.setAliases(value.getAliases());
        result.setType(value.getType());
        result.setRarity(value.getRarity());
        result.setEffect(value.getEffect());
        result.setOrigin(value.getOrigin());
        result.setDescription(value.getDescription());
        result.setOwnerId(value.getOwnerid());
        CharacterRecord owner = characters.get(value.getOwnerid());
        result.setOwner(owner == null ? null : new OwnerSummary(owner.getId(), owner.getName()));
        result.setCreatedAt(DatabaseTimestamp.api(value.getCreatedat()));
        result.setUpdatedAt(DatabaseTimestamp.api(value.getUpdatedat()));
        return result;
    }

    private static LocationDto location(LocationRecord value) {
        return new LocationDto(
                value.getAliases(),
                value.getClimate(),
                DatabaseTimestamp.api(value.getCreatedat()),
                value.getCulture(),
                value.getDescription(),
                value.getId(),
                value.getName(),
                value.getParentid(),
                value.getType(),
                DatabaseTimestamp.api(value.getUpdatedat()));
    }

    private static FactionDto faction(FactionRecord value) {
        return new FactionDto(
                value.getAliases(),
                value.getBaseid(),
                DatabaseTimestamp.api(value.getCreatedat()),
                value.getDescription(),
                value.getId(),
                value.getName(),
                value.getType(),
                DatabaseTimestamp.api(value.getUpdatedat()));
    }

    private static GlossaryDto glossary(GlossaryRecord value) {
        return new GlossaryDto(
                value.getCategory(),
                DatabaseTimestamp.api(value.getCreatedat()),
                value.getDefinition(),
                value.getId(),
                value.getTerm(),
                DatabaseTimestamp.api(value.getUpdatedat()));
    }
}
