package cn.inkforge.core.lore.application;

import cn.inkforge.contracts.api.CharacterResponse;
import cn.inkforge.contracts.api.ContentRequest;
import cn.inkforge.contracts.api.ContentResponse;
import cn.inkforge.contracts.api.CreateCharacterRequest;
import cn.inkforge.contracts.api.CreateCharacterResponse;
import cn.inkforge.contracts.api.CreateExperienceRequest;
import cn.inkforge.contracts.api.CreateExperienceResponse;
import cn.inkforge.contracts.api.CreateFactionRequest;
import cn.inkforge.contracts.api.CreateFactionResponse;
import cn.inkforge.contracts.api.CreateGlossaryRequest;
import cn.inkforge.contracts.api.CreateGlossaryResponse;
import cn.inkforge.contracts.api.CreateItemRequest;
import cn.inkforge.contracts.api.CreateItemResponse;
import cn.inkforge.contracts.api.CreateLocationRequest;
import cn.inkforge.contracts.api.CreateLocationResponse;
import cn.inkforge.contracts.api.CreateRelationRequest;
import cn.inkforge.contracts.api.CreateRelationResponse;
import cn.inkforge.contracts.api.DeleteEntityRequest;
import cn.inkforge.contracts.api.DeleteImpactResponse;
import cn.inkforge.contracts.api.ExperienceResponse;
import cn.inkforge.contracts.api.FactionResponse;
import cn.inkforge.contracts.api.GlossaryResponse;
import cn.inkforge.contracts.api.ItemResponse;
import cn.inkforge.contracts.api.LocationResponse;
import cn.inkforge.contracts.api.RelationResponse;
import cn.inkforge.contracts.api.UpdateCharacterRequest;
import cn.inkforge.contracts.api.UpdateExperienceRequest;
import cn.inkforge.contracts.api.UpdateFactionRequest;
import cn.inkforge.contracts.api.UpdateGlossaryRequest;
import cn.inkforge.contracts.api.UpdateItemRequest;
import cn.inkforge.contracts.api.UpdateLocationRequest;
import cn.inkforge.contracts.api.UpdateRelationRequest;
import cn.inkforge.contracts.api.WritingBibleRequest;
import cn.inkforge.contracts.api.WritingBibleResponse;
import cn.inkforge.core.lore.domain.ContentKind;
import cn.inkforge.core.lore.domain.ExperiencePatch;
import cn.inkforge.core.lore.domain.LoreEntityData;
import cn.inkforge.core.lore.domain.LoreEntityKind;
import cn.inkforge.core.lore.domain.LoreEntityPatch;
import cn.inkforge.core.lore.domain.RelationPatch;
import cn.inkforge.core.lore.domain.WritingBiblePatch;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.http.RequiredRequestField;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.function.Function;
import org.openapitools.jackson.nullable.JsonNullable;

/**
 * 人物、世界观和关系资料的公共用例层。
 *
 * <p>本层把 OpenAPI 的可空/缺省语义转换成领域 patch，统一必填字段、空更新和产品长度限制；归属、幂等、
 * CAS 与跨实体引用完整性由仓储在事务中重验。故事进展、背景、世界观和写作圣经保持独立数据层。
 */
public final class LoreService {

    private static final int STORY_PROGRESS_LIMIT = 30_000;
    private static final Map<LoreEntityKind, Set<String>> REQUIRED_FIELDS = Map.of(
            LoreEntityKind.CHARACTERS, Set.of("name", "currentStatus"),
            LoreEntityKind.ITEMS, Set.of("name"),
            LoreEntityKind.LOCATIONS, Set.of("name"),
            LoreEntityKind.FACTIONS, Set.of("name"),
            LoreEntityKind.GLOSSARY, Set.of("term", "definition"));

    private final LoreRepository repository;

    public LoreService(LoreRepository repository) {
        this.repository = Objects.requireNonNull(repository);
    }

    public List<CharacterResponse> listCharacters(String userId, String novelId) {
        return list(userId, novelId, LoreEntityKind.CHARACTERS,
                LoreResponseMapper::character);
    }

