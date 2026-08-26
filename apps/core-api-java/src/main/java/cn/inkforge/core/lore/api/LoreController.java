package cn.inkforge.core.lore.api;

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
import cn.inkforge.core.generated.api.LoreApi;
import cn.inkforge.core.identity.application.AuthenticatedUser;
import cn.inkforge.core.identity.application.CurrentUserAccess;
import cn.inkforge.core.lore.application.LoreService;
import cn.inkforge.core.lore.domain.LoreEntityKind;
import cn.inkforge.core.platform.http.ApiException;
import java.util.List;
import java.util.Optional;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RestController;

/** 冻结的 32 个长篇设定 HTTP 接口。 */
@RestController
public final class LoreController implements LoreApi {

    private final Optional<LoreService> configuredService;
    private final Optional<CurrentUserAccess> configuredUsers;

    public LoreController(
            Optional<LoreService> configuredService,
            Optional<CurrentUserAccess> configuredUsers) {
        this.configuredService = configuredService;
        this.configuredUsers = configuredUsers;
    }

    @Override
    public ResponseEntity<CreateCharacterResponse>
            createCharacterApiV1NovelsNovelIdCharactersPost(
                    String novelId,
                    CreateCharacterRequest request,
                    String token) {
        return ResponseEntity.status(201).body(
                service().createCharacter(user(token).id(), novelId, request));
    }

    @Override
    public ResponseEntity<CreateExperienceResponse>
            createExperienceApiV1NovelsNovelIdCharactersCharacterIdExperiencesPost(
                    String novelId,
                    String characterId,
                    CreateExperienceRequest request,
                    String token) {
        return ResponseEntity.status(201).body(service().createExperience(
                user(token).id(), novelId, characterId, request));
    }

    @Override
    public ResponseEntity<CreateFactionResponse>
            createFactionApiV1NovelsNovelIdFactionsPost(
                    String novelId, CreateFactionRequest request, String token) {
        return ResponseEntity.status(201).body(
                service().createFaction(user(token).id(), novelId, request));
    }

    @Override
    public ResponseEntity<CreateGlossaryResponse>
            createGlossaryApiV1NovelsNovelIdGlossaryPost(
                    String novelId, CreateGlossaryRequest request, String token) {
        return ResponseEntity.status(201).body(
                service().createGlossary(user(token).id(), novelId, request));
    }

    @Override
    public ResponseEntity<CreateItemResponse> createItemApiV1NovelsNovelIdItemsPost(
            String novelId, CreateItemRequest request, String token) {
        return ResponseEntity.status(201).body(
                service().createItem(user(token).id(), novelId, request));
    }

    @Override
    public ResponseEntity<CreateLocationResponse>
            createLocationApiV1NovelsNovelIdLocationsPost(
                    String novelId, CreateLocationRequest request, String token) {
        return ResponseEntity.status(201).body(
                service().createLocation(user(token).id(), novelId, request));
    }

    @Override
    public ResponseEntity<CreateRelationResponse>
            createRelationApiV1NovelsNovelIdRelationsPost(
                    String novelId, CreateRelationRequest request, String token) {
        return ResponseEntity.status(201).body(
                service().createRelation(user(token).id(), novelId, request));
    }

    @Override
    public ResponseEntity<DeleteImpactResponse>
            deleteCharacterApiV1NovelsNovelIdCharactersEntityIdDelete(
                    String novelId,
                    String entityId,
                    DeleteEntityRequest request,
                    String token) {
        return ResponseEntity.ok(service().deleteEntity(
                user(token).id(), novelId, LoreEntityKind.CHARACTERS, entityId, request));
    }

    @Override
    public ResponseEntity<DeleteImpactResponse>
            deleteExperienceApiV1NovelsNovelIdExperiencesExperienceIdDelete(
                    String novelId,
                    String experienceId,
                    DeleteEntityRequest request,
                    String token) {
        return ResponseEntity.ok(service().deleteExperience(
                user(token).id(), novelId, experienceId, request));
    }