    public CreateCharacterResponse createCharacter(
            String userId, String novelId, CreateCharacterRequest request) {
        LoreEntityData data = LoreRequestMapper.character(request);
        validateEntity(LoreEntityKind.CHARACTERS, data.fields());
        return LoreResponseMapper.character(repository.createEntity(
                novelId,
                userId,
                LoreEntityKind.CHARACTERS,
                request.getClientRequestId(),
                data));
    }

    public CharacterResponse updateCharacter(
            String userId,
            String novelId,
            String entityId,
            UpdateCharacterRequest request) {
        return LoreResponseMapper.character(updateEntity(
                userId,
                novelId,
                LoreEntityKind.CHARACTERS,
                entityId,
                LoreRequestMapper.character(request),
                request.getExpectedUpdatedAt()));
    }

    public List<ItemResponse> listItems(String userId, String novelId) {
        return list(userId, novelId, LoreEntityKind.ITEMS, LoreResponseMapper::item);
    }

    public CreateItemResponse createItem(
            String userId, String novelId, CreateItemRequest request) {
        LoreEntityData data = LoreRequestMapper.item(request);
        validateEntity(LoreEntityKind.ITEMS, data.fields());
        return LoreResponseMapper.item(repository.createEntity(
                novelId, userId, LoreEntityKind.ITEMS,
                request.getClientRequestId(), data));
    }

    public ItemResponse updateItem(
            String userId,
            String novelId,
            String entityId,
            UpdateItemRequest request) {
        return LoreResponseMapper.item(updateEntity(
                userId, novelId, LoreEntityKind.ITEMS, entityId,
                LoreRequestMapper.item(request), request.getExpectedUpdatedAt()));
    }

    public List<LocationResponse> listLocations(String userId, String novelId) {
        return list(userId, novelId, LoreEntityKind.LOCATIONS,
                LoreResponseMapper::location);
    }

    public CreateLocationResponse createLocation(
            String userId, String novelId, CreateLocationRequest request) {
        LoreEntityData data = LoreRequestMapper.location(request);
        validateEntity(LoreEntityKind.LOCATIONS, data.fields());
        return LoreResponseMapper.location(repository.createEntity(
                novelId, userId, LoreEntityKind.LOCATIONS,
                request.getClientRequestId(), data));
    }

    public LocationResponse updateLocation(
            String userId,
            String novelId,
            String entityId,
            UpdateLocationRequest request) {
        return LoreResponseMapper.location(updateEntity(
                userId, novelId, LoreEntityKind.LOCATIONS, entityId,
                LoreRequestMapper.location(request), request.getExpectedUpdatedAt()));
    }

    public List<FactionResponse> listFactions(String userId, String novelId) {
        return list(userId, novelId, LoreEntityKind.FACTIONS,
                LoreResponseMapper::faction);
    }

    public CreateFactionResponse createFaction(
            String userId, String novelId, CreateFactionRequest request) {
        LoreEntityData data = LoreRequestMapper.faction(request);
        validateEntity(LoreEntityKind.FACTIONS, data.fields());
        return LoreResponseMapper.faction(repository.createEntity(
                novelId, userId, LoreEntityKind.FACTIONS,
                request.getClientRequestId(), data));
    }

    public FactionResponse updateFaction(
            String userId,
            String novelId,
            String entityId,
            UpdateFactionRequest request) {
        return LoreResponseMapper.faction(updateEntity(
                userId, novelId, LoreEntityKind.FACTIONS, entityId,
                LoreRequestMapper.faction(request), request.getExpectedUpdatedAt()));
    }

    public List<GlossaryResponse> listGlossary(String userId, String novelId) {
        return list(userId, novelId, LoreEntityKind.GLOSSARY,
                LoreResponseMapper::glossary);
    }

    public CreateGlossaryResponse createGlossary(
            String userId, String novelId, CreateGlossaryRequest request) {
        LoreEntityData data = LoreRequestMapper.glossary(request);
        validateEntity(LoreEntityKind.GLOSSARY, data.fields());
        return LoreResponseMapper.glossary(repository.createEntity(
                novelId, userId, LoreEntityKind.GLOSSARY,
                request.getClientRequestId(), data));
    }