    @Override
    public ResponseEntity<DeleteImpactResponse>
            deleteFactionApiV1NovelsNovelIdFactionsEntityIdDelete(
                    String novelId,
                    String entityId,
                    DeleteEntityRequest request,
                    String token) {
        return ResponseEntity.ok(service().deleteEntity(
                user(token).id(), novelId, LoreEntityKind.FACTIONS, entityId, request));
    }

    @Override
    public ResponseEntity<DeleteImpactResponse>
            deleteGlossaryApiV1NovelsNovelIdGlossaryEntityIdDelete(
                    String novelId,
                    String entityId,
                    DeleteEntityRequest request,
                    String token) {
        return ResponseEntity.ok(service().deleteEntity(
                user(token).id(), novelId, LoreEntityKind.GLOSSARY, entityId, request));
    }

    @Override
    public ResponseEntity<DeleteImpactResponse>
            deleteItemApiV1NovelsNovelIdItemsEntityIdDelete(
                    String novelId,
                    String entityId,
                    DeleteEntityRequest request,
                    String token) {
        return ResponseEntity.ok(service().deleteEntity(
                user(token).id(), novelId, LoreEntityKind.ITEMS, entityId, request));
    }

    @Override
    public ResponseEntity<DeleteImpactResponse>
            deleteLocationApiV1NovelsNovelIdLocationsEntityIdDelete(
                    String novelId,
                    String entityId,
                    DeleteEntityRequest request,
                    String token) {
        return ResponseEntity.ok(service().deleteEntity(
                user(token).id(), novelId, LoreEntityKind.LOCATIONS, entityId, request));
    }

    @Override
    public ResponseEntity<DeleteImpactResponse>
            deleteRelationApiV1NovelsNovelIdRelationsRelationIdDelete(
                    String novelId,
                    String relationId,
                    DeleteEntityRequest request,
                    String token) {
        return ResponseEntity.ok(service().deleteRelation(
                user(token).id(), novelId, relationId, request));
    }

    @Override
    public ResponseEntity<List<CharacterResponse>>
            listCharactersApiV1NovelsNovelIdCharactersGet(
                    String novelId, String token) {
        return ResponseEntity.ok(service().listCharacters(user(token).id(), novelId));
    }

    @Override
    public ResponseEntity<List<ExperienceResponse>>
            listExperiencesApiV1NovelsNovelIdCharactersCharacterIdExperiencesGet(
                    String novelId, String characterId, String token) {
        return ResponseEntity.ok(service().listExperiences(
                user(token).id(), novelId, characterId));
    }

    @Override
    public ResponseEntity<List<FactionResponse>>
            listFactionsApiV1NovelsNovelIdFactionsGet(
                    String novelId, String token) {
        return ResponseEntity.ok(service().listFactions(user(token).id(), novelId));
    }

    @Override
    public ResponseEntity<List<GlossaryResponse>>
            listGlossaryApiV1NovelsNovelIdGlossaryGet(
                    String novelId, String token) {
        return ResponseEntity.ok(service().listGlossary(user(token).id(), novelId));
    }

    @Override
    public ResponseEntity<List<ItemResponse>> listItemsApiV1NovelsNovelIdItemsGet(
            String novelId, String token) {
        return ResponseEntity.ok(service().listItems(user(token).id(), novelId));
    }

    @Override
    public ResponseEntity<List<LocationResponse>>
            listLocationsApiV1NovelsNovelIdLocationsGet(
                    String novelId, String token) {
        return ResponseEntity.ok(service().listLocations(user(token).id(), novelId));
    }

    @Override
    public ResponseEntity<List<RelationResponse>>
            listRelationsApiV1NovelsNovelIdRelationsGet(
                    String novelId, String token) {
        return ResponseEntity.ok(service().listRelations(user(token).id(), novelId));
    }

    @Override
    public ResponseEntity<ContentResponse>
            saveStoryBackgroundApiV1NovelsNovelIdStoryBackgroundPut(
                    String novelId, ContentRequest request, String token) {
        return ResponseEntity.ok(service().saveStoryBackground(
                user(token).id(), novelId, request));
    }

    @Override
    public ResponseEntity<ContentResponse>
            saveStoryProgressApiV1NovelsNovelIdStoryProgressPut(
                    String novelId, ContentRequest request, String token) {
        return ResponseEntity.ok(service().saveStoryProgress(
                user(token).id(), novelId, request));
    }

    @Override
    public ResponseEntity<ContentResponse>
            saveWorldSettingApiV1NovelsNovelIdWorldSettingPut(
                    String novelId, ContentRequest request, String token) {
        return ResponseEntity.ok(service().saveWorldSetting(
                user(token).id(), novelId, request));
    }

    @Override
    public ResponseEntity<WritingBibleResponse>
            saveWritingBibleApiV1NovelsNovelIdWritingBiblePut(
                    String novelId, WritingBibleRequest request, String token) {
        return ResponseEntity.ok(service().saveWritingBible(
                user(token).id(), novelId, request));
    }

    @Override
    public ResponseEntity<CharacterResponse>
            updateCharacterApiV1NovelsNovelIdCharactersEntityIdPatch(
                    String novelId,
                    String entityId,
                    UpdateCharacterRequest request,
                    String token) {
        return ResponseEntity.ok(service().updateCharacter(
                user(token).id(), novelId, entityId, request));
    }

    @Override
    public ResponseEntity<ExperienceResponse>
            updateExperienceApiV1NovelsNovelIdExperiencesExperienceIdPatch(
                    String novelId,
                    String experienceId,
                    UpdateExperienceRequest request,
                    String token) {
        return ResponseEntity.ok(service().updateExperience(
                user(token).id(), novelId, experienceId, request));
    }

    @Override
    public ResponseEntity<FactionResponse>
            updateFactionApiV1NovelsNovelIdFactionsEntityIdPatch(
                    String novelId,
                    String entityId,
                    UpdateFactionRequest request,
                    String token) {
        return ResponseEntity.ok(service().updateFaction(
                user(token).id(), novelId, entityId, request));
    }

    @Override
    public ResponseEntity<GlossaryResponse>
            updateGlossaryApiV1NovelsNovelIdGlossaryEntityIdPatch(
                    String novelId,
                    String entityId,
                    UpdateGlossaryRequest request,
                    String token) {
        return ResponseEntity.ok(service().updateGlossary(
                user(token).id(), novelId, entityId, request));
    }

    @Override
    public ResponseEntity<ItemResponse>
            updateItemApiV1NovelsNovelIdItemsEntityIdPatch(
                    String novelId,
                    String entityId,
                    UpdateItemRequest request,
                    String token) {
        return ResponseEntity.ok(service().updateItem(
                user(token).id(), novelId, entityId, request));
    }

    @Override
    public ResponseEntity<LocationResponse>
            updateLocationApiV1NovelsNovelIdLocationsEntityIdPatch(
                    String novelId,
                    String entityId,
                    UpdateLocationRequest request,
                    String token) {
        return ResponseEntity.ok(service().updateLocation(
                user(token).id(), novelId, entityId, request));
    }

    @Override
    public ResponseEntity<RelationResponse>
            updateRelationApiV1NovelsNovelIdRelationsRelationIdPatch(
                    String novelId,
                    String relationId,
                    UpdateRelationRequest request,
                    String token) {
        return ResponseEntity.ok(service().updateRelation(
                user(token).id(), novelId, relationId, request));
    }

    private LoreService service() {
        return configuredService.orElseThrow(() -> new ApiException(
                503, "LORE_SERVICE_UNAVAILABLE", "设定服务暂时不可用"));
    }

    private AuthenticatedUser user(String token) {
        return configuredUsers.orElseThrow(() ->
                        new ApiException(503, "AUTH_UNAVAILABLE", "认证服务暂时不可用"))
                .require(token);
    }
}