    public GlossaryResponse updateGlossary(
            String userId,
            String novelId,
            String entityId,
            UpdateGlossaryRequest request) {
        return LoreResponseMapper.glossary(updateEntity(
                userId, novelId, LoreEntityKind.GLOSSARY, entityId,
                LoreRequestMapper.glossary(request), request.getExpectedUpdatedAt()));
    }

    public DeleteImpactResponse deleteEntity(
            String userId,
            String novelId,
            LoreEntityKind kind,
            String entityId,
            DeleteEntityRequest request) {
        return repository.deleteEntity(
                novelId, userId, kind, entityId, request.getExpectedUpdatedAt());
    }

    public CreateExperienceResponse createExperience(
            String userId,
            String novelId,
            String characterId,
            CreateExperienceRequest request) {
        return LoreResponseMapper.experience(repository.createExperience(
                novelId,
                userId,
                characterId,
                request.getClientRequestId(),
                LoreRequestMapper.experience(request)));
    }

    public List<ExperienceResponse> listExperiences(
            String userId, String novelId, String characterId) {
        return repository.listExperiences(novelId, userId, characterId).stream()
                .map(LoreResponseMapper::experience)
                .toList();
    }

    public ExperienceResponse updateExperience(
            String userId,
            String novelId,
            String experienceId,
            UpdateExperienceRequest request) {
        ExperiencePatch patch = LoreRequestMapper.experience(request);
        if (patch.empty()) {
            throw emptyUpdate();
        }
        if ((patch.content().present() && patch.content().value() == null)
                || (patch.order().present() && patch.order().value() == null)) {
            throw new ApiException(
                    422, "LORE_FIELD_REQUIRED", "经历内容和顺序不能为 null");
        }
        return LoreResponseMapper.experience(repository.updateExperience(
                novelId, userId, experienceId, patch, request.getExpectedUpdatedAt()));
    }

    public DeleteImpactResponse deleteExperience(
            String userId,
            String novelId,
            String experienceId,
            DeleteEntityRequest request) {
        return repository.deleteExperience(
                novelId, userId, experienceId, request.getExpectedUpdatedAt());
    }

    public CreateRelationResponse createRelation(
            String userId, String novelId, CreateRelationRequest request) {
        return LoreResponseMapper.relation(repository.createRelation(
                novelId,
                userId,
                request.getClientRequestId(),
                LoreRequestMapper.relation(request)));
    }

    public List<RelationResponse> listRelations(String userId, String novelId) {
        return repository.listRelations(novelId, userId).stream()
                .map(LoreResponseMapper::relation)
                .toList();
    }

    public RelationResponse updateRelation(
            String userId,
            String novelId,
            String relationId,
            UpdateRelationRequest request) {
        RelationPatch patch = LoreRequestMapper.relation(request);
        if (patch.empty()) {
            throw emptyUpdate();
        }
        if ((patch.relationType().present() && patch.relationType().value() == null)
                || (patch.intimacy().present() && patch.intimacy().value() == null)) {
            throw new ApiException(
                    422, "LORE_FIELD_REQUIRED", "关系类型和亲密度不能为 null");
        }
        return LoreResponseMapper.relation(repository.updateRelation(
                novelId, userId, relationId, patch, request.getExpectedUpdatedAt()));
    }

    public DeleteImpactResponse deleteRelation(
            String userId,
            String novelId,
            String relationId,
            DeleteEntityRequest request) {
        return repository.deleteRelation(
                novelId, userId, relationId, request.getExpectedUpdatedAt());
    }

    public ContentResponse saveStoryBackground(
            String userId, String novelId, ContentRequest request) {
        return saveRequiredContent(
                userId, novelId, request, ContentKind.STORY_BACKGROUND);
    }

    public ContentResponse saveWorldSetting(
            String userId, String novelId, ContentRequest request) {
        return saveRequiredContent(
                userId, novelId, request, ContentKind.WORLD_SETTING);
    }

    public ContentResponse saveStoryProgress(
            String userId, String novelId, ContentRequest request) {
        String content = RequiredRequestField.nullable(request.getContent(), "content");
        OffsetDateTime expected = RequiredRequestField.nullable(
                request.getExpectedUpdatedAt(), "expectedUpdatedAt");
        if (content != null
                && content.codePointCount(0, content.length()) > STORY_PROGRESS_LIMIT) {
            // 只限制故事进展摘要；不得借此截断正文、设定或 Agent 结果。
            throw new ApiException(
                    422,
                    "STORY_PROGRESS_TOO_LONG",
                    "故事进度不能超过 30000 个字符");
        }
        return LoreResponseMapper.content(repository.saveStoryProgress(
                novelId, userId, content, expected));
    }

    public WritingBibleResponse saveWritingBible(
            String userId, String novelId, WritingBibleRequest request) {
        OffsetDateTime expected = RequiredRequestField.nullable(
                request.getExpectedUpdatedAt(), "expectedUpdatedAt");
        JsonNullable<WritingBibleRequest.StoryLengthProfileEnum> profile =
                request.getStoryLengthProfile();
        // 长篇/中短篇是创建时确定的产品工作流，不能通过普通写作圣经 patch 偷换模式。
        if (profile != null
                && !profile.isUndefined()
                && profile.orElse(null)
                        == WritingBibleRequest.StoryLengthProfileEnum.SHORT_MEDIUM) {
            throw new ApiException(
                    422,
                    "WRITING_BIBLE_PROFILE_MISMATCH",
                    "长篇作品不能改为中短篇模式");
        }
        WritingBiblePatch patch = LoreRequestMapper.writingBible(request);
        if (patch.empty()) {
            throw emptyUpdate();
        }
        return LoreResponseMapper.writingBible(repository.saveWritingBible(
                novelId, userId, patch, expected));
    }

    private ContentResponse saveRequiredContent(
            String userId,
            String novelId,
            ContentRequest request,
            ContentKind kind) {
        String content = RequiredRequestField.nullable(request.getContent(), "content");
        OffsetDateTime expected = RequiredRequestField.nullable(
                request.getExpectedUpdatedAt(), "expectedUpdatedAt");
        if (content == null) {
            throw new ApiException(
                    422, "LORE_CONTENT_REQUIRED", "内容不能为 null");
        }
        return LoreResponseMapper.content(repository.saveContent(
                novelId, userId, kind, content, expected));
    }

    private cn.inkforge.core.lore.domain.LoreEntitySnapshot updateEntity(
            String userId,
            String novelId,
            LoreEntityKind kind,
            String entityId,
            LoreEntityPatch patch,
            OffsetDateTime expectedUpdatedAt) {
        if (patch.empty()) {
            throw emptyUpdate();
        }
        validateEntity(kind, patch.fields());
        return repository.updateEntity(
                novelId, userId, kind, entityId, patch, expectedUpdatedAt);
    }

    private <T> List<T> list(
            String userId,
            String novelId,
            LoreEntityKind kind,
            Function<cn.inkforge.core.lore.domain.LoreEntitySnapshot, T> mapper) {
        return repository.listEntities(novelId, userId, kind).stream()
                .map(mapper)
                .toList();
    }

    private static void validateEntity(
            LoreEntityKind kind, Map<String, Object> fields) {
        for (String field : REQUIRED_FIELDS.get(kind)) {
            if (fields.containsKey(field) && fields.get(field) == null) {
                throw new ApiException(
                        422, "LORE_FIELD_REQUIRED", "该字段不能为 null");
            }
        }
        String nameField = kind == LoreEntityKind.GLOSSARY ? "term" : "name";
        Object value = fields.get(nameField);
        if (value instanceof String text && text.strip().isEmpty()) {
            throw new ApiException(
                    422, "LORE_NAME_REQUIRED", "名称不能为空");
        }
    }

    private static ApiException emptyUpdate() {
        return new ApiException(422, "EMPTY_UPDATE", "至少需要提供一个更新字段");
    }
}
